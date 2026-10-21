"""Versioned data-plane and inference job contracts. Credentials never persist."""
from typing import Literal
from pydantic import Field, model_serializer
from .models import Artifact, uid

class DomainVersion(Artifact):
    profile_id: str = Field(default_factory=uid)
    domain_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    version: int = Field(ge=1)
    name: str = Field(min_length=1,max_length=200)
    business_scope: str = Field(min_length=1,max_length=5000)
    template_id: Literal['POLICY_RAG','MISSING_KNOWLEDGE','CLARIFICATION'] = 'POLICY_RAG'
    agent_kind: Literal['RAG','TOOL_TRACE'] = 'RAG'
    judge_prompt: str = Field(min_length=1,max_length=24000)
    rules: dict = Field(default_factory=dict)
    rubric: dict
    max_attempts: int = Field(default=2,ge=1,le=5)
    content_hash: str
    evidence_contract_version: str = 'EVIDENCE_CONTRACT_V2'
    wire_contract_version: str | None = None
    scoring_components: dict | None = None

    @model_serializer(mode='wrap')
    def preserve_old_wire_protocol(self,handler):
        data=handler(self)
        for key in ('wire_contract_version','scoring_components'):
            if key not in self.model_fields_set:data.pop(key,None)
        return data

class EvidenceBatch(Artifact):
    batch_id: str = Field(default_factory=uid)
    parent_batch_id: str | None = None
    domain_id: str
    profile_id: str
    name: str = Field(min_length=1,max_length=200)
    raw_records: list[dict]
    records: list[dict]
    mapping: dict
    processing: dict
    confirmed_by: str = Field(min_length=1,max_length=100)
    confirmation_reason: str = Field(min_length=1,max_length=3000)
    content_hash: str

class InferenceJob(Artifact):
    job_id: str = Field(default_factory=uid)
    domain_id: str
    batch_id: str
    profile_id: str
    request_id: str
    provider_session_id: str
    provider_configuration: dict
    rule_snapshot: dict
    expected_ids: list[str]
    status: Literal['QUEUED','RUNNING','COMPLETE','PARTIAL','FAILED','CANCEL_REQUESTED','CANCELLED','WAITING_CREDENTIALS'] = 'QUEUED'
    started_at: str | None = None
    finished_at: str | None = None
    attempt: int = 0
    last_error: str | None = None
    window: dict = Field(default_factory=dict)
    resumed_from_job_id: str | None = None
    uncertain_delivery_attempts: list[int] = Field(default_factory=list)

class InferenceEvent(Artifact):
    event_id: str = Field(default_factory=uid)
    job_id: str
    domain_id: str
    sample_id: str
    attempt: int
    status: str
    evaluation_state: str
    judgment: dict | None = None
    input_package: dict | None = None
    reason: str = ''
    request_count: int = 0
    provider_call_traces: list[dict] = Field(default_factory=list)
    elapsed_ms: float = 0
    tool_checks: list[dict] = Field(default_factory=list)

class OperationsReview(Artifact):
    review_id: str = Field(default_factory=uid)
    job_id: str
    sample_id: str
    evaluation_state: Literal['PASS','FAIL','EVIDENCE_INSUFFICIENT','NOT_APPLICABLE']
    reason: str = Field(min_length=1,max_length=5000)
    actor: str = Field(min_length=1,max_length=100)
    revision: int
    machine_exposed: bool = True

class SamplingPlan(Artifact):
    plan_id: str = Field(default_factory=uid)
    job_id: str
    seed: str
    random_count: int
    source_count: int
    selections: list[dict]
    protocol: str = 'RANDOM_PLUS_ALL_FAILURE_ABSTENTION_AND_HUMAN_DISAGREEMENT_V1'

class DailyPlan(Artifact):
    plan_id: str = Field(default_factory=uid)
    domain_id: str
    batch_id: str
    provider_session_id: str
    name: str = Field(min_length=1,max_length=200)
    timezone: str
    hour: int = Field(ge=0,le=23)
    minute: int = Field(default=0,ge=0,le=59)
    enabled: bool = True
    late_policy: Literal['NEXT_WINDOW','REQUIRE_REVISED_BATCH'] = 'REQUIRE_REVISED_BATCH'
    revision: int = 1
    replaces_plan_id: str | None = None
