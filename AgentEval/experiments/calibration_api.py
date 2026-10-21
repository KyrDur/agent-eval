"""Explicit calibration routes never expose holdout machine results through generic reads."""
import re
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import Field
from .api import service, Input
from .providers import ProviderFailure
from .calibration_models import (CalibrationSample, Judgment, Source, IssueSource, IssueRepairPlan,
    IssueVerificationReport, IssueVerificationKind, IssueClosure, IssueEvidenceLevel)
from .calibration_service import CalibrationService
from evaluation.calibration import RUBRIC_TEMPLATE

router=APIRouter(prefix='/experiments/calibration',tags=['Evaluation Calibration'])

def calibration():
    exp=service()
    if not hasattr(exp,'calibration'): exp.calibration=CalibrationService(exp)
    return exp.calibration

def reject(error):
    if isinstance(error,FileNotFoundError) or isinstance(error,StopIteration): raise HTTPException(404,'CALIBRATION_RECORD_MISSING') from None
    if isinstance(error,ProviderFailure): raise HTTPException(409,error.code) from None
    code=str(error)
    raise HTTPException(409,code if re.fullmatch(r'[A-Z_]{3,100}',code) else 'CALIBRATION_INPUT_INVALID') from None

def invoke(fn,*args,**kwargs):
    try: return fn(*args,**kwargs)
    except (ValueError,TypeError,FileNotFoundError,StopIteration,ProviderFailure) as error: reject(error)

async def acquire(fn,**kwargs):
    try: return await fn(**kwargs)
    except (ValueError,TypeError,FileNotFoundError,ProviderFailure) as error: reject(error)

class RunSelection(Input):
    run_id: str
    case_id: str
    group_id: str = Field(min_length=1,max_length=200)
    partition: Literal['CALIBRATION','HOLDOUT']
    origin: Literal['ACTUAL','CONSTRUCTED','AI_GENERATED','UNKNOWN']
    scenario: str = Field(default='',max_length=100)
    summary: str = Field(default='',max_length=3000)
    diagnostic: bool = False
    source_viewer: str = Field(default='workspace-user',min_length=1,max_length=100)

class DatasetInput(Input):
    name: str = Field(min_length=1,max_length=200)
    samples: list[CalibrationSample] = Field(default_factory=list,max_length=100)
    selections: list[RunSelection] = Field(default_factory=list,max_length=100)
    group_review_confirmed: Literal[True]
    priority_metric: str = Field(min_length=1,max_length=2000)
    acceptable_cost: str = Field(min_length=1,max_length=2000)

class RubricInput(Input):
    definition: dict | None = None
    parent_rubric_id: str | None = None

class DerivedInput(Input):
    sample_id: str
    corrections: dict
    reason: str = Field(min_length=1,max_length=3000)
    cleaning_version: str = Field(min_length=1,max_length=200)
    semantic_mapping_version: str = Field(min_length=1,max_length=200)
    actor: str = Field(min_length=1,max_length=100)

class BlindInput(Input):
    dataset_id: str
    sample_id: str
    rubric_id: str
    annotator_id: str = Field(min_length=1,max_length=100)

class AnnotationInput(BlindInput):
    source: Source
    mode: Literal['BLIND','IMPORT']
    judgment: Judgment
    seen_machine: bool
    seen_peer: bool = False
    blind_access_id: str | None = None
    labeled_at: str | None = Field(default=None,max_length=100)

class AnnotationBatch(Input):
    annotations: list[AnnotationInput] = Field(min_length=1,max_length=200)

class AdjudicationInput(Input):
    dataset_id: str
    sample_id: str
    rubric_id: str
    annotation_ids: list[str] = Field(min_length=2,max_length=10)
    adjudicator_id: str = Field(min_length=1,max_length=100)
    source: Source
    judgment: Judgment
    reason: str = Field(min_length=1,max_length=3000)

