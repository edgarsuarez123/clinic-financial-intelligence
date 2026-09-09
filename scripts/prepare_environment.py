"""Create isolated local configuration; no Docker or database operations."""
import argparse
import json
from pathlib import Path
import secrets

ROOT=Path(__file__).resolve().parents[1]
def prepare(name,root=ROOT):
    if name not in {'dev','test','staging','production'}: raise ValueError('Unknown environment')
    target=root/'environments'/name
    if target.exists(): raise ValueError('Environment directory exists; refusing to overwrite configuration or credentials')
    target.mkdir(parents=True,mode=0o700)
    cfg=target/'config';cfg.mkdir(mode=0o755)
    for filename,value in {
        'ingestion.json':{'mode':'disabled','no_phi_confirmed':False,'authorized_user_ids':[],'profiles':{}},
        'analytics.json':{'authorized_user_ids':[],'compensation_authorized_user_ids':[]},
        'simulation.json':{'authorized_user_ids':[],'synthetic_data':False},
        'query.json':{'enabled':False,'authorized_user_ids':[],'cost_report_user_ids':[]},
    }.items():
        path=cfg/filename;path.write_text(json.dumps(value,indent=2)+'\n');path.chmod(0o644)
    index=['dev','test','staging','production'].index(name)
    values={'APP_ENV':name,'CONFIG_DIRECTORY':'./environments/'+name+'/config',
        'API_PORT':str(8010 if name=='dev' else 8000+index),'UI_PORT':str(8501+index),'WEB_PORT':str(3000+index),
        'POSTGRES_PASSWORD':secrets.token_hex(32),'APP_DB_PASSWORD':secrets.token_hex(32),
        'MIGRATION_DB_PASSWORD':secrets.token_hex(32),'QUERY_DB_PASSWORD':secrets.token_hex(32),
        'CONFIRM_DISPOSABLE_TEST_DATABASE':'true' if name=='test' else 'false','LLM_API_KEY':''}
    path=target/'.env';path.write_text('\n'.join(k+'='+v for k,v in values.items())+'\n');path.chmod(0o600)
    return target
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('environment',choices=['dev','test','staging','production'])
    args=parser.parse_args()
    try: target=prepare(args.environment)
    except ValueError as exc: parser.error(str(exc))
    print('Created '+str(target)+'. Credentials were written to .env and are not printed. No service was started.')
