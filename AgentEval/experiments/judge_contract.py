"""Judge wire contract. Short selectors are resolved only after strict validation."""
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from .calibration_models import Score

VERSION = 'JUDGE_WIRE_V2'

class WireModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class WireDimension(WireModel):
    score: Score
    answer_fragment_ids: list[str] = Field(max_length=10)
    evidence_fragment_ids: list[str] = Field(max_length=20)
    reason: str = Field(min_length=1, max_length=3000)

    @field_validator('score', mode='before')
    @classmethod
    def strict_score(cls, value):
        if not (type(value) is int and value in (0, 1, 2)) and not (type(value) is str and value in ('NA', 'INSUFFICIENT')):
            raise ValueError('Expected 0, 1, 2, "NA", or "INSUFFICIENT"')
        return value

class WireDimensions(WireModel):
    faithfulness: WireDimension
    conditions: WireDimension
    relevance: WireDimension
    actionability: WireDimension

class BusinessAssessment(WireModel):
    task_outcome: Literal['COMPLETED','UNRESOLVED','WAITING_CLARIFICATION','UNKNOWN']
    current_turn_behavior: Literal['ANSWERED','CLARIFIED','REFUSED_OR_ESCALATED','INCORRECT','UNKNOWN']

class WireJudgment(WireModel):
    dimensions: WireDimensions
    critical_errors: list[str] = Field(max_length=20)
    error_tags: list[str] = Field(max_length=20)
    task_resolved: Literal['YES','NO','INSUFFICIENT']
    faithful_to_available: Literal['YES','NO','INSUFFICIENT']
    task_failure_reasons: list[str] = Field(max_length=20)
    insufficient_items: list[str] = Field(max_length=20)
    reason: str = Field(min_length=1, max_length=3000)
    business_assessment: BusinessAssessment | None = None

def issue(stage, code, field_path='$', expected=None, actual=None, retryable=False):
    return dict(stage=stage, code=code, field_path=field_path, expected=expected,
                actual=actual, retryable=retryable)

class JudgeValidationError(ValueError):
    def __init__(self, issues):
        self.issues = issues
        super().__init__(issues[0]['code'] if issues else 'JUDGMENT_SCHEMA_INVALID')

def validate_wire(raw):
    try:
        return WireJudgment.model_validate(raw).model_dump(exclude_none=True)
    except ValidationError as error:
        issues = []
        for e in error.errors(include_url=False, include_context=False):
            path = '.'.join(map(str, e['loc'])) or '$'
            score = path.endswith('.score')
            issues.append(issue('SCHEMA', 'JUDGMENT_SCHEMA_INVALID', path,
                '0 | 1 | 2 | "NA" | "INSUFFICIENT"' if score else e['msg'],
                e.get('input'), True))
        raise JudgeValidationError(issues) from None

def json_schema():
    schema = WireJudgment.model_json_schema()
    # Strict structured-output providers require every property to be required.
    # Optional business_assessment is nullable, while dimension scores never are.
    schema['required'] = list(schema['properties'])
    return schema

def response_format(mode):
    if mode == 'text': return None
    if mode == 'json_object': return {'type':'json_object'}
    if mode == 'json_schema':
        return {'type':'json_schema','json_schema':{'name':'agent_eval_judgment_v2','strict':True,'schema':json_schema()}}
    raise ValueError('FORMAT_MODE_UNSUPPORTED')

EXAMPLE = {
    'dimensions':{name:{'score':'NA' if name=='actionability' else 2,
        'answer_fragment_ids':[] if name=='actionability' else ['A1'],
        'evidence_fragment_ids':[] if name=='actionability' else ['R1' if name=='faithfulness' else 'P1'],
        'reason':'规格事实题没有行动需求，Rubric 允许此维 NA。' if name=='actionability' else '回答原文与所选规格证据一致。'}
        for name in ('faithfulness','conditions','relevance','actionability')},
    'critical_errors':[],'error_tags':[],'task_resolved':'YES','faithful_to_available':'YES',
    'task_failure_reasons':[],'insufficient_items':[],'reason':'桌面材质与承重均与规格一致。'}

PROMPT_SUFFIX = '''
JUDGE_WIRE_V2：四维 score 仅允许整数 0、1、2 或字符串 "NA"、"INSUFFICIENT"。不适用必须显式写 "NA"，证据不足写 "INSUFFICIENT"；禁止 null、布尔值、字符串数字、漏维度。NA 仍须符合本题冻结 Rubric。
以下为规格事实题的完整格式示例（仅说明格式，引用必须改为本题编号）：
''' + json.dumps(EXAMPLE, ensure_ascii=False)
