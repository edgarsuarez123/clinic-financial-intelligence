"""Bounded in-memory extraction. Parsers never persist or log raw input."""
from abc import ABC, abstractmethod
import csv
from io import BytesIO, StringIO
import posixpath
from zipfile import ZipFile, BadZipFile
from defusedxml import ElementTree as ET

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50000
MAX_CELL = 256
MAX_EXPANDED = 50 * 1024 * 1024
NS = {"s":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

class FormatError(ValueError):
    def __init__(self, code, message):
        self.code=code
        super().__init__(message)

class Parser(ABC):
    @abstractmethod
    def tables(self, data, profile):
        """Yield (safe location label, list of source rows), with a header first."""

class CSVParser(Parser):
    def tables(self, data, profile):
        try:
            text=data.decode("utf-8-sig")
            if "\x00" in text: raise ValueError()
            reader=csv.reader(StringIO(text,newline=""),delimiter=profile.delimiter,strict=True)
            rows=[]
            for row in reader:
                rows.append(row)
                if len(rows)>MAX_ROWS+1: raise FormatError("too_many_rows","File exceeds the row limit.")
            yield "csv",rows
        except FormatError: raise
        except (UnicodeError,ValueError,csv.Error):
            raise FormatError("invalid_csv","CSV must be valid UTF-8 with correctly quoted fields.") from None

class XLSXParser(Parser):
    def tables(self, data, profile):
        try:
            with ZipFile(BytesIO(data)) as z:
                infos=z.infolist()
                if len(infos)>2000 or sum(x.file_size for x in infos)>MAX_EXPANDED:
                    raise FormatError("xlsx_limit","Workbook exceeds expansion limits.")
                if len({x.filename for x in infos}) != len(infos): raise ValueError()
                if any(x.filename.startswith("xl/externalLinks/") or x.filename.endswith("vbaProject.bin") for x in infos):
                    raise FormatError("xlsx_active_content","External links and macros are not supported.")
                workbook=ET.fromstring(z.read("xl/workbook.xml"))
                sheets=workbook.findall("s:sheets/s:sheet",NS)
                if len(sheets)!=1:
                    raise FormatError("xlsx_sheets","Provide an export with exactly one worksheet; no sheets are silently ignored.")
                if sheets[0].get("state","visible")!="visible":
                    raise FormatError("xlsx_hidden","Hidden worksheets are not supported.")
                rid=sheets[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                rels=ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
                rel=next((x for x in rels if x.get("Id")==rid),None)
                if rel is None or rel.get("TargetMode")=="External": raise ValueError()
                target=rel.get("Target","")
                path=posixpath.normpath(target.lstrip("/") if target.startswith("/") else "xl/"+target)
                if not path.startswith("xl/worksheets/"): raise ValueError()
                shared=[]
                if "xl/sharedStrings.xml" in z.namelist():
                    root=ET.fromstring(z.read("xl/sharedStrings.xml"))
                    shared=["".join(e.itertext()) for e in root.findall("s:si",NS)]
                root=ET.fromstring(z.read(path))
                if root.find("s:mergeCells",NS) is not None:
                    raise FormatError("xlsx_merged","Merged cells are not supported in tabular exports.")
                rows=[]; expected=1
                for node in root.findall("s:sheetData/s:row",NS):
                    idx=int(node.get("r","0"))
                    if idx < expected or idx>MAX_ROWS+1: raise ValueError()
                    while expected<idx: rows.append([]); expected+=1
                    if node.get("hidden") in ("1","true"):
                        raise FormatError("xlsx_hidden","Hidden rows are not supported.")
                    row=[]
                    for cell in node.findall("s:c",NS):
                        ref=cell.get("r","")
                        letters="".join(c for c in ref if c.isalpha())
                        col=0
                        for ch in letters: col=col*26+ord(ch)-64
                        if not 1<=col<=100 or col<=len(row): raise ValueError()
                        row.extend([""]*(col-len(row)))
                        kind=cell.get("t")
                        if cell.find("s:f",NS) is not None:
                            row[col-1]=InvalidCell("formula","Formula cells are not accepted; export literal values.")
                            continue
                        val=cell.find("s:v",NS)
                        raw=val.text if val is not None and val.text is not None else ""
                        if kind=="s": row[col-1]=shared[int(raw)]
                        elif kind=="inlineStr": row[col-1]="".join(t.text or "" for t in cell.findall("s:is//s:t",NS))
                        elif kind in (None,"n","str","d"): row[col-1]=raw
                        else: row[col-1]=InvalidCell("cell_type","Unsupported spreadsheet cell type.")
                    rows.append(row); expected=idx+1
                if rows:
                    width=len(rows[0])
                    rows=[r+[""]*max(0,width-len(r)) for r in rows]
                yield "xlsx",rows
        except FormatError: raise
        except Exception:
            raise FormatError("invalid_xlsx","Workbook is invalid, encrypted, or outside the supported table format.") from None

class PDFParser(Parser):
    def tables(self, data, profile):
        import pdfplumber
        try:
            with pdfplumber.open(BytesIO(data)) as pdf:
                if not 1<=len(pdf.pages)<=50:
                    raise FormatError("pdf_pages","PDF must contain 1–50 pages.")
                for page_no,page in enumerate(pdf.pages,1):
                    if not page.chars:
                        raise FormatError("pdf_no_text","Scanned or image-only PDFs are not supported. Export CSV/XLSX or a text PDF.")
                    tables=page.extract_tables({"vertical_strategy":profile.pdf_strategy,
                                                "horizontal_strategy":profile.pdf_strategy})
                    if not tables:
                        raise FormatError("pdf_no_table","A page has no reliably extractable table. Export CSV/XLSX instead.")
                    for table_no,rows in enumerate(tables,1):
                        yield f"page {page_no}, table {table_no}",[[v if v is not None else "" for v in row] for row in rows]
        except FormatError: raise
        except Exception:
            raise FormatError("invalid_pdf","PDF cannot be read as a structured table; export CSV/XLSX instead.") from None

class InvalidCell:
    def __init__(self,code,message): self.code,self.message=code,message

PARSERS={"csv":CSVParser(),"xlsx":XLSXParser(),"pdf":PDFParser()}
