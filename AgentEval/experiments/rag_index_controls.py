"""Narrowly permitted derived-index differences; all other controls remain frozen."""
from .retrieval_models import KnowledgeIndex


def embedding_identity(index):
    return {k:v for k,v in index.embedding_snapshot.items() if k!='index_generation'}


def validate_index_change(kind,old,new):
    if old.index_id==new.index_id:raise ValueError('INDEX_CHANGE_NO_DIFFERENCE')
    if old.knowledge_dataset_id!=new.knowledge_dataset_id:raise ValueError('KNOWLEDGE_DATASET_CHANGED')
    if kind=='KNOWLEDGE_UPDATE':
        if new.knowledge_version<=old.knowledge_version or old.chunk_config!=new.chunk_config or embedding_identity(old)!=embedding_identity(new):
            raise ValueError('KNOWLEDGE_UPDATE_SCOPE_CHANGED')
    elif kind=='CHUNKING_CHANGE':
        if old.knowledge_hash!=new.knowledge_hash or old.knowledge_version!=new.knowledge_version or old.chunk_config==new.chunk_config or embedding_identity(old)!=embedding_identity(new):
            raise ValueError('CHUNKING_CHANGE_SCOPE_CHANGED')
    elif kind=='EMBEDDING_CHANGE':
        if old.knowledge_hash!=new.knowledge_hash or old.knowledge_version!=new.knowledge_version or old.chunk_config!=new.chunk_config or old.chunks!=new.chunks or old.embedding_snapshot['model']==new.embedding_snapshot['model']:
            raise ValueError('EMBEDDING_CHANGE_SCOPE_CHANGED')
    else:raise ValueError('INDEX_CHANGE_TYPE_INVALID')


def index_control_reasons(before,after,kind):
    allowed={'eval_set_hash','eval_set_snapshot','knowledge_snapshot','chunk_snapshot_hash','index_snapshot','embedding_snapshot'}
    reasons=[k.upper()+'_CHANGED' for k in set(before)|set(after) if k not in allowed and before.get(k)!=after.get(k)]
    a,b=before['eval_set_snapshot'],after['eval_set_snapshot']
    if a['cases']!=b['cases'] or a.get('split_reviewed')!=b.get('split_reviewed'):
        reasons.append('TEST_SEMANTICS_CHANGED')
    try:
        validate_index_change(kind,KnowledgeIndex.model_validate(before['index_snapshot']),KnowledgeIndex.model_validate(after['index_snapshot']))
    except ValueError as e:reasons.append(str(e))
    if kind!='KNOWLEDGE_UPDATE' and before['knowledge_snapshot']!=after['knowledge_snapshot']:
        reasons.append('KNOWLEDGE_CHANGED')
    return reasons
