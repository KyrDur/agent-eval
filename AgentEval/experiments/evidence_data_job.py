"""Warehouse/file adapter: prepare frozen business evidence without a model call.

Example: PYTHONPATH=AgentEval python -m experiments.evidence_data_job STORE DOMAIN INPUT
  --mapping mapping.json --decisions reviewed-decisions.json --actor domain-owner
  --reason '2026-10-18 data window reviewed' --parent previous-batch-id

The warehouse owns extraction/window semantics. This adapter consumes its immutable
JSON/JSONL/CSV output; no SQL connection or production table is assumed.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from .store import JsonStore
from .operations_service import OperationsService


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('store');parser.add_argument('domain');parser.add_argument('input')
    parser.add_argument('--mapping');parser.add_argument('--decisions');parser.add_argument('--actor',default='data-job-owner')
    parser.add_argument('--reason',default='');parser.add_argument('--parent');parser.add_argument('--preview',action='store_true')
    args=parser.parse_args();source=Path(args.input)
    content=source.read_text(encoding='utf-8-sig');format='csv' if source.suffix=='.csv' else 'jsonl' if source.suffix=='.jsonl' else 'json'
    mapping=json.loads(Path(args.mapping).read_text()) if args.mapping else {}
    op=OperationsService(SimpleNamespace(store=JsonStore(args.store),providers=None))
    preview=op.preview(args.domain,content,format,mapping)
    if args.preview:
        print(json.dumps(preview,ensure_ascii=False,default=str));return
    if not args.decisions or not args.reason:parser.error('Save requires reviewed --decisions and --reason; use --preview first.')
    decisions=json.loads(Path(args.decisions).read_text())
    batch=op.save_batch(args.domain,content,format,mapping,'NECESSARY',source.name,args.actor,args.reason,decisions,args.parent,preview['preview_hash'])
    print(json.dumps({'batch_id':batch.batch_id,'domain_id':batch.domain_id,'content_hash':batch.content_hash,'model_calls':0},ensure_ascii=False))

if __name__=='__main__':main()
