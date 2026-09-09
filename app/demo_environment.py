"""Explicit dev/test-only dummy setup; never runs in staging or production."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from .query.config import QueryConfig
from .simulation.config import SimulationConfig

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('username');parser.add_argument('--config-dir',required=True)
    parser.add_argument('--confirm-disposable',action='store_true',required=True)
    args=parser.parse_args()
    if os.getenv('APP_ENV') not in {'dev','test'}: parser.error('Dummy setup is restricted to APP_ENV=dev or test')
    directory=Path(args.config_dir)
    if not directory.is_dir(): parser.error('Prepare the environment configuration directory first')
    for filename in ('ingestion.json','analytics.json','simulation.json','query.json'):
        value=json.loads((directory/filename).read_text())
        if value.get('authorized_user_ids') or value.get('enabled') or value.get('mode','disabled')!='disabled':
            parser.error('Existing configuration is enabled; refusing to replace it')
    with tempfile.TemporaryDirectory() as temporary:
        temp=Path(temporary)
        subprocess.run([sys.executable,'-m','app.ingestion.demo',args.username,'--output',str(temp/'ingestion.json'),'--confirm-disposable'],check=True)
        subprocess.run([sys.executable,'-m','app.analytics.demo','--source',str(temp/'ingestion.json'),'--output',str(temp/'analytics.json')],check=True)
        users=json.loads((temp/'ingestion.json').read_text())['authorized_user_ids']
        simulation=SimulationConfig(authorized_user_ids=users,synthetic_data=True)
        query=QueryConfig(enabled=True,transport='demo',synthetic_data=True,authorized_user_ids=users,cost_report_user_ids=users,
            provider_name='Local deterministic demo; no external API',model='demo-catalog-v1',
            input_price_per_million='0',output_price_per_million='0',pricing_currency='USD')
        (temp/'simulation.json').write_text(simulation.model_dump_json(indent=2))
        (temp/'query.json').write_text(query.model_dump_json(indent=2))
        for filename in ('ingestion.json','analytics.json','simulation.json','query.json'):
            (directory/filename).write_text((temp/filename).read_text()+'\n')
if __name__=='__main__': main()
