"""Append-only calibration records. No Agent generation and no legacy score writes."""
from typing import Literal
from pydantic import Field, model_validator, field_validator, model_serializer
from .models import Artifact, uid
from .retrieval_models import InputModel
from .providers import ProviderConfig

DIMENSIONS = ('faithfulness', 'conditions', 'relevance', 'actionability')
Score = Literal[0, 1, 2, 'INSUFFICIENT', 'NA']
Verdict = Literal['PASS', 'FAIL', 'PENDING']
Source = Literal['HUMAN', 'AI', 'CODEX']
CAUSES = ('RUBRIC_AMBIGUOUS', 'REFERENCE_ERROR', 'MISSED_CONDITION', 'UNSUPPORTED_INFERENCE',
          'REASONABLE_REFUSAL', 'VERBOSITY_PREFERENCE', 'CONTEXT_MISREAD')

class Evidence(InputModel):
    evidence_id: str = Field(min_length=1, max_length=200)
    document_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=200000)
    title: str = Field(default='', max_length=200)

class CalibrationSample(InputModel):
    sample_id: str = Field(default_factory=uid)
    group_id: str = Field(min_length=1, max_length=200)
    template_id: str | None = None
    partition: Literal['CALIBRATION', 'HOLDOUT']
    question: str = Field(min_length=1, max_length=5000)
    context: list[dict] = Field(default_factory=list, max_length=20)
    answer: str = Field(min_length=1, max_length=20000)
    retrieved_evidence: list[Evidence] = Field(default_factory=list, max_length=100)
    reference_policy: list[Evidence] = Field(default_factory=list, max_length=100)
    reference_complete: bool = False
    expected_facts: list[str] = Field(default_factory=list, max_length=50)
    scenario: str = Field(default='单事实', min_length=1, max_length=100)
    origin: Literal['ACTUAL', 'CONSTRUCTED', 'AI_GENERATED', 'UNKNOWN']
    diagnostic: bool = False
    source_run_id: str | None = None
    source_case_id: str | None = None
    summary: str = Field(default='', max_length=3000)
    prior_machine_exposure: bool = False
    machine_exposed_actors: list[str] = Field(default_factory=list,max_length=20)
    creator_seen_content: bool = True
    provenance: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def valid_content(self):
        if not self.answer.strip() or not self.question.strip(): raise ValueError('Empty frozen content')
        if self.reference_complete and not self.reference_policy: raise ValueError('Missing reference policy')
        for sources in (self.retrieved_evidence, self.reference_policy):
            ids = [e.evidence_id for e in sources]
            if len(ids) != len(set(ids)): raise ValueError('Duplicate evidence ID in scope')
        if any(set(m) != {'role','content'} or m['role'] not in {'user','assistant'}
               or not isinstance(m['content'], str) for m in self.context):
            raise ValueError('Invalid context')
        if sum(len(m['content']) for m in self.context) > 50000: raise ValueError('Context too large')
        if sum(len(e.text) for e in self.retrieved_evidence+self.reference_policy)>500000:
            raise ValueError('CALIBRATION_INPUT_TOO_LARGE')
        return self

class CalibrationDataset(Artifact):
    dataset_id: str = Field(default_factory=uid)
    name: str = Field(min_length=1, max_length=200)
    samples: list[CalibrationSample] = Field(min_length=1, max_length=100)
    content_hash: str
    group_review_confirmed: Literal[True]
    priority_metric: str = Field(min_length=1, max_length=2000)
    acceptable_cost: str = Field(min_length=1, max_length=2000)
    isolation: Literal['WORKFLOW_ONLY'] = 'WORKFLOW_ONLY'

class RubricVersion(Artifact):
    rubric_id: str = Field(default_factory=uid)
    parent_rubric_id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    dimensions: dict
    critical_errors: dict[str, str]
    applicable_scope: str = Field(min_length=1, max_length=3000)
    rules: dict
    content_hash: str
    status: Literal['INITIAL_UNVALIDATED'] = 'INITIAL_UNVALIDATED'

class Citation(InputModel):
    scope: Literal['RETRIEVED', 'REFERENCE']
    evidence_id: str
    quote: str = Field(min_length=1, max_length=3000)

class DimensionJudgment(InputModel):
    score: Score
    answer_quotes: list[str] = Field(default_factory=list, max_length=10)
    citations: list[Citation] = Field(default_factory=list, max_length=20)
    reason: str = Field(min_length=1, max_length=3000)

    @field_validator('score', mode='before')
    @classmethod
    def score_type(cls,value):
        if type(value) is not int and value not in ('INSUFFICIENT','NA'): raise ValueError('Invalid score type')
        return value

