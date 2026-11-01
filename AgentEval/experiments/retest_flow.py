"""A durable sequence of existing index/change/run receipts, never a second inference engine.

GET only reads. Explicit resume reconciles receipts; it never replays a saved run.
A process lease serializes each sequence across tabs and server workers.
"""
import asyncio
from typing import Literal
from pydantic import Field
from .models import Artifact, now
from .canonical import digest

class RetestFlow(Artifact):
    flow_id: str
    input_hash: str
    inputs: dict
    confirmed_scope: dict
    stage: Literal['SAVED','PREPARING','APPLYING','SUBMITTING','RUNNING','COMPARING','COMPLETE','PARTIAL','FAILED','CANCELLED','UNKNOWN']='SAVED'
    index_job_id: str|None=None
    index_id: str|None=None
    change_id: str|None=None
    run_id: str|None=None
    comparison_id: str|None=None
    cancel_requested: bool=False
    error: str|None=None
    events: list[dict]=Field(default_factory=list)

TERMINAL={'COMPLETE','PARTIAL','FAILED','CANCELLED'}
_tasks={}

def identity(rag,identifier):return (str(rag.store.root.resolve()),identifier)

def update(rag,identifier,**values):
    with rag.store.transaction():
        flow=rag.store.get('retest_flows',identifier)
        event={'at':now(),**values}
        return rag.store.put('retest_flows',flow.model_copy(update={**values,'events':[*flow.events,event]}))

def read(rag,identifier):
    flow=rag.store.get('retest_flows',identifier)
    # Read interrupted progress honestly, without resuming any paid work.
    if flow.stage not in TERMINAL and identity(rag,identifier) not in _tasks:
        try:lease=rag.store.acquire_run_lease(identifier,'retest_flows')
        except BlockingIOError:return flow
        lease.close()
        return flow.model_copy(update={'stage':'UNKNOWN','error':'FLOW_RECONCILE_REQUIRED'})
    return flow

def validate(rag,inputs):
    from .retrieval_models import RetrievalConfig,ChunkConfig
    from .retrieval_service import CHANGE_FIELDS,INDEX_CHANGES,config_diff,implementation_snapshot
    from .rag_index_controls import validate_index_change
    base=rag.store.get('retrieval_runs',inputs['baseline_run_id'])
    if base.run_type!='BASELINE' or base.status not in {'COMPLETE','PARTIAL'}:raise ValueError('BASELINE_NOT_ACQUIRED')
    if inputs.get('execution_mode')!='TRIAL' and base.controls.get('retrieval_implementation')!=implementation_snapshot():raise ValueError('BASELINE_IMPLEMENTATION_CHANGED')
    if not inputs.get('user_confirmed'):raise ValueError('CONFIRMATION_REQUIRED')
    ids=inputs['selected_case_ids']
    if not ids or len(set(ids))!=len(ids) or set(ids)-set(base.execution_order):raise ValueError('FLOW_SCOPE_INVALID')
    if inputs.get('execution_mode')=='TRIAL' and len(ids)!=1:raise ValueError('TRIAL_SCOPE_INVALID')
    if inputs.get('trial_flow_id'):
        trial=rag.store.get('retest_flows',inputs['trial_flow_id'])
        if (inputs.get('execution_mode','FULL')!='FULL' or trial.stage!='COMPLETE' or trial.inputs.get('execution_mode')!='TRIAL'
            or any(trial.inputs.get(k)!=inputs.get(k) for k in ['baseline_run_id','provider_session_id','change_type','after_config','selected_case_ids','target_index_id','prepare_index'])):
            raise ValueError('TRIAL_PLAN_CHANGED')
    session=rag.providers.get(inputs['provider_session_id'])
    rag.providers.credential(session.provider_session_id)
    rag.providers.judge_credential(session.provider_session_id)
    if session.text_connection_status!='READY':raise ValueError('CONNECTION_NOT_VERIFIED')
    if session.configuration.model_dump()!=base.provider_configuration_snapshot:raise ValueError('PROVIDER_CONFIG_CHANGED')
    kind=inputs['change_type'];after=RetrievalConfig.model_validate(inputs['after_config'])
    changes=config_diff(base.retrieval_config,after)
    prep=inputs.get('prepare_index');target=inputs.get('target_index_id')
    old=rag.store.get('knowledge_indices',base.controls['index_snapshot']['index_id'])
    if kind in INDEX_CHANGES:
        if changes or bool(prep)==bool(target):raise ValueError('FLOW_INDEX_SCOPE_INVALID')
        if any(c.get('relevant_chunk_ids') for c in base.controls['eval_set_snapshot']['cases']):raise ValueError('STABLE_DOCUMENT_LABELS_REQUIRED')
        if target:validate_index_change(kind,old,rag.store.get('knowledge_indices',target))
        else:
            config=ChunkConfig.model_validate(prep['chunk_config'])
            if prep['dataset_id']!=old.knowledge_dataset_id:raise ValueError('KNOWLEDGE_DATASET_CHANGED')
            if kind=='KNOWLEDGE_UPDATE':raise ValueError('KNOWLEDGE_UPDATE_REQUIRES_REVIEWED_INDEX')
            if prep['version']!=old.knowledge_version:raise ValueError('KNOWLEDGE_CHANGED')
            model=prep['embedding_model']
            if kind=='CHUNKING_CHANGE' and (model!=old.embedding_snapshot['model'] or config==old.chunk_config):raise ValueError('CHUNKING_CHANGE_SCOPE_CHANGED')
            if kind=='EMBEDDING_CHANGE' and (model==old.embedding_snapshot['model'] or config!=old.chunk_config):raise ValueError('EMBEDDING_CHANGE_SCOPE_CHANGED')
    elif prep or target or len(changes)!=1 or changes[0]['path']!=CHANGE_FIELDS.get(kind):raise ValueError('FLOW_CHANGE_SCOPE_INVALID')
    return base,session,after

