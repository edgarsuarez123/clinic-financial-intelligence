"""Create analytics configuration only from an explicitly synthetic ingestion setup."""
import argparse
import json
from pathlib import Path
from ..ingestion.config import IngestionConfig

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--extend-existing',action='store_true')
    args=parser.parse_args()
    source=IngestionConfig.model_validate_json(Path(args.source).read_text())
    if source.mode!='synthetic': parser.error('Only an explicitly synthetic source is accepted')
    output=Path(args.output)
    existing = None
    if output.exists():
        if not args.extend_existing: parser.error('Output exists; choose a new output path')
        existing=json.loads(output.read_text())
        if not existing.get('synthetic_data'): parser.error('Only synthetic analytics can be extended')
    categories={str(key):label for profile in source.profiles.values() for label,key in profile.categories.items()}
    providers={str(key):label for profile in source.profiles.values() for label,key in profile.providers.items()}
    result={'synthetic_data':True,'authorized_user_ids':[str(x) for x in source.authorized_user_ids],
        'compensation_authorized_user_ids':[str(x) for x in source.authorized_user_ids],
        'public_category_labels':categories,'provider_labels':providers,
        'fully_loaded_cost_coverage':{}}
    if existing:
        existing['public_category_labels'].update(categories)
        existing['provider_labels'].update(providers)
        result=existing
    output.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__': main()
