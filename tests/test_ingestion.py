from io import BytesIO
from uuid import UUID
from zipfile import ZipFile, ZIP_DEFLATED
import pytest
from openpyxl import Workbook
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from app.ingestion.config import Profile, IngestionConfig
from app.ingestion.parsers import FormatError
from app.ingestion.validation import prepare

HEADER="date,amount,type,category,provider\n"
GOOD="2026-01-05,125.10,revenue,Collections,DEMO1\n"
CAT=UUID('00000000-0000-0000-0000-000000000001')
PROVIDER=UUID('00000000-0000-0000-0000-000000000002')

@pytest.fixture
def profile():
    return Profile(columns={k:k for k in ('date','amount','type','category','provider')},
        date_format='%Y-%m-%d',types={'revenue':'revenue','expense':'expense'},
        categories={'Collections':CAT},providers={'DEMO1':PROVIDER},
        allow_negative_amounts=False,currency='USD')

def test_valid_csv_and_null_provider(profile):
    result=prepare((HEADER+GOOD+'2026-01-06,0.00,revenue,Collections,\n').encode(),'csv',profile)
    assert result.total_rows==2 and not result.rejections
    assert result.rows[0]['amount']=='125.10'
    assert result.rows[1]['provider_key'] is None
    assert result.rows[0]['category_key']==str(CAT)

def test_approved_revenue_dimensions_and_rejected_patient_values(profile):
    profile=Profile.model_validate({**profile.model_dump(),
        'columns':{**profile.columns,'medical_insurance':'insurer','billing_code':'code'},
        'medical_insurances':{'Demo A':'Demo A'},'billing_codes':{'C1':'C1'}})
    header=HEADER.rstrip()+',insurer,code\n'
    good=GOOD.rstrip()+',Demo A,C1\n'
    result=prepare((header+good).encode(),'csv',profile)
    assert result.rows[0]['medical_insurance']=='Demo A' and result.rows[0]['billing_code']=='C1'
    rejected=prepare((header+good.replace('Demo A','PRIVATE NAME')).encode(),'csv',profile)
    assert not rejected.rows and rejected.rejections[0]['code']=='invalid_revenue_dimension'
    assert 'PRIVATE NAME' not in str(rejected)
    assert not prepare((header+good.replace('revenue','expense')).encode(),'csv',profile).rows
    missing=prepare((header+GOOD.rstrip()+',,\n').encode(),'csv',profile)
    assert missing.rows[0]['medical_insurance'] is None

def test_legacy_profile_hash_is_unchanged(profile):
    import hashlib,json
    legacy=profile.model_dump(mode='json')
    legacy.pop('medical_insurances');legacy.pop('billing_codes')
    assert profile.digest()==hashlib.sha256(json.dumps(legacy,sort_keys=True).encode()).hexdigest()

@pytest.mark.parametrize('line,code',[
 ('2026-01-05,0.001,revenue,Collections,DEMO1','invalid_amount'),
 ('2026-01-05,NaN,revenue,Collections,DEMO1','invalid_amount'),
 ('2026-01-05,1e2,revenue,Collections,DEMO1','invalid_amount'),
 ('2026-01-05,$20,revenue,Collections,DEMO1','invalid_amount'),
 ('2026-01-05,-20,revenue,Collections,DEMO1','negative_amount'),
 ('2026-02-30,20,revenue,Collections,DEMO1','invalid_date'),
 ('2026-1-05,20,revenue,Collections,DEMO1','invalid_date'),
 ('46027,20,revenue,Collections,DEMO1','invalid_date'),
 ('2026-01-05,20,unknown,Collections,DEMO1','unknown_type'),
 ('2026-01-05,20,revenue,Secret Name,DEMO1','unknown_category'),
 ('2026-01-05,20,revenue,Collections,Secret Name','unknown_provider'),
 ('2026-01-05,,revenue,Collections,DEMO1','required_value'),
 ('2026-01-05,20,revenue,Collections','column_count'),
 ('','column_count'),
])
def test_rejected_rows_are_specific_and_sanitized(profile,line,code):
    result=prepare((HEADER+line+'\n').encode(),'csv',profile)
    assert result.rows==[]
    assert result.total_rows==1
    assert result.rejections[0]['code']==code
    assert 'Secret Name' not in str(result)

