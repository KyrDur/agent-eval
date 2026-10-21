"""Workspace-local evidence governance and independently dispatched inference."""
from typing import Literal
from fastapi import APIRouter,Query
from fastapi.responses import Response
from pydantic import Field
from .api import Input,service,execute
from .operations_service import OperationsService
from .retrieval_api import acquire

router=APIRouter(prefix='/experiments/operations',tags=['Evidence Operations'])

def operations():
    instance=service()
    if not hasattr(instance,'operations'):instance.operations=OperationsService(instance)
    return instance.operations

class DomainInput(Input):
    domain_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    name: str = Field(min_length=1,max_length=200)
    business_scope: str = Field(min_length=1,max_length=5000)
    template_id: Literal['POLICY_RAG','MISSING_KNOWLEDGE','CLARIFICATION'] = 'POLICY_RAG'
    agent_kind: Literal['RAG','TOOL_TRACE'] = 'RAG'
    judge_prompt: str | None = Field(default=None,max_length=24000)
    rules: dict = Field(default_factory=dict)
    rubric: dict | None = None
    max_attempts: int = Field(default=2,ge=1,le=5)

class PreviewInput(Input):
    domain_id: str
    content: str = Field(min_length=1,max_length=5242880)
    format: Literal['json','jsonl','csv'] = 'json'
    mapping: dict[str,str] = Field(default_factory=dict)
    history_mode: Literal['NECESSARY','FULL'] = 'NECESSARY'

class BatchInput(PreviewInput):
    name: str = Field(min_length=1,max_length=200)
    confirmed_by: str = Field(min_length=1,max_length=100)
    confirmation_reason: str = Field(min_length=1,max_length=3000)
    decisions: list[dict] = Field(min_length=1,max_length=100)
    parent_batch_id: str | None = None
    preview_hash: str

class JobInput(Input):
    batch_id: str
    provider_session_id: str
    request_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')

class ReviewInput(Input):
    sample_id: str
    evaluation_state: Literal['PASS','FAIL','EVIDENCE_INSUFFICIENT','NOT_APPLICABLE']
    reason: str = Field(min_length=1,max_length=5000)
    actor: str = Field(min_length=1,max_length=100)

class SampleInput(Input):
    count: int = Field(default=5,ge=1,le=100)
    seed: str = Field(min_length=1,max_length=128)

class CalibrationInput(Input):
    actor: str = Field(min_length=1,max_length=100)

class ScheduleInput(Input):
    domain_id: str
    batch_id: str
    provider_session_id: str
    name: str = Field(min_length=1,max_length=200)
    timezone: str = 'Asia/Shanghai'
    hour: int = Field(ge=0,le=23)
    minute: int = Field(default=0,ge=0,le=59)
    enabled: bool = True
    replaces_plan_id: str | None = None

@router.get('/overview')
def overview():
    op=operations()
    return {'domains':op.domains(),'batches':[{k:getattr(b,k) for k in ('batch_id','domain_id','name','created_at','profile_id','parent_batch_id','processing')} for b in op.store.list('evidence_batches')],
        'jobs':op.store.list('inference_jobs'),'schedules':op.schedule_health(),'sampling_plans':op.store.list('sampling_plans')}

@router.post('/domains')
def domain(body:DomainInput):return execute(operations().save_domain,**body.model_dump())

@router.post('/preview')
def preview(body:PreviewInput):return execute(operations().preview,**body.model_dump())

@router.post('/batches')
def batch(body:BatchInput):return execute(operations().save_batch,**body.model_dump())

@router.get('/batches/{identifier}')
def get_batch(identifier:str):return execute(operations().store.get,'evidence_batches',identifier)

@router.post('/jobs')
async def job(body:JobInput):
    value=execute(operations().create_job,**body.model_dump())
    await acquire(operations().dispatch(value.job_id))
    return operations().view(value.job_id)

@router.get('/jobs/{identifier}')
def view(identifier:str):return execute(operations().view,identifier)

@router.post('/jobs/{identifier}/retry')
async def retry(identifier:str):return await acquire(operations().dispatch(identifier,retry=True))

@router.post('/jobs/{identifier}/cancel')
def cancel(identifier:str):return execute(operations().cancel,identifier)

@router.post('/jobs/{identifier}/reviews')
def review(identifier:str,body:ReviewInput):return execute(operations().review,identifier,**body.model_dump())

@router.post('/jobs/{identifier}/sampling')
def sample(identifier:str,body:SampleInput):return execute(operations().sample,identifier,**body.model_dump())

@router.post('/sampling/{identifier}/calibration')
def calibration(identifier:str,body:CalibrationInput):return execute(operations().calibration_dataset,identifier,body.actor)

@router.post('/schedules')
def schedule(body:ScheduleInput):return execute(operations().save_schedule,**body.model_dump())

@router.get('/compare')
def compare(left:str,right:str):return execute(operations().compare,left,right)

@router.get('/jobs/{identifier}/export')
def export(identifier:str):
    content=execute(operations().csv,identifier)
    return Response(content,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="agent-evaluation.csv"','Cache-Control':'private, no-store'})

@router.get('/rag-source/{identifier}')
def rag_source(identifier:str):return execute(operations().from_rag,identifier)
