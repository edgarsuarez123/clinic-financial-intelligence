"""Explicitly seed a synthetic demo into a DISPOSABLE database, never clinic data."""
import argparse
import json
import os
from pathlib import Path
import psycopg
from uuid import uuid4
from ..demo_data import STAFF, INSURERS, CODES, CATEGORIES

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("username")
    parser.add_argument("--output",required=True)
    parser.add_argument("--confirm-disposable",action="store_true",required=True)
    parser.add_argument("--extend-existing",action="store_true")
    args=parser.parse_args()
    if os.getenv('APP_ENV') not in {'dev','test'}: parser.error('Demo setup requires APP_ENV=dev or test')
    existing = None
    if args.extend_existing and not Path(args.output).exists(): parser.error('Extension requires an existing synthetic configuration')
    if Path(args.output).exists():
        if not args.extend_existing: parser.error("Output exists; choose a new output path")
        existing = json.loads(Path(args.output).read_text())
        if existing.get('mode') != 'synthetic': parser.error('Only synthetic configuration can be extended')
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as c:
        user=c.execute("SELECT user_id FROM core.app_user WHERE username=%s AND deleted_at IS NULL",(args.username,)).fetchone()
        if not user: parser.error("Create the synthetic login with app.bootstrap first")
        if not args.extend_existing and c.execute("SELECT count(*) FROM analytics.transactions").fetchone()[0]:
            parser.error("Demo initialization requires an empty transaction table")
        if existing:
            legacy = existing['profiles']['synthetic']
            provider=legacy['providers']['DEMO1']; revenue=legacy['categories']['Collections']; expense=legacy['categories']['Supplies']
        else:
            provider=uuid4(); revenue=uuid4(); expense=uuid4()
            c.execute("INSERT INTO analytics.dim_provider (provider_key,name,role) VALUES (%s,'SYNTHETIC PROVIDER','demo')",(provider,))
            c.execute("INSERT INTO analytics.dim_category (category_key,category_name,category_type) VALUES (%s,'SYNTHETIC Collections','revenue'),(%s,'SYNTHETIC Supplies','variable_cost')",(revenue,expense))
        profile={"columns":{k:k for k in ("date","amount","type","category","provider")},
            "date_format":"%Y-%m-%d","types":{"revenue":"revenue","expense":"expense"},
            "categories":{"Collections":str(revenue),"Supplies":str(expense)},
            "providers":{"DEMO1":str(provider)},"allow_negative_amounts":False,"currency":"USD"}
        revenue_profile={**profile,'columns':{**profile['columns'],'medical_insurance':'medical_insurance','billing_code':'billing_code'},
            'medical_insurances':{'Demo Health A':'Demo Health A','Demo Health B':'Demo Health B'},
            'billing_codes':{'DEMO-001':'DEMO-001','DEMO-002':'DEMO-002'}}
        config={"mode":"synthetic","no_phi_confirmed":True,"authorized_user_ids":[str(user[0])],
                "profiles":{"synthetic":profile,'synthetic-revenue':revenue_profile}}
        if existing: config = existing
        providers = {}
        for name, role, _ in STAFF:
            record = c.execute('SELECT provider_key FROM analytics.dim_provider WHERE name=%s AND deleted_at IS NULL',(name,)).fetchone()
            key = record[0] if record else uuid4()
            if not record: c.execute('INSERT INTO analytics.dim_provider (provider_key,name,role) VALUES (%s,%s,%s)',(key,name,role))
            providers[name] = str(key)
        categories = {}
        for name, kind in CATEGORIES.items():
            label = 'Demo ' + name
            record = c.execute('SELECT category_key FROM analytics.dim_category WHERE category_name=%s AND deleted_at IS NULL',(label,)).fetchone()
            key = record[0] if record else uuid4()
            if not record: c.execute('INSERT INTO analytics.dim_category (category_key,category_name,category_type) VALUES (%s,%s,%s)',(key,label,kind))
            categories[name] = str(key)
        staff_profile = {**profile, 'providers': providers, 'categories': categories}
        config['profiles']['staff-costs'] = staff_profile
        config['profiles']['medical-billing'] = {**staff_profile,
            'columns': {**profile['columns'], 'medical_insurance':'medical_insurance', 'billing_code':'billing_code'},
            'medical_insurances':dict(zip(INSURERS,INSURERS)), 'billing_codes':dict(zip(CODES,CODES))}
        c.execute("INSERT INTO audit.audit_log (actor,action,target,request_id,outcome) VALUES (%s,'demo.configured','synthetic',%s,'success')",(user[0],uuid4()))
        Path(args.output).write_text(json.dumps(config,indent=2)+"\n")

if __name__=="__main__": main()
