"""Python-only Retrieval API on the existing artifact store and credential vault."""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from urllib.parse import quote
from pydantic import Field
from typing import Literal
import re
from .api import service, execute, Input
from .providers import ProviderFailure
from .retrieval_models import DocumentInput, ChunkConfig, RetrievalCase, RetrievalConfig
from .retrieval_service import RetrievalService
from .retrieval_embeddings import EmbeddingFailure

router=APIRouter(prefix='/experiments',tags=['Retrieval Experiments'])

def retrieval():
    instance=service()
    if not hasattr(instance,'retrieval'): instance.retrieval=RetrievalService(instance)
    return instance.retrieval

def csv_download(exporter, identifier):
    try:
        result = exporter(retrieval(), identifier)
    except FileNotFoundError:
        raise HTTPException(404,'Artifact not found') from None
    except ValueError as error:
        code = str(error)
        if code == 'CSV_EXPORT_TOO_LARGE':
            raise HTTPException(413,code) from None
        if code == 'CSV_EXPORT_RUN_NOT_FINISHED':
            raise HTTPException(409,code) from None
        raise HTTPException(409,'CSV_EXPORT_UNAVAILABLE') from None
    return Response(result.content,media_type='text/csv; charset=utf-8',headers={
        'Content-Disposition':f"attachment; filename=\"evaluation.csv\"; filename*=UTF-8''{quote(result.filename,safe='')}",
        'Cache-Control':'private, no-store', 'X-Content-Type-Options':'nosniff',
        'X-CSV-Row-Count':str(result.row_count), 'X-Export-Schema':'EVAL_CSV_V1'})

async def acquire(coroutine):
    try: return await coroutine
    except EmbeddingFailure as error: raise HTTPException(409,str(error)) from None
    except ProviderFailure as error: raise HTTPException(409,error.code) from None
    except FileNotFoundError: raise HTTPException(404,'Artifact not found') from None
    except (ValueError,TypeError) as error:
        code=str(error)
        raise HTTPException(409,code if re.fullmatch('[A-Z_]{3,100}',code) else 'Retrieval lifecycle or frozen configuration rejected') from None

class KnowledgeInput(Input):
    documents: list[DocumentInput] = Field(min_length=1,max_length=100)
    name: str = Field(min_length=1,max_length=200)
    knowledge_dataset_id: str | None = None
    metadata: dict = Field(default_factory=dict)

class IndexInput(Input):
    version: int = Field(ge=1)
    chunk_config: ChunkConfig | None = None
    embedding_model: Literal['all-MiniLM-L6-v2','sha256-lexical-bigram-v1'] = 'all-MiniLM-L6-v2'

class EvalSetInput(Input):
    index_id: str
    name: str = Field(min_length=1,max_length=200)
    cases: list[RetrievalCase] = Field(min_length=1,max_length=100)
    retrieval_eval_set_id: str | None = None
    split_reviewed: bool = False

class RunInput(Input):
    request_id: str | None = Field(default=None,pattern=r'^[A-Za-z0-9_-]{1,128}$')
    provider_session_id: str
    retrieval_eval_set_id: str
    version: int | None = Field(default=None,ge=1)
    run_type: Literal['BASELINE','RETEST'] = 'BASELINE'
    parent_run_id: str | None = None
    change_id: str | None = None
    retrieval_config: RetrievalConfig | None = None
    verify_answers: bool = False
    scoring_profile_id: str | None = Field(default=None,min_length=1,max_length=128)

class ChangeInput(Input):
    baseline_run_id: str
    change_type: Literal['TOP_K_CHANGE','QUERY_REWRITE_TOGGLE','RERANK_TOGGLE','KNOWLEDGE_UPDATE','ANSWER_PROMPT_CHANGE']
    target_index_id: str | None = None
    after_config: RetrievalConfig
    reason: str = Field(min_length=1,max_length=3000)
    selected_case_ids: list[str] = Field(min_length=1)
    user_confirmed: Literal[True]

class RunTaskInput(RunInput):
    request_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')

class ComparisonInput(Input):
    baseline_run_id: str
    retest_run_id: str

class PreviewInput(Input):
    provider_session_id: str
    query: str = Field(min_length=1,max_length=5000)

class ReviewInput(Input):
    case_id: str
    human_final_status: Literal['PASS','FAIL','INVALID','EVIDENCE_INSUFFICIENT','NOT_APPLICABLE']
    human_reason: str = Field(min_length=1,max_length=5000)
    reviewer: str = Field(default='工作区用户',min_length=1,max_length=100)

@router.post('/knowledge-datasets')
def create_knowledge(body:KnowledgeInput):
    return execute(retrieval().knowledge.create,[d.model_dump() for d in body.documents],body.name,
                   body.knowledge_dataset_id,body.metadata)

