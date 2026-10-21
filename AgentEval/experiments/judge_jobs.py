"""Fixed-answer scoring on the existing domain worker and atomic event store.

STARTED events reserve the budget before network I/O. Unknown delivery is never
automatically repeated. Reports are immutable, explicit subsets of one protocol.
"""
import asyncio
import json
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from pydantic import Field
from .models import Artifact, uid, now
from .canonical import digest, text_hash
from .calibration_models import CalibrationSample, RubricVersion
from .judge_contract import VERSION, PROMPT_SUFFIX, json_schema, issue
from .providers import ProviderConfig, ProviderFailure

class AnswerArtifact(Artifact):
    answer_id: str
    source_run_id: str
    source_case_id: str
    source_hash: str
    input_hash: str
    answer_hash: str

class ScoreJob(Artifact):
    job_id: str = Field(default_factory=uid)
    request_id: str
    request_hash: str
    source_run_id: str
    answer_ids: list[str]
    case_ids: list[str]
    provider_session_id: str
    provider_configuration: dict
    protocol: dict
    protocol_hash: str
    request_budget: int
    token_budget: int
    max_attempts: int = 2
    status: Literal['QUEUED','RUNNING','COMPLETE','PARTIAL','FAILED'] = 'QUEUED'
    finished_at: str | None = None
    report_id: str | None = None
    last_error: str | None = None

class ScoreRequest(Artifact):
    request_id: str
    request_hash: str
    job_id: str

class JudgeAttempt(Artifact):
    event_id: str
    attempt_id: str
    job_id: str
    case_id: str
    answer_id: str
    answer_hash: str
    protocol_hash: str
    number: int
    parent_attempt_id: str | None = None
    trigger: str
    phase: Literal['STARTED','FINISHED','UNKNOWN']
    reserved_requests: int = 0
    reserved_tokens: int = 0
    result: dict | None = None
    traces: list[dict] = Field(default_factory=list)
    finished_at: str | None = None

class ScoreReport(Artifact):
    report_id: str = Field(default_factory=uid)
    job_id: str
    source_run_id: str
    score_revision: int
    protocol_hash: str
    case_ids: list[str]
    adoption_manifest: list[dict]
    manifest_hash: str
    summary: dict

def component_identity():
    root=Path(__file__).parent
    groups={
        'scoring':['judge_contract.py','judge_jobs.py','evidence_judge.py','calibration_models.py','evidence_policy.py','trusted_results.py','scoring_profiles.py',
                   'calibration_service.py','operations_models.py','domain_worker.py','retrieval_export.py',
                   '../evaluation/calibration.py','../evaluation/calibration_evidence.py'],
        'transport':['provider_transport.py','provider_trace.py','providers.py','openai_chat.py','input_budget.py']}
    return {group:{p:text_hash((root/p).read_text()) for p in paths} for group,paths in groups.items()}