async def submit(rag,identifier,inputs,capacity):
    fingerprint=digest(inputs)
    # Idempotent replay remains readable after credentials expire.
    try:old=rag.store.get('retest_flows',identifier)
    except FileNotFoundError:old=None
    if old:
        if old.input_hash!=fingerprint:raise ValueError('IDEMPOTENCY_CONFLICT')
        return read(rag,identifier)
    base,session,after=validate(rag,inputs)
    ids=inputs['selected_case_ids'] if inputs.get('execution_mode')=='TRIAL' else base.execution_order
    count=len(ids)
    scope={'baseline_run_id':base.run_id,'case_ids':ids,'purpose':'SINGLE_CASE_TRIAL' if inputs.get('execution_mode')=='TRIAL' else 'FULL_RETEST','knowledge_version':base.controls['knowledge_snapshot']['version'],
        'controls_hash':digest(base.controls),'before_config':base.retrieval_config.model_dump(),'after_config':after.model_dump(),
        'model':session.configuration.model,'request_limit':session.configuration.max_calls,
        'estimated_requests':count*(int(after.query_rewrite)+int(after.rerank)+2*int(base.verify_answers)),
        'estimate_basis':'ONE_SUCCESSFUL_REQUEST_PER_STAGE; ACTUAL_RETRIES_USE_THE_SAME_LIMIT','cost':'UNKNOWN'}
    with rag.store.transaction():
        try:old=rag.store.get('retest_flows',identifier)
        except FileNotFoundError:old=None
        if old:
            if old.input_hash!=fingerprint:raise ValueError('IDEMPOTENCY_CONFLICT')
            return old
        if any(r.parent_run_id==base.run_id and r.status=='RUNNING' for r in rag.store.list('retrieval_runs')):
            raise ValueError('WORKSPACE_BUSY')
        if any(f.inputs.get('baseline_run_id')==base.run_id and f.stage not in TERMINAL for f in rag.store.list('retest_flows')):
            raise ValueError('WORKSPACE_BUSY')
        flow=RetestFlow(flow_id=identifier,input_hash=fingerprint,inputs=inputs,confirmed_scope=scope,
            events=[{'at':now(),'stage':'SAVED','action':'USER_CONFIRMED_PLAN_AND_RUN_SCOPE'}])
        rag.store.put('retest_flows',flow)
    launch(rag,identifier,capacity)
    return flow

def launch(rag,identifier,capacity):
    k=identity(rag,identifier)
    if k in _tasks:return
    try:lease=rag.store.acquire_run_lease(identifier,'retest_flows')
    except BlockingIOError:return
    task=asyncio.create_task(execute(rag,identifier,capacity,lease));_tasks[k]=task
    def finished(t):
        _tasks.pop(k,None)
        if not t.cancelled():t.exception()
    task.add_done_callback(finished)

async def resume(rag,identifier,capacity):
    flow=rag.store.get('retest_flows',identifier)
    if flow.stage in TERMINAL:return flow
    # No automatic replay of an interrupted external request: existing run is
    # always read and compared, never executed again.
    launch(rag,identifier,capacity)
    return read(rag,identifier)