@router.get('/knowledge-datasets/{identifier}')
def knowledge(identifier:str,version:int|None=Query(default=None,ge=1)):
    return execute(retrieval().store.get,'knowledge_datasets',identifier,version)

@router.post('/knowledge-datasets/{identifier}/index')
def index(identifier:str,body:IndexInput):
    return execute(retrieval().knowledge.build,identifier,body.version,body.chunk_config.model_dump() if body.chunk_config else None,body.embedding_model)

@router.get('/knowledge-indices/{identifier}')
def get_index(identifier:str): return execute(retrieval().store.get,'knowledge_indices',identifier)

@router.post('/retrieval-evalsets')
def create_evalset(body:EvalSetInput):
    return execute(retrieval().create_evalset,body.index_id,body.name,[c.model_dump() for c in body.cases],
        body.retrieval_eval_set_id,split_reviewed=body.split_reviewed)

@router.get('/retrieval-scoring-profiles')
def profiles():
    from .scoring_profiles import available_profiles
    return execute(available_profiles,retrieval().store)

@router.get('/retrieval-scoring-profiles/{identifier}')
def profile(identifier:str,provider_session_id:str):
    from .scoring_profiles import resolve_profile
    rag=retrieval()
    return execute(resolve_profile,rag.store,identifier,rag.providers.get(provider_session_id).configuration)

@router.get('/retrieval-evalsets/{identifier}')
def evalset(identifier:str,version:int|None=Query(default=None,ge=1)):
    return execute(retrieval().store.get,'retrieval_evalsets',identifier,version)

@router.post('/retrieval-runs')
async def run(body:RunInput):
    return await acquire(retrieval().run(**body.model_dump()))

@router.post('/retrieval-run-tasks',status_code=202)
async def submit_run(body:RunTaskInput,request:Request):
    from .retrieval_background import background
    registry=getattr(request.app.state,'workspaces',None)
    capacity=registry.expensive if registry else request.app.state.retrieval_slots
    return await acquire(background(retrieval()).submit(body.model_dump(),capacity))

@router.get('/retrieval-runs/{identifier}')
def get_run(identifier:str): return execute(retrieval().view,identifier)

@router.get('/retrieval-runs/{identifier}/export')
def export_run(identifier:str,format:Literal['csv']='csv'):
    from .retrieval_export import export_run as create_csv
    return csv_download(create_csv,identifier)

@router.post('/retrieval-changes')
def create_change(body:ChangeInput): return execute(retrieval().propose_change,**body.model_dump())

@router.post('/retrieval-changes/{identifier}/apply')
def apply(identifier:str): return execute(retrieval().apply,identifier)

@router.get('/retrieval-changes/{identifier}')
def get_change(identifier:str): return execute(retrieval().store.get,'retrieval_changes',identifier)

@router.post('/retrieval-comparisons')
def compare(body:ComparisonInput): return execute(retrieval().compare,body.baseline_run_id,body.retest_run_id)

@router.get('/retrieval-comparisons/{identifier}')
def get_comparison(identifier:str): return execute(retrieval().store.get,'retrieval_comparisons',identifier)

@router.get('/retrieval-comparisons/{identifier}/export')
def export_comparison(identifier:str,format:Literal['csv']='csv'):
    from .retrieval_export import export_comparison as create_csv
    return csv_download(create_csv,identifier)

@router.post('/retrieval-rewrite-preview')
async def preview(body:PreviewInput): return await acquire(retrieval().preview_rewrite(body.provider_session_id,body.query))

@router.post('/retrieval-runs/{identifier}/reviews')
def review(identifier:str,body:ReviewInput):
    return execute(retrieval().review,identifier,body.case_id,body.human_final_status,body.human_reason,body.reviewer)

@router.get('/retrieval-history')
def history():
    return [{'run_id':r.run_id,'run_type':r.run_type,'parent_run_id':r.parent_run_id,'status':r.status,
             'created_at':r.created_at,'name':r.controls['eval_set_snapshot']['name'],
             'retrieval_eval_set_id':r.controls['eval_set_snapshot']['retrieval_eval_set_id'],
             'version':r.controls['eval_set_snapshot']['version']}
            for r in sorted(retrieval().store.list('retrieval_runs'),key=lambda r:r.created_at)]

class HoldoutLockInput(Input):
    comparison_id: str
    reason: str = Field(min_length=1,max_length=5000)
    request_budget: int = Field(ge=1,le=500)

class HoldoutExecuteInput(Input):
    provider_session_id: str