def load_answer(store, run_id, case_id):
    from .retrieval_models import RetrievalCase
    run=store.get('retrieval_runs',run_id)
    if run.status not in {'COMPLETE','PARTIAL'}:raise ValueError('SOURCE_RUN_UNAVAILABLE')
    if not run.runtime_end_check.get('reliable_isolation'):raise ValueError('RUNTIME_ISOLATION_UNVERIFIED')
    cases=[c for c in run.controls['eval_set_snapshot']['cases'] if c['case_id']==case_id]
    rows=[r for r in run.case_results if r['case_id']==case_id]
    answers=[a for a in run.answer_results if a.case_id==case_id]
    if len(cases)!=1 or len(rows)!=1 or len(answers)!=1 or case_id not in run.execution_order:
        raise ValueError('RESULT_RECONCILIATION_INCOMPLETE')
    case=RetrievalCase.model_validate(cases[0]);row=rows[0];answer=answers[0]
    if case.partition!='DEBUG' or row.get('partition','DEBUG')!='DEBUG':raise ValueError('HOLDOUT_LOCKED')
    if row.get('status')!='SUCCESS' or answer.execution_status!='SUCCESS' or not answer.turn_evidence:
        raise ValueError('ANSWER_NOT_ACQUIRED')
    package=row.get('input_package') or {}
    expected=digest({k:v for k,v in package.items() if k not in {'content_hash','input_id'}})
    if expected!=package.get('content_hash') or expected!=package.get('input_id'):
        raise ValueError('SOURCE_HASH_MISMATCH')
    if package.get('current_answer')!=answer.turn_evidence[-1].response or package.get('question')!=case.query or package.get('sample_id')!=case_id or package.get('run_id')!=run_id:
        raise ValueError('SOURCE_HASH_MISMATCH')
    if any(e.get('source_sha256')!=text_hash(e['text']) for e in package['evidence']):
        raise ValueError('SOURCE_HASH_MISMATCH')
    identity={'source_run_id':run_id,'source_case_id':case_id,'source_hash':digest(run.model_dump(mode='json')),
              'input_hash':expected,'answer_hash':text_hash(package['current_answer'])}
    artifact=AnswerArtifact(answer_id=digest(identity),**identity)
    sample=CalibrationSample(sample_id=case_id,group_id=case.group_id or case_id,partition='CALIBRATION',
        question=package['question'],context=package['necessary_history'],answer=package['current_answer'],
        retrieved_evidence=[{'evidence_id':e['evidence_id'],'document_id':e['document_id'],'text':e['text']} for e in package['evidence'] if e['scope']=='RETRIEVED'],
        reference_policy=[{'evidence_id':e['evidence_id'],'document_id':e['document_id'],'text':e['text']} for e in package['evidence'] if e['scope']=='REFERENCE'],
        reference_complete=package.get('reference_complete') is True,origin=package.get('source_type','UNKNOWN'),
        expected_facts=[*case.must_do,*([case.expected_answer] if case.expected_answer else [])],
        provenance={'input_id':expected,'reference_completeness':package.get('reference_completeness'),
            'reference_completeness_known':package.get('reference_complete') is not None,
            'evidence_context':case.evidence_context,'scenario_rules':package.get('scenario_rules',{}),'tool_evidence':package.get('tool_evidence',[])})
    return run,artifact,sample,package,answer

def snapshot_protocol(run, configuration, max_attempts):
    from .evidence_judge import ALIAS_PROMPT
    profile=run.controls.get('scoring_profile')
    if not profile:raise ValueError('SCORING_PROFILE_REQUIRED')
    protocol=profile['protocol']
    if protocol.get('output_schema')!='EXACT_FRAGMENT_ALIASES_V1':raise ValueError('SCORING_PROFILE_REQUIRED')
    cfg=ProviderConfig.model_validate(configuration)
    judge=ProviderConfig.model_validate(cfg.judge_provider_configuration) if cfg.judge_provider_configuration else cfg
    return {'wire_contract_version':VERSION,'prompt':protocol.get('prompt',ALIAS_PROMPT),
        'prompt_suffix':PROMPT_SUFFIX,'examples':protocol.get('examples',[]),'wire_schema':json_schema(),
        'rubric':profile['rubric'],'output_mode':judge.judge_output_mode,'judge_configuration':judge.model_dump(mode='json'),
        'components':component_identity(),'parser_version':'STRICT_ALIASES_2',
        'recovery':{'max_attempts':max_attempts,'adoption':'FIRST_VALID','unknown_delivery':'STOP',
            'retry_valid_fail':False,'retry_truncated':False},'calibration_status':'NEW_PROTOCOL_UNVALIDATED'}