class Judgment(InputModel):
    dimensions: dict[str, DimensionJudgment]
    critical_errors: list[str] = Field(default_factory=list, max_length=20)
    error_tags: list[str] = Field(default_factory=list, max_length=20)
    verdict: Verdict
    task_resolved: Literal['YES', 'NO', 'INSUFFICIENT']
    faithful_to_available: Literal['YES', 'NO', 'INSUFFICIENT']
    task_failure_reasons: list[str] = Field(default_factory=list, max_length=20)
    insufficient_items: list[str] = Field(default_factory=list, max_length=20)
    reason: str = Field(min_length=1, max_length=3000)

    @model_validator(mode='after')
    def complete_dimensions(self):
        if set(self.dimensions) != set(DIMENSIONS): raise ValueError('Four dimensions required')
        if any(isinstance(d.score, bool) for d in self.dimensions.values()): raise ValueError('Boolean score')
        return self

class CalibrationAccess(Artifact):
    access_id: str = Field(default_factory=uid)
    dataset_id: str
    sample_ids: list[str] = Field(default_factory=list)
    actor: str
    kind: Literal['BLIND_OPEN', 'MACHINE_VIEW', 'ANNOTATION_VIEW', 'HOLDOUT_RELEASE', 'HOLDOUT_INVALIDATED']
    details: dict = Field(default_factory=dict)

class Annotation(Artifact):
    annotation_id: str = Field(default_factory=uid)
    dataset_id: str
    sample_id: str
    rubric_id: str
    annotator_id: str = Field(min_length=1, max_length=100)
    source: Source
    mode: Literal['BLIND', 'IMPORT']
    blind_access_id: str | None = None
    seen_machine: bool
    seen_peer: bool = False
    independent: bool
    labeled_at: str
    judgment: Judgment

class Adjudication(Artifact):
    adjudication_id: str = Field(default_factory=uid)
    dataset_id: str
    sample_id: str
    rubric_id: str
    annotation_ids: list[str] = Field(min_length=2)
    adjudicator_id: str = Field(min_length=1, max_length=100)
    source: Source
    judgment: Judgment
    reason: str = Field(min_length=1, max_length=3000)

class JudgeProtocolVersion(Artifact):
    protocol_id: str = Field(default_factory=uid)
    dataset_id: str
    rubric_id: str
    name: str = Field(min_length=1, max_length=200)
    variant: Literal['J1', 'J2', 'J3']
    parent_protocol_id: str | None = None
    change_hypothesis: str = Field(min_length=1, max_length=3000)
    declared_changes: list[str] = Field(default_factory=list)
    provider_configuration: ProviderConfig
    prompt: str
    examples: list[dict] = Field(default_factory=list, max_length=8)
    evidence_input: Literal['FROZEN_DUAL_SCOPE_V1', 'FROZEN_FRAGMENT_CATALOG_V2','FROZEN_FRAGMENT_ALIASES_V1'] = 'FROZEN_DUAL_SCOPE_V1'
    output_schema: Literal['CALIBRATION_JUDGMENT_V1', 'CALIBRATION_FRAGMENT_JUDGMENT_V2','EXACT_FRAGMENT_ALIASES_V1'] = 'CALIBRATION_JUDGMENT_V1'
    parser_version: Literal['1', '2','3'] = '1'
    evidence_contract_version: str | None = None
    wire_contract_version: str | None = None
    scoring_components: dict | None = None

    @model_serializer(mode='wrap')
    def preserve_old_engine_shape(self,handler):
        data=handler(self)
        if 'evidence_contract_version' not in self.model_fields_set:data.pop('evidence_contract_version',None)
        for key in ('wire_contract_version','scoring_components'):
            if key not in self.model_fields_set:data.pop(key,None)
        return data
    content_hash: str

    @model_validator(mode='after')
    def consistent_citation_version(self):
        if (self.evidence_input,self.output_schema,self.parser_version) not in {
            ('FROZEN_DUAL_SCOPE_V1','CALIBRATION_JUDGMENT_V1','1'),
            ('FROZEN_FRAGMENT_CATALOG_V2','CALIBRATION_FRAGMENT_JUDGMENT_V2','2'),
            ('FROZEN_FRAGMENT_ALIASES_V1','EXACT_FRAGMENT_ALIASES_V1','3')}:
            raise ValueError('Inconsistent citation protocol version')
        return self

