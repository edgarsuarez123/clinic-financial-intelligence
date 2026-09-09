from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from .parsers import PARSERS, FormatError, InvalidCell, MAX_BYTES, MAX_ROWS, MAX_CELL

@dataclass(frozen=True)
class PreparedUpload:
    rows: list[dict]
    rejections: list[dict]
    total_rows: int

def rejection(number, location, code, message):
    return {"source_row":number,"location":location,"code":code,"reason":message}

def prepare(data: bytes, kind: str, profile) -> PreparedUpload:
    if not data: raise FormatError("empty_file","File is empty.")
    if len(data)>MAX_BYTES: raise FormatError("file_too_large","File exceeds 10 MiB.")
    if kind not in PARSERS: raise FormatError("unsupported_format","Use CSV, XLSX, or structured PDF.")
    accepted=[]; rejected=[]; number=0; table_count=0
    for location,rows in PARSERS[kind].tables(data,profile):
        table_count+=1
        if not rows: raise FormatError("no_header","A column header is required.")
        header=rows[0]
        if len(header)!=5 or any(not isinstance(v,str) for v in header) or set(header)!=set(profile.columns.values()):
            raise FormatError("header_mismatch","Headers must match all five approved mapped columns exactly; extra or missing columns are rejected.")
        indices={key:header.index(value) for key,value in profile.columns.items()}
        for local_row,values in enumerate(rows[1:],2):
            number+=1
            if number>MAX_ROWS: raise FormatError("too_many_rows","File exceeds 50,000 data rows.")
            row_location=f"{location}, row {local_row}"
            def reject(code,message): rejected.append(rejection(number,row_location,code,message))
            if len(values)!=len(header):
                reject("column_count","Row does not contain exactly the mapped number of fields."); continue
            invalid=next((x for x in values if isinstance(x,InvalidCell)),None)
            if invalid:
                reject(invalid.code,invalid.message); continue
            if any(not isinstance(x,str) or len(x)>MAX_CELL for x in values):
                reject("cell_length","A cell exceeds 256 characters or has an unsupported type."); continue
            raw={key:values[index] for key,index in indices.items()}
            if any(raw[x]=="" for x in ("date","amount","type","category")):
                reject("required_value","Date, amount, type and category are required."); continue
            try:
                day=datetime.strptime(raw["date"],profile.date_format).date()
                if day.strftime(profile.date_format)!=raw["date"]: raise ValueError()
            except ValueError:
                reject("invalid_date","Date must exactly match the configured format; Excel serial dates are not inferred."); continue
            if not re.fullmatch(r"-?\d{1,16}(?:\.\d{1,2})?",raw["amount"]):
                reject("invalid_amount","Amount must be a plain decimal with at most two fractional digits; no currency symbols, grouping, or exponents."); continue
            amount=Decimal(raw["amount"])
            if amount<0 and not profile.allow_negative_amounts:
                reject("negative_amount","This mapping does not permit negative amounts."); continue
            transaction_type=profile.types.get(raw["type"])
            if not transaction_type:
                reject("unknown_type","Transaction type is not in the approved mapping."); continue
            category=profile.categories.get(raw["category"])
            if not category:
                reject("unknown_category","Category is not in the approved mapping."); continue
            provider=profile.providers.get(raw["provider"]) if raw["provider"] else None
            if raw["provider"] and provider is None:
                reject("unknown_provider","Provider identifier is not in the approved mapping."); continue
            accepted.append({"source_row":number,"location":row_location,"date":day.isoformat(),
                "amount":str(amount),"type":transaction_type,"category_key":str(category),
                "provider_key":str(provider) if provider else None})
    if not table_count or number==0: raise FormatError("no_data","No data rows were found.")
    return PreparedUpload(accepted,rejected,number)
