"""Voluntary external advice is evidence of a suggestion, never a quality verdict."""
from typing import Literal
from pydantic import Field
from .models import Artifact,uid

class ExternalSuggestion(Artifact):
    suggestion_id:str=Field(default_factory=uid)
    run_id:str
    source:Literal['EXTERNAL_AI_UNVERIFIED']='EXTERNAL_AI_UNVERIFIED'
    status:Literal['PENDING_VERIFICATION']='PENDING_VERIFICATION'
    stage:Literal['case','plan','comparison','resume','interview','retrospective']
    text:str=Field(min_length=1,max_length=8000)