class CalibrationResult(InputModel):
    sample_id: str
    repetition: int
    status: Literal['SUCCESS', 'INTERFACE_ERROR', 'PARSE_ERROR', 'CONTENT_INVALID', 'NOT_RUN']
    judgment: Judgment | None = None
    error: str | None = None
    raw_output: str | None = None
    citation_provenance: list[dict] = Field(default_factory=list)
    request_count: int = 0
    usage: dict | None = None
    latency_ms: float = 0
    validation_issues: list[dict] = Field(default_factory=list)
    output_mode: str | None = None
    stop_reason: str | None = None
    provider_finish_reason: str | None = None
    wire_contract_version: str | None = None

    @model_serializer(mode='wrap')
    def preserve_historical_fields(self,handler):
        data=handler(self)
        for name in ('validation_issues','output_mode','stop_reason','provider_finish_reason','wire_contract_version'):
            if name not in self.model_fields_set:data.pop(name,None)
        return data

class CalibrationRun(Artifact):
    run_id: str = Field(default_factory=uid)
    request_id: str
    request_hash: str
    dataset_id: str
    rubric_id: str
    protocol_id: str
    partition: Literal['CALIBRATION', 'HOLDOUT']
    validation_id: str | None = None
    status: Literal['RUNNING', 'COMPLETE', 'PARTIAL', 'FAILED'] = 'RUNNING'
    finished_at: str | None = None
    repetitions: int = Field(ge=1, le=5)
    budget: int = Field(ge=1, le=500)
    dataset_hash: str
    sample_snapshot: list[CalibrationSample]
    rubric_snapshot: RubricVersion
    protocol_snapshot: JudgeProtocolVersion
    reference_snapshot: dict
    results: list[CalibrationResult] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    provider_observations: list[dict] = Field(default_factory=list)
    request_count: int = 0
    elapsed_ms: float = 0
    warnings: list[str] = Field(default_factory=list)

class CalibrationComparison(Artifact):
    comparison_id: str = Field(default_factory=uid)
    dataset_id: str
    baseline_run_id: str
    candidate_run_id: str
    comparable: bool
    reasons: list[str]
    protocol_differences: list[dict]
    single_component_change: bool
    attributable: Literal[False] = False
    reference_snapshot: dict
    metrics_before: dict
    metrics_after: dict
    pairs: list[dict]

class CalibrationValidation(Artifact):
    validation_id: str = Field(default_factory=uid)
    dataset_id: str
    rubric_id: str
    baseline_protocol_id: str
    candidate_protocol_id: str
    reason: str = Field(min_length=1, max_length=3000)
    reference_snapshot: dict
    repetitions: int = Field(ge=1, le=5)
    request_budget: int = Field(ge=1, le=500)
    status: Literal['LOCKED', 'RUNNING', 'COMPLETE', 'FAILED'] = 'LOCKED'
    run_ids: list[str] = Field(default_factory=list)
    comparison_id: str | None = None
    released_at: str | None = None

class CalibrationConclusion(Artifact):
    conclusion_id: str = Field(default_factory=uid)
    dataset_id: str
    comparison_id: str
    validation_id: str | None = None
    decision: Literal['ADOPT', 'REVISE', 'KEEP_BASELINE']
    reason: str = Field(min_length=1, max_length=5000)
    research_status: Literal['PENDING', 'COMPLETED_WITH_SINGLE_ANNOTATOR', 'COMPLETED_WITH_ADJUDICATED_REFERENCE']
    report_snapshot: dict

class CalibrationHypothesis(Artifact):
    hypothesis_id: str = Field(default_factory=uid)
    dataset_id: str
    sample_id: str
    run_id: str
    actor: str
    causes: list[str] = Field(min_length=1, max_length=7)
    reason: str = Field(min_length=1, max_length=3000)
    status: Literal['HYPOTHESIS_ONLY'] = 'HYPOTHESIS_ONLY'


IssueStatus = Literal['OPEN', 'REPRODUCED', 'CHANGED', 'RETESTED', 'UNRESOLVED', 'CLOSED']
IssueSource = Literal['CALIBRATION', 'RETRIEVAL_RUN', 'RETRIEVAL_COMPARISON', 'RETRIEVAL_REVIEW']
IssueVerificationKind = Literal['CALIBRATION', 'DATA_REPLAY', 'RUBRIC_STUDY', 'RETRIEVAL']
IssueClosure = Literal['FIXED', 'FALSE_ALARM', 'DEFERRED']
IssueEvidenceLevel = Literal['UNVERIFIED', 'SAME_CASE', 'REGRESSION', 'UNSEEN']


