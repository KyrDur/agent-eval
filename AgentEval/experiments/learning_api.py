"""No-Key learning replay. Reference answers are gated on server progress."""
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator
from .api import Input, service
from .learning_models import LearningJudgment
from .learning_service import LearningService, LearningError

router=APIRouter(prefix='/experiments/learning',tags=['Agent Eval Learning'])

def learning():
    return LearningService(service())

def run(fn,*args,**kwargs):
    try:
        return fn(*args,**kwargs)
    except LearningError as error:
        raise HTTPException(409,str(error)) from None
    except FileNotFoundError:
        raise HTTPException(404,'Artifact not found') from None

class Request(Input):
    request_id: str = Field(pattern=r'^[A-Za-z0-9_-]{8,100}$')

class Start(Request):
    case_id: str
    mode: Literal['TRAINING','FREE']='TRAINING'

class Judgment(Request, LearningJudgment):
    pass

class Hint(Request):
    level: int = Field(ge=1,le=3,strict=True)

class Prediction(Request):
    choice: Literal['APPLY','KEEP']
    expected_result: str = Field(min_length=2,max_length=3000)
    potential_cost: str = Field(min_length=2,max_length=3000)
    reason: str = Field(min_length=2,max_length=3000)

class Decision(Request):
    decision: Literal['ADOPT','DECLINE','KEEP','CONTINUE_OBSERVING']
    reason: str = Field(min_length=2,max_length=3000)
    limitations: str = Field(min_length=2,max_length=3000)

class Feedback(Request):
    helpful: Literal['YES','PARTLY','NO']
    note: str = Field(default='',max_length=3000)

class Exit(Request):
    reason: Literal['TIME','DIFFICULT','NOT_RELEVANT','TECHNICAL','OTHER']
    note: str = Field(default='',max_length=3000)

@router.get('/pack')
def pack(): return learning().catalog()

@router.get('/attempts')
def attempts(): return learning().history()

@router.get('/summary')
def summary(): return learning().summary()

@router.post('/attempts')
def start(body:Start): return run(learning().start,**body.model_dump())

@router.get('/attempts/{identifier}')
def attempt(identifier:str): return run(learning().view,identifier)

@router.get('/attempts/{identifier}/export')
def export(identifier:str): return run(learning().export,identifier)

def mutate(identifier, action, body):
    payload=body.model_dump(exclude={'request_id'})
    # Blank required user prose must not be counted as a completed learning step.
    if any(isinstance(v,str) and len(v.strip())<2 for k,v in payload.items() if k in {'expected_result','potential_cost','reason','limitations'}):
        raise HTTPException(422,'LEARNING_INPUT_INVALID')
    return run(learning().mutate,identifier,action,payload,body.request_id)

@router.post('/attempts/{identifier}/initial')
def initial(identifier:str,body:Judgment): return mutate(identifier,'initial',body)

@router.post('/attempts/{identifier}/revision')
def revision(identifier:str,body:Judgment): return mutate(identifier,'revision',body)

@router.post('/attempts/{identifier}/hint')
def hint(identifier:str,body:Hint): return mutate(identifier,'hint',body)

@router.post('/attempts/{identifier}/prediction')
def prediction(identifier:str,body:Prediction): return mutate(identifier,'prediction',body)

@router.post('/attempts/{identifier}/replay')
def replay(identifier:str,body:Request): return mutate(identifier,'replay',body)

@router.post('/attempts/{identifier}/decision')
def decision(identifier:str,body:Decision): return mutate(identifier,'decision',body)

@router.post('/attempts/{identifier}/transfer-start')
def transfer_start(identifier:str,body:Request): return mutate(identifier,'transfer-start',body)

@router.post('/attempts/{identifier}/transfer-submit')
def transfer_submit(identifier:str,body:Judgment): return mutate(identifier,'transfer-submit',body)

@router.post('/attempts/{identifier}/transfer-feedback')
def transfer_feedback(identifier:str,body:Request): return mutate(identifier,'transfer-feedback',body)

@router.post('/attempts/{identifier}/feedback')
def feedback(identifier:str,body:Feedback): return mutate(identifier,'feedback',body)

@router.post('/attempts/{identifier}/exit')
def exit(identifier:str,body:Exit): return mutate(identifier,'exit',body)

@router.post('/attempts/{identifier}/technical-failure')
def failure(identifier:str,body:Exit): return mutate(identifier,'technical-failure',body)