class JudgeJobService:
    def __init__(self, rag):
        self.rag=rag;self.store=rag.store;self.providers=rag.providers
        self.tasks={}

    def preview(self, run_id, case_ids, provider_session_id, max_attempts=2):
        if not case_ids or len(case_ids)!=len(set(case_ids)) or max_attempts not in (1,2):raise ValueError('SCORING_SCOPE_INVALID')
        session=self.providers.get(provider_session_id)
        cfg=session.configuration
        loaded=[load_answer(self.store,run_id,sid) for sid in case_ids]
        protocol=snapshot_protocol(loaded[0][0],cfg.model_dump(mode='json'),max_attempts)
        judge=ProviderConfig.model_validate(protocol['judge_configuration'])
        return {'protocol':protocol,'protocol_hash':digest(protocol),'case_ids':case_ids,
            'answer_hashes':{a.source_case_id:a.answer_hash for _,a,_,_,_ in loaded},
            'maximum_requests':min(cfg.max_calls,len(case_ids)*max_attempts),'token_reservation_per_attempt':judge.context_window_tokens,
            'scope':'SELECTED_FIXED_ANSWERS','agent_calls':0,'retrieval_calls':0}

    def create(self, run_id, case_ids, provider_session_id, request_id, max_attempts=2, request_budget=None, token_budget=None, protocol_hash=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',request_id):raise ValueError('IDEMPOTENCY_REQUEST_INVALID')
        params=dict(run_id=run_id,case_ids=case_ids,provider_session_id=provider_session_id,max_attempts=max_attempts,
                    request_budget=request_budget,token_budget=token_budget,protocol_hash=protocol_hash)
        request_hash=digest(params)
        # Replaying an accepted request never needs credentials or a current code version.
        with self.store.transaction():
            try:receipt=self.store.get('score_requests',request_id)
            except FileNotFoundError:receipt=None
            if receipt:
                if receipt.request_hash!=request_hash:raise ValueError('IDEMPOTENCY_CONFLICT')
                return self.store.get('score_jobs',receipt.job_id)
            prior=next((j for j in self.store.list('score_jobs') if j.request_id==request_id),None)
            if prior:
                if prior.request_hash!=request_hash:raise ValueError('IDEMPOTENCY_CONFLICT')
                return prior
        preview=self.preview(run_id,case_ids,provider_session_id,max_attempts)
        if protocol_hash and preview['protocol_hash']!=protocol_hash:raise ValueError('SCORING_PROTOCOL_CHANGED')
        cfg=self.providers.get(provider_session_id).configuration
        if self.providers.get(provider_session_id).text_connection_status!='READY':raise ValueError('CONNECTION_NOT_VERIFIED')
        self.providers.credential(provider_session_id);self.providers.judge_credential(provider_session_id)
        requests=request_budget if request_budget is not None else preview['maximum_requests']
        tokens=token_budget if token_budget is not None else requests*preview['token_reservation_per_attempt']
        if type(requests) is not int or not len(case_ids)<=requests<=min(cfg.max_calls,preview['maximum_requests']) or type(tokens) is not int or tokens<1:
            raise ValueError('REQUEST_BUDGET_INVALID')
        with self.store.transaction():
            try:receipt=self.store.get('score_requests',request_id)
            except FileNotFoundError:receipt=None
            if receipt:
                if receipt.request_hash!=request_hash:raise ValueError('IDEMPOTENCY_CONFLICT')
                return self.store.get('score_jobs',receipt.job_id)
            prior=next((j for j in self.store.list('score_jobs') if j.request_id==request_id),None)
            if prior:
                if prior.request_hash!=request_hash:raise ValueError('IDEMPOTENCY_CONFLICT')
                return prior
            # Different browser clicks also coalesce while the same scope is active.
            active=next((j for j in self.store.list('score_jobs') if j.source_run_id==run_id and j.case_ids==case_ids
                and j.protocol_hash==preview['protocol_hash'] and j.status in {'QUEUED','RUNNING'}),None)
            if active:
                self.store.put('score_requests',ScoreRequest(request_id=request_id,request_hash=request_hash,job_id=active.job_id))
                return active
            answer_ids=[]
            for sid in case_ids:
                _,a,_,_,_=load_answer(self.store,run_id,sid)
                try:self.store.get('answer_artifacts',a.answer_id)
                except FileNotFoundError:self.store.put('answer_artifacts',a)
                answer_ids.append(a.answer_id)
            job=self.store.put('score_jobs',ScoreJob(request_id=request_id,request_hash=request_hash,
                source_run_id=run_id,answer_ids=answer_ids,case_ids=case_ids,provider_session_id=provider_session_id,
                provider_configuration=cfg.model_dump(mode='json'),protocol=preview['protocol'],protocol_hash=preview['protocol_hash'],
                max_attempts=max_attempts,request_budget=requests,token_budget=tokens))
            self.store.put('score_requests',ScoreRequest(request_id=request_id,request_hash=request_hash,job_id=job.job_id))
            return job

    async def dispatch(self, job_id, resume=False):
        from .worker_dispatch import launch_worker
        job=self.store.get('score_jobs',job_id)
        if job.status not in ({'QUEUED','PARTIAL'} if resume else {'QUEUED'}):return job
        if job_id in self.tasks and not self.tasks[job_id].done():return job
        cfg=self.providers.get(job.provider_session_id).configuration.model_dump(mode='json')
        if cfg!=job.provider_configuration:raise ValueError('PROVIDER_CONFIG_CHANGED')
        key=self.providers.credential(job.provider_session_id);judge_key=self.providers.judge_credential(job.provider_session_id)
        task=asyncio.create_task(launch_worker(self.store.root,job_id,key,judge_key,kind='score'))
        self.tasks[job_id]=task
        return job

    def view(self, job_id):
        job=self.store.get('score_jobs',job_id)
        events=[e for e in self.store.list('judge_attempts') if e.job_id==job_id]
        reports=sorted([r for r in self.store.list('score_reports') if r.job_id==job_id],key=lambda r:r.score_revision)
        # GET is read-only: a stale RUNNING record is explicit, never a dispatch trigger.
        lease=None
        try:lease=self.store.acquire_run_lease(job_id,'score_jobs')
        except BlockingIOError:pass
        running=lease is None
        if lease:lease.close()
        return {'job':job,'events':events,'reports':reports,'report':reports[-1] if reports else None,
            'worker_active':running,'interrupted':job.status=='RUNNING' and not running}

    def history(self, run_id):
        self.store.get('retrieval_runs',run_id)
        return [j for j in self.store.list('score_jobs') if j.source_run_id==run_id]

    def report(self, report_id):
        return self.store.get('score_reports',report_id)

    def compare(self, before_id, after_id):
        before=self.report(before_id);after=self.report(after_id)
        reasons=[]
        if before.protocol_hash!=after.protocol_hash:reasons.append('SCORING_PROTOCOL_MISMATCH')
        if set(before.case_ids)!=set(after.case_ids):reasons.append('SCORING_SCOPE_MISMATCH')
        for sid in set(before.case_ids)&set(after.case_ids):
            a=load_answer(self.store,before.source_run_id,sid)[2]
            b=load_answer(self.store,after.source_run_id,sid)[2]
            if (a.question,a.context,a.expected_facts,a.provenance.get('scenario_rules'))!=(b.question,b.context,b.expected_facts,b.provenance.get('scenario_rules')):
                reasons.append('SCORING_SAMPLE_MISMATCH');break
        left={r['case_id']:r for r in before.adoption_manifest}
        right={r['case_id']:r for r in after.adoption_manifest}
        return {'before_report_id':before_id,'after_report_id':after_id,'comparable':not reasons,'reasons':reasons,
            'before_summary':before.summary,'after_summary':after.summary,
            'pairs':[{'case_id':sid,'before':left[sid]['evaluation_state'],'after':right[sid]['evaluation_state']}
                for sid in before.case_ids if sid in right],
            'agent_improvement_established':False,'scope':'EXPLICIT_SCORE_REVISIONS_ONLY'}

def publish_report(store,job):
    events=[e for e in store.list('judge_attempts') if e.job_id==job.job_id]
    starts=[e for e in events if e.phase=='STARTED']
    ends={e.attempt_id:e for e in events if e.phase in {'FINISHED','UNKNOWN'}}
    manifest=[]
    for sid in job.case_ids:
        attempts=sorted([s for s in starts if s.case_id==sid],key=lambda s:s.number)
        finished=[ends[s.attempt_id] for s in attempts if s.attempt_id in ends]
        valid=next((e for e in finished if (e.result or {}).get('status')=='SUCCESS' and (e.result or {}).get('judgment')),None)
        chosen=valid or (finished[-1] if finished else None)
        result=(chosen.result or {}) if chosen else {}
        state=({'PASS':'PASS','FAIL':'FAIL','PENDING':'EVIDENCE_INSUFFICIENT'}[result['judgment']['verdict']]
            if valid else 'EVIDENCE_INSUFFICIENT' if result.get('status')=='NOT_RUN' else 'EXECUTION_FAILED' if chosen else 'NOT_RUN')
        manifest.append({'case_id':sid,'answer_id':job.answer_ids[job.case_ids.index(sid)],
            'adopted_attempt_id':valid.attempt_id if valid else None,'latest_attempt_id':chosen.attempt_id if chosen else None,
            'evaluation_state':state,'result':result,'attempt_count':len(attempts)})
    counts=Counter(r['evaluation_state'] for r in manifest);binary=counts['PASS']+counts['FAIL']
    known=[(e.result or {}).get('usage') for e in ends.values() if (e.result or {}).get('usage')]
    known_requests=sum((e.result or {}).get('request_count',0) for e in ends.values() if e.phase=='FINISHED')
    uncertain=sum(1 for s in starts if s.attempt_id not in ends or ends[s.attempt_id].phase=='UNKNOWN')
    report=ScoreReport(job_id=job.job_id,source_run_id=job.source_run_id,
        score_revision=len([r for r in store.list('score_reports') if r.job_id==job.job_id])+1,
        protocol_hash=job.protocol_hash,case_ids=job.case_ids,adoption_manifest=manifest,manifest_hash=digest(manifest),
        summary={'scope':'SELECTED_FIXED_ANSWERS','case_count':len(job.case_ids),'counts':dict(counts),
            'recovery_status':'COMPLETE' if binary==len(job.case_ids) else 'PARTIAL',
            'coverage':{'numerator':binary,'denominator':len(job.case_ids),'value':binary/len(job.case_ids)},
            'pass_rate':{'numerator':counts['PASS'],'denominator':binary,'value':counts['PASS']/binary if binary else None},
            'scoring_finished':all(r['latest_attempt_id'] for r in manifest),'request_reservations':len(starts),
            'token_reservations':sum(s.reserved_tokens for s in starts),'known_total_tokens':sum(u.get('total_tokens',u['input_tokens']+u['output_tokens']) for u in known),
            'known_request_count':known_requests,'uncertain_delivery_requests':uncertain,
            'actual_requests':None if uncertain else known_requests,
            'unknown_usage_requests':max(0,known_requests+uncertain-len(known)),
            'currency_cost':None,'agent_calls':0,'retrieval_calls':0,'agent_improvement_established':False})
    report=store.put('score_reports',report)
    return store.put('score_jobs',job.model_copy(update={'report_id':report.report_id}))

async def run_score_job(store,job_id,key,judge_key=None,provider_factory=None):
    from .provider_transport import ObservedProvider
    from .evidence_judge import score_alias_answer
    from .calibration_models import CalibrationResult
    try:lease=store.acquire_run_lease(job_id,'score_jobs')
    except BlockingIOError:return 'JOB_BUSY'
    provider=None
    try:
        with store.transaction():
            job=store.get('score_jobs',job_id)
            if job.status in {'COMPLETE','FAILED'}:return job.status
            if job.protocol.get('components')!=component_identity():raise ValueError('SCORING_PROTOCOL_CHANGED')
            job=store.put('score_jobs',job.model_copy(update={'status':'RUNNING','last_error':None,'finished_at':None}))
            # A begin without end is uncertain external delivery, including after a hard kill.
            events=[e for e in store.list('judge_attempts') if e.job_id==job_id]
            ended={e.attempt_id for e in events if e.phase!='STARTED'}
            for start in events:
                if start.phase=='STARTED' and start.attempt_id not in ended:
                    store.put('judge_attempts',start.model_copy(update={'event_id':start.attempt_id+'_end','phase':'UNKNOWN','finished_at':now(),
                        'result':{'status':'INTERFACE_ERROR','error':'DELIVERY_UNKNOWN','usage':None,'validation_issues':[issue('REQUEST','DELIVERY_UNKNOWN')]}}))
        provider=(provider_factory or ObservedProvider)(ProviderConfig.model_validate(job.provider_configuration),key,judge_key)
        provider.request_limit=job.request_budget
        rubric=RubricVersion.model_validate(job.protocol['rubric'])
        protocol=SimpleNamespace(**job.protocol)
        for sid,answer_id in zip(job.case_ids,job.answer_ids):
            _,a,sample,package,original=load_answer(store,job.source_run_id,sid)
            saved=store.get('answer_artifacts',answer_id)
            if any(getattr(saved,k)!=getattr(a,k) for k in ('source_hash','input_hash','answer_hash')):raise ValueError('SOURCE_HASH_MISMATCH')
            events=[e for e in store.list('judge_attempts') if e.job_id==job_id]
            starts=sorted([e for e in events if e.phase=='STARTED' and e.case_id==sid],key=lambda e:e.number)
            ends={e.attempt_id:e for e in events if e.phase!='STARTED'}
            if any((ends[s.attempt_id].result or {}).get('status')=='SUCCESS' for s in starts):continue
            previous=ends.get(starts[-1].attempt_id) if starts else None
            if previous and (previous.phase=='UNKNOWN' or not any(i.get('retryable') for i in (previous.result or {}).get('validation_issues',[]))):continue
            for number in range(len(starts)+1,job.max_attempts+1):
                reserve=ProviderConfig.model_validate(job.protocol['judge_configuration']).context_window_tokens
                with store.transaction():
                    all_starts=[e for e in store.list('judge_attempts') if e.job_id==job_id and e.phase=='STARTED']
                    if len(all_starts)>=job.request_budget or sum(s.reserved_tokens for s in all_starts)+reserve>job.token_budget:
                        job=store.put('score_jobs',job.model_copy(update={'last_error':'CALL_BUDGET_EXCEEDED'}));break
                    attempt_id=digest([job_id,sid,number])
                    start=JudgeAttempt(event_id=attempt_id+'_start',attempt_id=attempt_id,job_id=job_id,case_id=sid,
                        answer_id=answer_id,answer_hash=a.answer_hash,protocol_hash=job.protocol_hash,number=number,
                        parent_attempt_id=previous.attempt_id if previous else None,trigger='VALIDATION_RECOVERY' if previous else 'USER_FIXED_ANSWER_RESCORE',
                        phase='STARTED',reserved_requests=1,reserved_tokens=reserve)
                    store.put('judge_attempts',start)
                trace_start=len(provider.call_traces)
                blocked=[v for v in package.get('missing_items',[]) if v!='REFERENCE_COMPLETENESS_UNCONFIRMED']
                if blocked or package.get('truncated_items') or package.get('check',{}).get('issues'):
                    result=CalibrationResult(sample_id=sid,repetition=number,status='NOT_RUN',error='EVIDENCE_INSUFFICIENT')
                elif original.hard_rule_violations:
                    result=CalibrationResult(sample_id=sid,repetition=number,status='NOT_RUN',error='HARD_RULE_RESULT_PRESERVED')
                else:
                    result=await score_alias_answer(provider,rubric,sample,protocol,number,
                        (previous.result or {}).get('validation_issues') if previous else None)
                end=start.model_copy(update={'event_id':attempt_id+'_end','phase':'FINISHED',
                    'result':result.model_dump(mode='json'),'traces':provider.call_traces[trace_start:],'finished_at':now()})
                with store.transaction():
                    store.put('judge_attempts',end)
                    job=publish_report(store,job)
                previous=end
                if result.status=='SUCCESS' or not any(i.get('retryable') for i in result.validation_issues):break
        with store.transaction():
            job=publish_report(store,job)
            report=store.get('score_reports',job.report_id)
            status='COMPLETE' if report.summary['coverage']['numerator']==len(job.case_ids) else 'PARTIAL'
            store.put('score_jobs',job.model_copy(update={'status':status,'finished_at':now()}))
        return status
    except BaseException as error:
        with store.transaction():
            job=store.get('score_jobs',job_id)
            code=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z_]{3,100}',str(error)) else 'WORKER_INTERRUPTED_OR_FAILED'
            store.put('score_jobs',job.model_copy(update={'status':'PARTIAL','last_error':code,'finished_at':now()}))
        if isinstance(error,asyncio.CancelledError):raise
        return 'PARTIAL'
    finally:
        if provider:await provider.close()
        lease.close()
