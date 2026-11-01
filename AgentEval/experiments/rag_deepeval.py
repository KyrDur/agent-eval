"""Bounded optional metric observations; original judge results are immutable."""
import asyncio,json,os
from pathlib import Path
from pydantic import Field
from .models import Artifact,uid,now
from .canonical import digest,text_hash

class MetricBatch(Artifact):
    batch_id:str=Field(default_factory=uid)
    request_id:str
    input_hash:str
    parent_run_id:str
    frozen_input:dict
    status:str='RUNNING'
    result:dict|None=None
    error:str|None=None
    finished_at:str|None=None

async def evaluate(rag,run_id,case_ids,sid,request_id,request_limit):
    from .rag_lab import export_deepeval
    exported=export_deepeval(rag,run_id);rows=[r for r in exported['test_cases'] if r['case_id'] in case_ids]
    if not rows or set(case_ids)!={r['case_id'] for r in rows}:raise ValueError('ACQUIRED_DEBUG_CASE_REQUIRED')
    session=rag.providers.get(sid)
    if session.text_connection_status!='READY':raise ValueError('PROVIDER_NOT_READY')
    configuration=session.configuration.model_dump()
    # Explicitly choose this session's text model as sidecar judge.
    configuration={**configuration,'model':session.configuration.resolved()['judge']['model'],'temperature':session.configuration.resolved()['judge']['temperature'],'max_tokens':session.configuration.resolved()['judge']['max_tokens']}
    if session.configuration.judge_provider_configuration:
        configuration=session.configuration.judge_provider_configuration
        credential=rag.providers.judge_credential(sid)
    else:credential=rag.providers.credential(sid)
    request_limit=min(request_limit,configuration.get('max_calls',request_limit))
    executable=os.environ.get('AGENTEVAL_DEEPEVAL_PYTHON',str(Path(__file__).resolve().parents[2]/'.venv-deepeval/bin/python'))
    if not Path(executable).is_file():raise ValueError('DEEPEVAL_NOT_PREPARED')
    frozen={'test_cases':rows,'configuration':configuration,'request_limit':request_limit,
        'worker_hash':text_hash(Path(__file__).with_name('deepeval_worker.py').read_text()),'version':'4.3.1'}
    fingerprint=digest(frozen)
    with rag.store.transaction():
        previous=next((r for r in rag.store.list('rag_metric_batches') if r.request_id==request_id),None)
        if previous:
            if previous.input_hash!=fingerprint:raise ValueError('IDEMPOTENCY_CONFLICT')
            return previous
        record=MetricBatch(request_id=request_id,input_hash=fingerprint,parent_run_id=run_id,frozen_input=frozen)
        lease=rag.store.acquire_run_lease(record.batch_id,'rag_metric_batches');rag.store.put('rag_metric_batches',record)
    process=None;result=None;error=None
    try:
        process=await asyncio.create_subprocess_exec(executable,str(Path(__file__).with_name('deepeval_worker.py')),
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
            env={k:v for k,v in os.environ.items() if not k.startswith(('OPENAI_','ANTHROPIC_','CONFIDENT_','DEEPEVAL_'))})
        output,_=await asyncio.wait_for(process.communicate(json.dumps({**frozen,'credential':credential},ensure_ascii=False).encode()),timeout=180)
        if process.returncode or len(output)>2_000_000:raise ValueError('DEEPEVAL_SIDECAR_FAILED')
        result=json.loads(output)
        if credential and credential in json.dumps(result,ensure_ascii=False):
            result=None;raise ValueError('DEEPEVAL_INVALID_RESPONSE')
        if result['request_count']>request_limit:raise ValueError('DEEPEVAL_BUDGET_INVALID')
    except asyncio.CancelledError:error='DEEPEVAL_INTERRUPTED_USAGE_UNKNOWN'
    except Exception:error='DEEPEVAL_FAILED_USAGE_MAY_BE_UNKNOWN'
    finally:
        if process and process.returncode is None:process.kill();await process.wait()
        try:
            record=record.model_copy(update={'status':'FAILED' if error else 'COMPLETE','result':result,'error':error,'finished_at':now()})
            with rag.store.transaction():rag.store.put('rag_metric_batches',record)
        finally:lease.close()
    return record

def observations(rag,run_id):
    records=[]
    for record in rag.store.list('rag_metric_batches'):
        if record.parent_run_id!=run_id:continue
        if record.status=='RUNNING':
            with rag.store.transaction():
                record=rag.store.get('rag_metric_batches',record.batch_id)
                if record.status=='RUNNING':
                    try:lease=rag.store.acquire_run_lease(record.batch_id,'rag_metric_batches')
                    except BlockingIOError:pass
                    else:
                        try:
                            record=record.model_copy(update={'status':'FAILED','error':'DEEPEVAL_INTERRUPTED_USAGE_UNKNOWN','finished_at':now()});rag.store.put('rag_metric_batches',record)
                        finally:lease.close()
        records.append(record)
    return records
