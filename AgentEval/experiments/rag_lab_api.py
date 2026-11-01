from fastapi import APIRouter,Request
from pydantic import Field
from .api import Input,execute
from .retrieval_api import retrieval,acquire
from .retrieval_models import ChunkConfig
from .rag_evidence import SourceEvidence

router=APIRouter(prefix='/experiments',tags=['RAG knowledge evidence'])


class Preview(Input):
    version:int=Field(ge=1)
    chunk_config:ChunkConfig


class DiagnosticInput(Input):
    case_id:str
    request_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
    quotes:list[SourceEvidence]=Field(min_length=1,max_length=20)
    reviewer:str=Field(min_length=1,max_length=100)
    provider_session_id:str


@router.post('/knowledge-datasets/{identifier}/chunk-preview')
def preview(identifier:str,body:Preview):
    from .retrieval_knowledge import chunks_for
    rag=retrieval();dataset=execute(rag.store.get,'knowledge_datasets',identifier,body.version)
    return {'knowledge_version':dataset.version,'chunks':chunks_for(dataset,body.chunk_config)}


@router.get('/retrieval-evalsets/{identifier}/coverage')
def coverage(identifier:str):
    from .rag_lab import audit
    return execute(audit,retrieval(),identifier)


@router.post('/retrieval-runs/{identifier}/diagnostic')
async def diagnostic(identifier:str,body:DiagnosticInput,request:Request):
    from .rag_lab import diagnostic as run
    registry=getattr(request.app.state,'workspaces',None)
    slots=registry.expensive if registry else request.app.state.retrieval_slots
    async with slots:
        return await acquire(run(retrieval(),identifier,body.case_id,body.request_id,
            [q.model_dump() for q in body.quotes],body.reviewer,body.provider_session_id))


@router.get('/retrieval-runs/{identifier}/diagnostics')
def diagnostics(identifier:str):
    rag=retrieval();execute(rag.store.get,'retrieval_runs',identifier)
    from .rag_lab import recover_diagnostics
    return recover_diagnostics(rag,identifier)


@router.get('/retrieval-runs/{identifier}/deepeval-export')
def deepeval_export(identifier:str):
    from .rag_lab import export_deepeval
    return execute(export_deepeval,retrieval(),identifier)


from .retrieval_api import IndexInput
class IndexTaskInput(IndexInput):
    request_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')

@router.post('/knowledge-datasets/{identifier}/index-tasks')
async def index_task(identifier:str,body:IndexTaskInput):
    from .rag_index_jobs import submit
    rag=retrieval();execute(rag.store.get,'knowledge_datasets',identifier,body.version)
    return await acquire(submit(rag.store,body.request_id,{'dataset_id':identifier,'version':body.version,
        'config':body.chunk_config.model_dump() if body.chunk_config else None,'embedding_model':body.embedding_model}))

@router.get('/index-tasks/{identifier}')
def index_task_read(identifier:str):
    from .rag_index_jobs import read
    return execute(read,retrieval().store,identifier)

@router.get('/index-task-receipts/{request_id}')
def index_receipt(request_id:str):
    from fastapi import HTTPException
    from .rag_index_jobs import read
    rag=retrieval()
    job=next((j for j in rag.store.list('index_builds') if j.request_id==request_id),None)
    if not job:raise HTTPException(404,'INDEX_RECEIPT_NOT_FOUND')
    return read(rag.store,job.job_id)

@router.post('/index-tasks/{identifier}/cancel')
async def index_task_cancel(identifier:str):
    from .rag_index_jobs import cancel
    return await acquire(cancel(retrieval().store,identifier))

@router.get('/rag-policy-pack')
def policy_pack():
    from .rag_policy_pack import public_pack
    return public_pack()


class DeepEvalInput(Input):
    case_ids:list[str]=Field(min_length=1,max_length=3)
    provider_session_id:str
    request_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
    request_limit:int=Field(ge=1,le=24,strict=True)

@router.post('/retrieval-runs/{identifier}/deepeval')
async def deepeval(identifier:str,body:DeepEvalInput,request:Request):
    from .rag_deepeval import evaluate
    registry=getattr(request.app.state,'workspaces',None)
    slots=registry.expensive if registry else request.app.state.retrieval_slots
    async with slots:
        return await acquire(evaluate(retrieval(),identifier,body.case_ids,body.provider_session_id,body.request_id,body.request_limit))

@router.get('/retrieval-runs/{identifier}/deepeval')
def deepeval_observations(identifier:str):
    from .rag_deepeval import observations
    rag=retrieval();execute(rag.store.get,'retrieval_runs',identifier)
    return execute(observations,rag,identifier)