def test_negative_explicitly_enabled(profile):
    p=profile.model_copy(update={'allow_negative_amounts':True})
    assert prepare((HEADER+GOOD.replace('125.10','-125.10')).encode(),'csv',p).rows[0]['amount']=='-125.10'

def test_no_silent_drop_and_no_intrafile_dedup(profile):
    result=prepare((HEADER+GOOD+'\n'+GOOD).encode(),'csv',profile)
    assert len(result.rows)==2 and len(result.rejections)==1
    assert [r['source_row'] for r in result.rows]==[1,3]
    assert result.total_rows==3

@pytest.mark.parametrize('data,code',[
 (b'','empty_file'), (b'\xff','invalid_csv'),
 ((HEADER.rstrip()+',patient_name\n'+GOOD.rstrip()+',Someone\n').encode(),'header_mismatch'),
 (b'date,date,type,category,provider\n','header_mismatch'),
 (HEADER.encode(),'no_data'),
 ((HEADER+'"unterminated').encode(),'invalid_csv'),
])
def test_file_failures(profile,data,code):
    with pytest.raises(FormatError) as exc: prepare(data,'csv',profile)
    assert exc.value.code==code
    assert 'Someone' not in str(exc.value)

def workbook(rows,extra_sheet=False):
    wb=Workbook(); ws=wb.active
    for row in rows: ws.append(row)
    if extra_sheet: wb.create_sheet('Do not silently ignore')
    stream=BytesIO(); wb.save(stream); return stream.getvalue()

def test_xlsx_numeric_amount_without_float_conversion(profile):
    data=workbook([HEADER.strip().split(','),['2026-01-05',125.1,'revenue','Collections','DEMO1'],
                   ['2026-01-06','0.10','revenue','Collections',None]])
    result=prepare(data,'xlsx',profile)
    assert [r['amount'] for r in result.rows]==['125.1','0.10']
    assert not result.rejections

def test_xlsx_formula_rejected(profile):
    data=workbook([HEADER.strip().split(','),['2026-01-05','=1+2','revenue','Collections','DEMO1']])
    assert prepare(data,'xlsx',profile).rejections[0]['code']=='formula'

def test_xlsx_multiple_sheets_rejected(profile):
    with pytest.raises(FormatError,match='exactly one worksheet'):
        prepare(workbook([HEADER.strip().split(',')],True),'xlsx',profile)

def test_malformed_xlsx(profile):
    with pytest.raises(FormatError) as exc: prepare(b'not a workbook','xlsx',profile)
    assert exc.value.code=='invalid_xlsx'

def test_structured_pdf(profile):
    out=BytesIO(); doc=SimpleDocTemplate(out)
    table=Table([HEADER.strip().split(','),['2026-01-05','125.10','revenue','Collections','DEMO1']])
    table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),1,colors.black)]))
    doc.build([table])
    result=prepare(out.getvalue(),'pdf',profile)
    assert result.rows[0]['amount']=='125.10' and not result.rejections
    assert result.rows[0]['location']=='page 1, table 1, row 2'

def test_pdf_without_tables_fails(profile):
    out=BytesIO(); c=canvas.Canvas(out); c.drawString(50,700,'A statement without a table'); c.save()
    with pytest.raises(FormatError) as exc: prepare(out.getvalue(),'pdf',profile)
    assert exc.value.code=='pdf_no_table'

def test_image_only_pdf_rejected(profile):
    out=BytesIO(); c=canvas.Canvas(out); c.rect(50,50,100,100); c.showPage(); c.save()
    with pytest.raises(FormatError) as exc: prepare(out.getvalue(),'pdf',profile)
    assert exc.value.code=='pdf_no_text'

def test_profile_column_remapping(profile):
    mapped=profile.model_copy(update={'columns':{'date':'Day','amount':'Value','type':'Kind','category':'Bucket','provider':'Clinician'},'delimiter':';'})
    result=prepare(b'Day;Value;Kind;Bucket;Clinician\n2026-01-05;1.00;revenue;Collections;DEMO1\n','csv',mapped)
    assert len(result.rows)==1
    assert profile.digest()!=mapped.digest()

def test_enabled_config_requires_stakeholder_inputs():
    with pytest.raises(ValueError): IngestionConfig(mode='clinic')
    assert not IngestionConfig().permits(PROVIDER)

def test_profile_rejects_ambiguous_mappings(profile):
    data=profile.model_dump(); data['columns']['amount']='date'
    with pytest.raises(ValueError): Profile(**data)