class ProtocolInput(Input):
    dataset_id: str
    rubric_id: str
    provider_session_id: str
    name: str = Field(min_length=1,max_length=200)
    variant: Literal['J1','J2','J3']
    change_hypothesis: str = Field(min_length=1,max_length=3000)
    parent_protocol_id: str | None = None
    example_sample_ids: list[str] = Field(default_factory=list,max_length=8)
    prompt_addendum: str = Field(default='',max_length=6000)
    citation_mode: Literal['VERBATIM','FRAGMENT_IDS','SHORT_IDS'] = 'VERBATIM'

class RunInput(Input):
    dataset_id: str
    rubric_id: str
    protocol_id: str
    provider_session_id: str
    request_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
    repetitions: int = Field(default=1,ge=1,le=5,strict=True)
    budget: int = Field(ge=1,le=500,strict=True)

class ComparisonInput(Input):
    baseline_run_id: str
    candidate_run_id: str
    actor: str = Field(min_length=1,max_length=100)

class LockInput(Input):
    dataset_id: str
    rubric_id: str
    baseline_protocol_id: str
    candidate_protocol_id: str
    reason: str = Field(min_length=1,max_length=3000)
    repetitions: int = Field(default=1,ge=1,le=5,strict=True)
    request_budget: int = Field(ge=1,le=500,strict=True)
    actor: str = Field(min_length=1,max_length=100)

class ValidationInput(Input):
    baseline_session_id: str
    candidate_session_id: str
    actor: str = Field(min_length=1,max_length=100)

class ConclusionInput(Input):
    comparison_id: str
    decision: Literal['ADOPT','REVISE','KEEP_BASELINE']
    reason: str = Field(min_length=1,max_length=5000)
    actor: str = Field(min_length=1,max_length=100)
    validation_id: str | None = None

class HypothesisInput(Input):
    dataset_id: str
    sample_id: str
    run_id: str
    actor: str = Field(min_length=1,max_length=100)
    causes: list[str] = Field(min_length=1,max_length=7)
    reason: str = Field(min_length=1,max_length=3000)

class IssueInput(Input):
    dataset_id: str
    sample_id: str
    run_id: str
    actor: str = Field(min_length=1,max_length=100)
    title: str = Field(min_length=1,max_length=200)
    layer: Literal['DATA','PROMPT','RUBRIC','AGENT']
    owner: str = Field(min_length=1,max_length=100)
    description: str = Field(min_length=1,max_length=3000)
    source_type: IssueSource = 'CALIBRATION'
    source_id: str | None = None
    related_evidence: list[str] = Field(default_factory=list,max_length=30)
    possible_impact: str = Field(default='',max_length=2000)
    candidate_causes: list[str] = Field(default_factory=list,max_length=20)
    alternative_explanations: str = Field(default='',max_length=3000)
    next_check: str = Field(default='',max_length=3000)
    agent_component: Literal['UNKNOWN','KNOWLEDGE','RETRIEVAL','GENERATION','TOOL'] = 'UNKNOWN'
    repair_plan: IssueRepairPlan | None = None
    severity: Literal['CORE_TASK','CRITICAL','MINOR','UNKNOWN'] = 'UNKNOWN'
    observed_count: int | None = Field(default=None,ge=1)
    observed_denominator: int | None = Field(default=None,ge=1)
    sampling_source: str = Field(default='',max_length=1000)
    repair_cost: str = Field(default='',max_length=1000)

class IssueEventInput(Input):
    actor: str = Field(min_length=1,max_length=100)
    to_status: Literal['REPRODUCED','CHANGED','RETESTED','UNRESOLVED','CLOSED']
    previous_event_id: str | None = None
    note: str = Field(min_length=1,max_length=3000)
    change_summary: str = Field(default='',max_length=3000)
    verification_run_id: str | None = None
    outcome: Literal['FIXED','NOT_FIXED','INCONCLUSIVE'] | None = None
    candidate_causes: list[str] = Field(default_factory=list,max_length=20)
    confirmed_cause: str = Field(default='',max_length=2000)
    repair_plan: IssueRepairPlan | None = None
    verification_kind: IssueVerificationKind | None = None
    verification_sample_id: str | None = None
    verification_report: IssueVerificationReport | None = None
    closure_type: IssueClosure | None = None
    evidence_level: IssueEvidenceLevel = 'UNVERIFIED'

