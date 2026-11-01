"""Deterministic lexical/hybrid retrieval and evidence-preserving context assembly."""
import math,re
from collections import Counter


def terms(text):
    # Versioned CJK unigram+bigram tokenizer; preserves ASCII product identifiers.
    text=text.lower()
    values=re.findall(r'[a-z0-9]+(?:[-_.][a-z0-9]+)*',text)
    for seq in re.findall(r'[\u3400-\u9fff]+',text):
        values.extend(seq);values.extend(seq[i:i+2] for i in range(len(seq)-1))
    return values


def lexical(index,query,count):
    bags=[Counter(terms(c['text'])) for c in index.chunks]
    lengths=[sum(b.values()) for b in bags];avg=sum(lengths)/max(1,len(bags));q=set(terms(query))
    df={t:sum(t in b for b in bags) for t in q};rows=[]
    for c,b,n in zip(index.chunks,bags,lengths):
        score=sum(math.log(1+(len(bags)-df[t]+.5)/(df[t]+.5))*b[t]*2.5/
            (b[t]+1.5*(.25+.75*n/(avg or 1))) for t in q if b[t])
        if score>0:rows.append({**c,'score':score,'bm25_score':score,'retrieval_source':'BM25'})
    rows.sort(key=lambda x:(-x['score'],x['chunk_id']))
    return [{**r,'rank':i+1} for i,r in enumerate(rows[:count])]


def search(knowledge,index,query,config):
    mode=config.retrieval_mode;n=config.candidate_pool_size
    if mode=='VECTOR':return knowledge.search(index,query,n)
    bm=lexical(index,query,n)
    if mode=='BM25':return bm
    vector=knowledge.search(index,query,n);merged={}
    for name,rows in [('VECTOR',vector),('BM25',bm)]:
        for rank,row in enumerate(rows,1):
            entry=merged.setdefault(row['chunk_id'],{**row,'fusion_score':0.,'source_ranks':{}})
            entry['fusion_score']+=1/(60+rank);entry['source_ranks'][name]=rank
    rows=sorted(merged.values(),key=lambda x:(-x['fusion_score'],x['chunk_id']))[:n]
    return [{**r,'rank':i+1,'score':r['fusion_score'],'retrieval_source':'HYBRID_RRF_60'} for i,r in enumerate(rows)]


def assemble(index,selected,config):
    if config.context_strategy=='SELECTED':
        return selected,{'strategy':'SELECTED','added_ids':[],'removed_ids':[],'characters':sum(len(c['text']) for c in selected)}
    by_id={c['chunk_id']:c for c in index.chunks};ordered=[];seen=set()
    for hit in selected:
        source=by_id[hit['chunk_id']]
        siblings=[c for c in index.chunks if c['document_id']==source['document_id'] and
            ((config.context_strategy=='PARENT' and source.get('parent_id') and c.get('parent_id')==source['parent_id']) or
             (config.context_strategy=='NEIGHBORS' and abs(c['chunk_index']-source['chunk_index'])<=1))]
        # Keep hit first. Additional evidence is deterministic, never selected from answer labels.
        for c in [source,*sorted(siblings,key=lambda c:c['chunk_index'])]:
            if c['chunk_id'] not in seen:ordered.append(c);seen.add(c['chunk_id'])
    kept=[];removed=[];size=0
    for c in ordered:
        if size+len(c['text'])>12000:removed.append(c['chunk_id']);continue
        kept.append({**c,'context_origin':'SELECTED' if c['chunk_id'] in {h['chunk_id'] for h in selected} else 'EXPANDED'})
        size+=len(c['text'])
    return kept,{'strategy':config.context_strategy,'added_ids':[c['chunk_id'] for c in kept if c['context_origin']=='EXPANDED'],
        'removed_ids':removed,'character_budget':12000,'budget_unit':'CHARACTERS_NOT_TOKENS','characters':size}
