"""Opt into a genuine local LLM after synthetic environment initialization."""
import argparse
import json
from pathlib import Path
from app.query.config import QueryConfig
ROOT=Path(__file__).resolve().parents[1]
def configure(environment,model,endpoint='http://ollama:11434/api/chat',root=ROOT):
    if environment not in {'dev','test'}: raise ValueError('Ollama is restricted to dev/test')
    if not model.strip() or ':cloud' in model.lower(): raise ValueError('Choose a downloaded local model, not a cloud model')
    path=root/'environments'/environment/'config/query.json'
    existing=json.loads(path.read_text())
    if not existing.get('synthetic_data') or not existing.get('authorized_user_ids'):
        raise ValueError('Initialize the synthetic demo environment and user first')
    config=QueryConfig.model_validate({**existing,'enabled':True,'transport':'ollama','endpoint':endpoint,
        'provider_name':'Local Ollama','model':model,'input_price_per_million':'0','output_price_per_million':'0',
        'pricing_currency':'USD','disclosure_reference':None,'dpa_reference':None})
    path.write_text(config.model_dump_json(indent=2)+'\n')
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('environment',choices=['dev','test']);parser.add_argument('--model',required=True)
    parser.add_argument('--endpoint',default='http://ollama:11434/api/chat');args=parser.parse_args()
    try: configure(args.environment,args.model,args.endpoint)
    except (ValueError,FileNotFoundError) as exc: parser.error(str(exc))
