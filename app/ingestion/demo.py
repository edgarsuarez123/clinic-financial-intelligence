"""Explicitly seed a synthetic demo into a DISPOSABLE database, never clinic data."""
import argparse
import json
import os
from pathlib import Path
import psycopg
from uuid import uuid4

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("username")
    parser.add_argument("--output",required=True)
    parser.add_argument("--confirm-disposable",action="store_true",required=True)
    args=parser.parse_args()
    if Path(args.output).exists(): parser.error("Output exists; choose a new output path")
    with psycopg.connect(os.environ["MIGRATION_DATABASE_URL"]) as c:
        user=c.execute("SELECT user_id FROM core.app_user WHERE username=%s AND deleted_at IS NULL",(args.username,)).fetchone()
        if not user: parser.error("Create the synthetic login with app.bootstrap first")
        if c.execute("SELECT count(*) FROM analytics.transactions").fetchone()[0]:
            parser.error("Demo initialization requires an empty transaction table")
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
        c.execute("INSERT INTO audit.audit_log (actor,action,target,request_id,outcome) VALUES (%s,'demo.configured','synthetic',%s,'success')",(user[0],uuid4()))
        Path(args.output).write_text(json.dumps(config,indent=2)+"\n")

if __name__=="__main__": main()
