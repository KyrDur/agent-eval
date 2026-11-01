#!/usr/bin/env python3
"""Actual local retrieval only. Draft labels; no judge, human, or holdout claims."""
import argparse,json,time,resource,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'AgentEval'))
from experiments.store import JsonStore
from experiments.retrieval_knowledge import FrozenKnowledge
from experiments.retrieval_models import RetrievalConfig
from experiments.rag_retrieval import search,assemble
from experiments.rag_evidence import coverage
from experiments.rag_policy_pack import public_pack
from experiments.canonical import digest

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
 pack=public_pack();(args.output/'input-pack.json').write_text(json.dumps(pack,ensure_ascii=False,indent=2)+'\n');store=JsonStore(args.output/'store');knowledge=FrozenKnowledge(store)
 dataset=knowledge.create(pack['documents'],pack['name'],metadata={'pack_id':pack['pack_id'],'source':pack['source']})
 profiles=[('minilm-window','all-MiniLM-L6-v2','normalized-character-window-v1'),('bge-window','BAAI/bge-small-zh-v1.5','normalized-character-window-v1'),('minilm-section','all-MiniLM-L6-v2','source-section-v1'),('bge-section','BAAI/bge-small-zh-v1.5','source-section-v1')]
 report={'schema_version':'LOCAL_RETRIEVAL_STUDY_V1','dataset_id':dataset.knowledge_dataset_id,'knowledge_hash':dataset.knowledge_hash,'pack_hash':digest(pack),'label_status':'CODEX_DRAFT_NOT_HUMAN_REFERENCE','holdout_used':False,'provider_requests':0,'repetitions':1,'top_k':3,'candidate_pool_size':20,'profiles':[]}
 for name,model,algorithm in profiles:
  started=time.monotonic();index=knowledge.build(dataset.knowledge_dataset_id,1,{'chunk_size':200,'chunk_overlap':20,'algorithm':algorithm},model);build_ms=round((time.monotonic()-started)*1000)
  modes=['VECTOR','BM25','HYBRID'] if name=='bge-section' else ['VECTOR']
  for mode in modes:
   config=RetrievalConfig(top_k=3,retrieval_mode=mode);rows=[]
   for case in pack['debug_cases']:
    started=time.monotonic();candidates=search(knowledge,index,case['query'],config);selected=candidates[:3];context,trace=assemble(index,selected,config)
    cov=coverage(case['knowledge_requirements'],dataset.documents,context)
    rows.append({'case_id':case['case_id'],'query':case['query'],'elapsed_ms':round((time.monotonic()-started)*1000),'document_hit':any(r['document_id'] in case['relevant_document_ids'] for r in selected),
     'draft_fact_included':cov['included_count'],'draft_fact_total':cov['required_count'],'draft_fact_ratio':cov['included_count']/cov['required_count'] if cov['required_count'] else None,
     'context_characters':sum(len(r['text']) for r in context),'selected':selected,'candidate_count':len(candidates),'source_ranks_recorded':mode!='HYBRID' or all('source_ranks' in r for r in selected)})
   entry={'profile':name+'-'+mode.lower(),'model':model,'algorithm':algorithm,'mode':mode,'index_id':index.index_id,'embedding_snapshot':index.embedding_snapshot,'build_elapsed_ms':build_ms,'chunk_count':len(index.chunks),
    'draft_document_hit_count':sum(r['document_hit'] for r in rows),'denominator':len(rows),'draft_fact_inclusion_mean':statistics.mean(r['draft_fact_ratio'] for r in rows if r['draft_fact_ratio'] is not None),
    'query_median_ms':statistics.median(r['elapsed_ms'] for r in rows),'query_max_ms':max(r['elapsed_ms'] for r in rows),'context_characters_mean':statistics.mean(r['context_characters'] for r in rows),'rows':rows}
   report['profiles'].append(entry);(args.output/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:entry[k] for k in ['profile','draft_document_hit_count','denominator','draft_fact_inclusion_mean','build_elapsed_ms','query_median_ms']},ensure_ascii=False),flush=True)
 report['max_child_rss_raw']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss;report['max_child_rss_unit']='bytes' if sys.platform=='darwin' else 'KiB'
 report['resource_note']='Single sequential study; BGE reloads a bounded CPU worker per request. Child maximum is aggregate, not independent per-condition or concurrency evidence. Cold OS cache not controlled.'
 (args.output/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