def validations():
    from .retrieval_validation import RetrievalValidationService
    rag=retrieval()
    if not hasattr(rag,'validations'):rag.validations=RetrievalValidationService(rag)
    return rag.validations

@router.post('/retrieval-validations/lock')
def lock_holdout(body:HoldoutLockInput):
    value=execute(validations().lock,**body.model_dump())
    return validations().view(value.validation_id)

@router.get('/retrieval-validations')
def holdout_history(comparison_id:str):return execute(validations().history,comparison_id)

@router.get('/retrieval-validations/{identifier}')
def get_holdout(identifier:str):return execute(validations().view,identifier)

@router.post('/retrieval-validations/{identifier}/execute')
async def execute_holdout(identifier:str,body:HoldoutExecuteInput):
    return await acquire(validations().execute(identifier,body.provider_session_id))

@router.get('/retrieval-answer-prompt')
def answer_prompt():
    from .retrieval_runtime import ANSWER_PROMPT
    from .canonical import text_hash
    return {'prompt':ANSWER_PROMPT,'content_hash':text_hash(ANSWER_PROMPT),'version':'builtin-1'}

def scoring():
    from .judge_jobs import JudgeJobService
    rag=retrieval()
    if not hasattr(rag,'scoring_jobs'):rag.scoring_jobs=JudgeJobService(rag)
    return rag.scoring_jobs

class ScorePreviewInput(Input):
    case_ids: list[str] = Field(min_length=1,max_length=100)
    provider_session_id: str
    max_attempts: int = Field(default=2,ge=1,le=2,strict=True)

class ScoreJobInput(ScorePreviewInput):
    request_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
    protocol_hash: str
    request_budget: int = Field(ge=1,le=200,strict=True)
    token_budget: int = Field(ge=1,le=400000000,strict=True)

@router.get('/judge-contract')
def judge_contract():
    from .judge_contract import VERSION,json_schema
    return {'version':VERSION,'schema':json_schema(),'output_modes':['text','json_object','json_schema'],
        'mode_selection':'EXPLICIT_PROVIDER_CONFIGURATION','maximum_attempts':2}

@router.post('/retrieval-runs/{identifier}/scoring-preview')
def scoring_preview(identifier:str,body:ScorePreviewInput):
    return execute(scoring().preview,identifier,**body.model_dump())

@router.get('/retrieval-runs/{identifier}/scoring-jobs')
def scoring_history(identifier:str):return execute(scoring().history,identifier)

@router.post('/retrieval-runs/{identifier}/scoring-jobs')
async def create_scoring_job(identifier:str,body:ScoreJobInput):
    job=execute(scoring().create,identifier,**body.model_dump())
    await acquire(scoring().dispatch(job.job_id))
    return execute(scoring().view,job.job_id)

@router.get('/scoring-jobs/{identifier}')
def get_scoring_job(identifier:str):return execute(scoring().view,identifier)

@router.post('/scoring-jobs/{identifier}/resume')
async def resume_scoring_job(identifier:str):
    manager=scoring()
    view=execute(manager.view,identifier)
    if view['interrupted']:
        with manager.store.transaction():
            job=manager.store.get('score_jobs',identifier)
            manager.store.put('score_jobs',job.model_copy(update={'status':'PARTIAL'}))
    await acquire(manager.dispatch(identifier,resume=True))
    return execute(manager.view,identifier)

@router.get('/score-reports/{identifier}')
def get_score_report(identifier:str):return execute(scoring().report,identifier)

@router.get('/score-reports/{identifier}/export')
def export_score_report(identifier:str):
    from .retrieval_export import export_score_report as create_csv
    return csv_download(create_csv,identifier)

@router.get('/score-report-comparison')
def compare_score_reports(before_report_id:str,after_report_id:str):
    return execute(scoring().compare,before_report_id,after_report_id)

class GroupInput(Input):
    cases: list[RetrievalCase] = Field(min_length=1,max_length=100)

@router.post('/retrieval-case-groups')
def suggest_groups(body:GroupInput):
    from .retrieval_validation import same_case_family
    cases=body.cases; parents=list(range(len(cases)))
    def find(i):
        while parents[i]!=i:i=parents[i]
        return i
    for i,a in enumerate(cases):
        for j,b in enumerate(cases[:i]):
            if same_case_family(a,b):parents[find(i)]=find(j)
    rows=[c.model_copy(update={'group_id':cases[find(i)].group_id or 'family_'+str(find(i)+1)}).model_dump(mode='json') for i,c in enumerate(cases)]
    conflicts=sorted({r['group_id'] for r in rows if len({v['partition'] for v in rows if v['group_id']==r['group_id']})>1})
    return {'cases':rows,'conflicts':conflicts,'requires_human_confirmation':True}
