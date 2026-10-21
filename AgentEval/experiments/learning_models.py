"""Learning records are learner work, never calibration HUMAN references."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .models import Artifact, uid

Cause = Literal['DATA', 'PROMPT', 'RUBRIC', 'AGENT', 'UNCERTAIN']

class EvidenceQuote(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    evidence_id: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=2, max_length=2000)

class LearningJudgment(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    judgment: str = Field(min_length=2, max_length=5000)
    evidence: list[EvidenceQuote] = Field(min_length=1, max_length=12)
    candidate_causes: list[Cause] = Field(min_length=1, max_length=5)
    uncertainty: str = Field(min_length=2, max_length=3000)
    distinguishing_check: str = Field(min_length=2, max_length=3000)
    source: Literal['SELF', 'AI_ASSISTED', 'EXTERNAL_HELP'] = 'SELF'

    @field_validator('judgment', 'uncertainty', 'distinguishing_check')
    @classmethod
    def substantive(cls, value):
        if len(value.strip()) < 2:
            raise ValueError('LEARNING_INPUT_INVALID')
        return value.strip()

class LearningAttempt(Artifact):
    schema_version: str = 'learning-1'
    attempt_id: str = Field(default_factory=uid)
    request_id: str
    request_hash: str
    pack_id: str
    pack_version: str
    case_id: str
    family_id: str
    mode: Literal['TRAINING', 'FREE']
    source_kind: Literal['CONSTRUCTED_TEACHING_REPLAY'] = 'CONSTRUCTED_TEACHING_REPLAY'

class LearningEvent(Artifact):
    schema_version: str = 'learning-1'
    event_id: str = Field(default_factory=uid)
    attempt_id: str
    sequence: int = Field(ge=1)
    request_id: str
    request_hash: str
    name: str
    payload: dict = Field(default_factory=dict)

class LearningReview(Artifact):
    """Imported by a local maintainer, separate from calibration annotations."""
    schema_version: str = 'learning-1'
    review_id: str = Field(default_factory=uid)
    attempt_id: str
    transfer_event_id: str
    reviewer: str = Field(min_length=1, max_length=200)
    independent_human_attested: Literal[True]
    outcome: Literal['MEETS_CRITERIA', 'NOT_YET']
    checks: dict[Literal['evidence_relevant', 'hypotheses_reasonable', 'check_distinguishes_causes', 'limits_recognized'], bool]
    reason: str = Field(min_length=2, max_length=5000)
    reference_kind: Literal['LEARNING_OBSERVATION_NOT_CALIBRATION_GOLD'] = 'LEARNING_OBSERVATION_NOT_CALIBRATION_GOLD'