@router.get('/template')
def template(): return RUBRIC_TEMPLATE

@router.get('/history')
def history(): return invoke(calibration().history)

@router.post('/datasets')
def dataset(body:DatasetInput): return invoke(calibration().create_dataset,**body.model_dump())

@router.get('/datasets/{identifier}')
def dataset_view(identifier:str): return invoke(calibration().get_dataset,identifier)

@router.post('/datasets/{identifier}/derived-inputs')
def derived_input(identifier:str,body:DerivedInput):return invoke(calibration().derive_input,identifier,**body.model_dump())

@router.post('/rubrics')
def rubric(body:RubricInput): return invoke(calibration().create_rubric,**body.model_dump())

@router.post('/blind-sessions')
def blind(body:BlindInput): return invoke(calibration().open_blind,**body.model_dump())

@router.post('/annotations')
def annotation(body:AnnotationInput): return invoke(calibration().annotate,**body.model_dump())

@router.post('/annotation-imports')
def annotation_import(body:AnnotationBatch):
    # Append-only individual records; response identifies each successful import.
    results=[]
    for row in body.annotations:
        try:
            if row.mode!='IMPORT': raise ValueError('IMPORT_MODE_REQUIRED')
            record=calibration().annotate(**row.model_dump());results.append({'annotation_id':record.annotation_id,'status':'SAVED'})
        except (ValueError,TypeError,FileNotFoundError,StopIteration): results.append({'sample_id':row.sample_id,'status':'REJECTED'})
    return {'results':results}

@router.get('/annotations/{dataset_id}')
def annotations(dataset_id:str,rubric_id:str,actor:str):
    return invoke(calibration().annotation_view,dataset_id,rubric_id,actor)

@router.post('/adjudications')
def adjudication(body:AdjudicationInput): return invoke(calibration().adjudicate,**body.model_dump())

@router.post('/protocols')
def protocol(body:ProtocolInput): return invoke(calibration().create_protocol,**body.model_dump())

@router.post('/runs')
async def run(body:RunInput): return await acquire(calibration().run,**body.model_dump())

@router.get('/runs/{identifier}')
def run_view(identifier:str,actor:str): return invoke(calibration().run_view,identifier,actor)

@router.post('/comparisons')
def compare(body:ComparisonInput): return invoke(calibration().compare,**body.model_dump())

@router.get('/comparisons/{identifier}')
def comparison(identifier:str,actor:str): return invoke(calibration().comparison_view,identifier,actor)

@router.post('/validations/lock')
def lock(body:LockInput): return invoke(calibration().lock,**body.model_dump())

@router.post('/validations/{identifier}/execute')
async def validate(identifier:str,body:ValidationInput): return await acquire(calibration().validate,validation_id=identifier,**body.model_dump())

@router.post('/hypotheses')
def hypothesis(body:HypothesisInput): return invoke(calibration().hypothesis,**body.model_dump())

@router.post('/issues')
def create_issue(body:IssueInput): return invoke(calibration().create_issue,**body.model_dump())

@router.get('/issues')
def issues(actor:str,dataset_id:str|None=None,source_type:IssueSource|None=None,run_id:str|None=None):
    return invoke(calibration().issues_view,dataset_id,actor,source_type,run_id)

@router.get('/issue-sources/{run_id}')
def issue_source(run_id:str,case_id:str,actor:str,source_type:IssueSource='RETRIEVAL_RUN',source_id:str|None=None):
    return invoke(calibration().issue_source,run_id,case_id,actor,source_type,source_id)

@router.post('/issues/{identifier}/events')
def issue_event(identifier:str,body:IssueEventInput): return invoke(calibration().update_issue,identifier,**body.model_dump())

@router.post('/conclusions')
def conclude(body:ConclusionInput): return invoke(calibration().conclude,**body.model_dump())

@router.get('/conclusions/{identifier}/export')
def export(identifier:str,actor:str):
    conclusion=invoke(calibration().store.get,'calibration_conclusions',identifier)
    invoke(calibration().comparison_view,conclusion.comparison_id,actor)
    return invoke(calibration().export,identifier)