async def execute(rag,identifier,capacity,lease):
    from . import rag_index_jobs
    from .retrieval_background import background
    try:
        flow=rag.store.get('retest_flows',identifier);inputs=flow.inputs
        trial=inputs.get('execution_mode')=='TRIAL'
        group='retrieval_trial_runs' if trial else 'retrieval_runs'
        base=rag.store.get('retrieval_runs',inputs['baseline_run_id'])
        def cancelled():return rag.store.get('retest_flows',identifier).cancel_requested
        if cancelled():return update(rag,identifier,stage='CANCELLED')
        prior_trial=rag.store.get('retest_flows',inputs['trial_flow_id']) if inputs.get('trial_flow_id') else None
        target=flow.index_id or (prior_trial.index_id if prior_trial else None) or inputs.get('target_index_id')
        if inputs.get('prepare_index') and not target:
            update(rag,identifier,stage='PREPARING',error=None)
            prep=inputs['prepare_index']
            # Deterministic IDs bridge a lost HTTP response or server restart.
            job=await rag_index_jobs.submit(rag.store,'idx_'+identifier,{'dataset_id':prep['dataset_id'],'version':prep['version'],
                'config':prep['chunk_config'],'embedding_model':prep['embedding_model']})
            update(rag,identifier,index_job_id=job.job_id)
            while job.status in {'SUBMITTED','BUILDING'}:
                if cancelled():
                    await rag_index_jobs.cancel(rag.store,job.job_id)
                    return update(rag,identifier,stage='CANCELLED')
                await asyncio.sleep(.25);job=rag_index_jobs.read(rag.store,job.job_id)
            if job.status!='READY':return update(rag,identifier,stage='FAILED',error=job.error or 'INDEX_BUILD_FAILED')
            target=job.index_id;update(rag,identifier,index_id=target)
        if cancelled():return update(rag,identifier,stage='CANCELLED')
        # Revalidate prepared material against the exact confirmed variable.
        ready={**inputs,'target_index_id':target,'prepare_index':None}
        # Saved execution can be inspected after credentials expire; validation
        # is needed only before starting a run that has no receipt yet.
        existing=background(rag).saved('run_'+identifier,group)
        if not existing:
            validate(rag,inputs)
            validate(rag,{**ready,'trial_flow_id':None})
        update(rag,identifier,stage='APPLYING',error=None)
        change_id=prior_trial.change_id if prior_trial else 'chg_'+identifier
        try:change=rag.store.get('retrieval_changes',change_id)
        except FileNotFoundError:
            change=rag.propose_change(base.run_id,inputs['change_type'],inputs['after_config'],inputs['reason'],inputs['selected_case_ids'],True,
                target_index_id=target,identifier=change_id,verification_plan=inputs.get('verification_plan'))
        change=rag.apply(change.change_id);update(rag,identifier,change_id=change.change_id)
        if cancelled():return update(rag,identifier,stage='CANCELLED')
        update(rag,identifier,stage='SUBMITTING')
        args={'provider_session_id':inputs['provider_session_id'],'retrieval_eval_set_id':change.target_eval_set_id or base.controls['eval_set_snapshot']['retrieval_eval_set_id'],
            'version':1 if change.target_eval_set_id else base.controls['eval_set_snapshot']['version'],'run_type':'RETEST','parent_run_id':base.run_id,
            'change_id':change.change_id,'verify_answers':base.verify_answers,'request_id':'run_'+identifier}
        if trial:args.update(_sink_group=group,_case_ids=inputs['selected_case_ids'])
        run=existing or await background(rag).submit(args,capacity)
        update(rag,identifier,stage='RUNNING',run_id=run.run_id)
        while run.status=='RUNNING':
            if cancelled():background(rag).request_stop(args['request_id'])
            await asyncio.sleep(.25)
            run=rag.store.get(group,run.run_id)
            # A stopped process must not leave the sequence polling forever.
            try:run_lease=rag.store.acquire_run_lease(run.run_id,group)
            except BlockingIOError:pass
            else:
                run_lease.close()
                if run.status=='RUNNING':return update(rag,identifier,stage='UNKNOWN',error='RUN_INTERRUPTED_RESULT_UNKNOWN')
        if trial:return update(rag,identifier,stage='CANCELLED' if cancelled() else 'COMPLETE' if run.status=='COMPLETE' else 'PARTIAL',error=None)
        update(rag,identifier,stage='COMPARING')
        comparison=next((c for c in rag.store.list('retrieval_comparisons') if c.baseline_run_id==base.run_id and c.retest_run_id==run.run_id),None)
        comparison=comparison or rag.compare(base.run_id,run.run_id)
        update(rag,identifier,comparison_id=comparison.comparison_id,stage='CANCELLED' if cancelled() else 'COMPLETE' if run.status=='COMPLETE' else 'PARTIAL',error=None)
    except asyncio.CancelledError:
        update(rag,identifier,stage='UNKNOWN',error='FLOW_INTERRUPTED_READ_RECEIPTS_FIRST')
    except Exception as error:
        from .providers import ProviderFailure
        code=error.code if isinstance(error,ProviderFailure) else str(error)
        import re
        if not re.fullmatch('[A-Z_]{3,100}',code):code='FLOW_STEP_FAILED'
        from .retrieval_background import background
        saved=background(rag).saved('run_'+identifier,'retrieval_trial_runs' if inputs.get('execution_mode')=='TRIAL' else 'retrieval_runs')
        update(rag,identifier,stage='UNKNOWN' if saved else 'FAILED',error=code,**({'run_id':saved.run_id} if saved else {}))
    finally:lease.close()

async def cancel(rag,identifier):
    flow=rag.store.get('retest_flows',identifier)
    if flow.stage in TERMINAL:return flow
    update(rag,identifier,cancel_requested=True)
    from .retrieval_background import background
    background(rag).request_stop('run_'+identifier)
    if identity(rag,identifier) not in _tasks:update(rag,identifier,stage='CANCELLED')
    return read(rag,identifier)

async def close(rag):
    tasks=[t for (root,_),t in list(_tasks.items()) if root==str(rag.store.root.resolve())]
    for task in tasks:task.cancel()
    if tasks:await asyncio.gather(*tasks,return_exceptions=True)