class IssueRepairPlan(InputModel):
    success_criteria: str = Field(min_length=1, max_length=3000)
    target_error: str = Field(min_length=1, max_length=2000)
    potential_regressions: str = Field(min_length=1, max_length=2000)
    validation_scope: str = Field(min_length=1, max_length=2000)
    verification_sample_ids: list[str] = Field(min_length=1, max_length=100)
    expected_verdict: Literal['PASS', 'FAIL'] | None = None

    @model_validator(mode='after')
    def meaningful_plan(self):
        if any(not getattr(self, key).strip() for key in ('success_criteria','target_error','potential_regressions','validation_scope')):
            raise ValueError('ISSUE_PLAN_REQUIRED')
        if len(set(self.verification_sample_ids)) != len(self.verification_sample_ids):
            raise ValueError('ISSUE_PLAN_REQUIRED')
        return self


class IssueVerificationReport(InputModel):
    target_eliminated: bool
    regression_checked: bool
    regression_found: bool | None = None
    regression_result: str = Field(min_length=1, max_length=3000)
    validation_scope: str = Field(min_length=1, max_length=2000)
    unexcluded_factors: list[str] = Field(default_factory=list, max_length=20)
    regression_sample_ids: list[str] = Field(default_factory=list, max_length=100)
    unseen_sample_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def meaningful_report(self):
        if not self.regression_result.strip() or not self.validation_scope.strip():
            raise ValueError('ISSUE_ACCEPTANCE_REQUIRED')
        if self.regression_checked and self.regression_found is None:
            raise ValueError('ISSUE_ACCEPTANCE_REQUIRED')
        return self


class CalibrationIssue(Artifact):
    issue_id: str = Field(default_factory=uid)
    dataset_id: str
    sample_id: str
    run_id: str
    rubric_id: str
    actor: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    layer: Literal['DATA', 'PROMPT', 'RUBRIC', 'AGENT']
    owner: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=3000)
    source_type: IssueSource = 'CALIBRATION'
    source_id: str | None = None
    related_evidence: list[str] = Field(default_factory=list, max_length=30)
    possible_impact: str = Field(default='', max_length=2000)
    candidate_causes: list[str] = Field(default_factory=list, max_length=20)
    alternative_explanations: str = Field(default='', max_length=3000)
    next_check: str = Field(default='', max_length=3000)
    agent_component: Literal['UNKNOWN', 'KNOWLEDGE', 'RETRIEVAL', 'GENERATION', 'TOOL'] = 'UNKNOWN'
    repair_plan: IssueRepairPlan | None = None
    baseline_snapshot: dict = Field(default_factory=dict)
    severity: Literal['CORE_TASK', 'CRITICAL', 'MINOR', 'UNKNOWN'] = 'UNKNOWN'
    observed_count: int | None = Field(default=None, ge=1)
    observed_denominator: int | None = Field(default=None, ge=1)
    sampling_source: str = Field(default='', max_length=1000)
    repair_cost: str = Field(default='', max_length=1000)
    status: Literal['OPEN'] = 'OPEN'


class CalibrationIssueEvent(Artifact):
    event_id: str = Field(default_factory=uid)
    issue_id: str
    actor: str = Field(min_length=1, max_length=100)
    previous_event_id: str | None = None
    from_status: IssueStatus
    to_status: IssueStatus
    note: str = Field(min_length=1, max_length=3000)
    change_summary: str = Field(default='', max_length=3000)
    verification_run_id: str | None = None
    outcome: Literal['FIXED', 'NOT_FIXED', 'INCONCLUSIVE'] | None = None
    candidate_causes: list[str] = Field(default_factory=list, max_length=20)
    confirmed_cause: str = Field(default='', max_length=2000)
    repair_plan: IssueRepairPlan | None = None
    verification_kind: IssueVerificationKind | None = None
    verification_sample_id: str | None = None
    verification_report: IssueVerificationReport | None = None
    verification_snapshot: dict = Field(default_factory=dict)
    closure_type: IssueClosure | None = None
    evidence_level: IssueEvidenceLevel = 'UNVERIFIED'
