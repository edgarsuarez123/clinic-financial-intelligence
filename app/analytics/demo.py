"""Create analytics configuration only from an explicitly synthetic ingestion setup."""
import argparse
import json
from pathlib import Path
from ..ingestion.config import IngestionConfig

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    source=IngestionConfig.model_validate_json(Path(args.source).read_text())
    if source.mode!='synthetic': parser.error('Only an explicitly synthetic source is accepted')
    output=Path(args.output)
    if output.exists(): parser.error('Output exists; choose a new output path')
    categories={str(key):'Synthetic '+label for profile in source.profiles.values() for label,key in profile.categories.items()}
    providers={str(key):'Synthetic '+label for profile in source.profiles.values() for label,key in profile.providers.items()}
    output.write_text(json.dumps({'synthetic_data':True,'authorized_user_ids':[str(x) for x in source.authorized_user_ids],
        'compensation_authorized_user_ids':[str(x) for x in source.authorized_user_ids],
        'public_category_labels':categories,'provider_labels':providers,
        'fully_loaded_cost_coverage':{}},indent=2)+'\n')

if __name__=='__main__': main()
