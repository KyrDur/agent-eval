"""Dedicated inference worker. Receives credentials only through stdin's private pipe."""
import asyncio
import json
import sys
import time
from types import SimpleNamespace
from .canonical import digest
from .models import now
from .store import JsonStore
from .operations_models import InferenceEvent
from .providers import ProviderConfig,ProviderFailure
from .provider_transport import ObservedProvider
from .retrieval_models import RetrievalCase
from .scoring_profiles import score_grounded
from .calibration_models import RubricVersion


def tool_checks(record,profile):
    if profile['agent_kind']!='TOOL_TRACE':return [{'name':'business_tools','status':'NOT_APPLICABLE','reason':'当前Agent只有知识检索'}]
    results=[];tools=record['tool_evidence']
    expectations=record.get('tool_expectations') or [{'name':n} for n in profile.get('rules',{}).get('required_tools',[])]
    if not expectations:results.append({'name':'business_tools','status':'NOT_CHECKED','reason':'尚未声明本场景工具标准'})
    for expectation in expectations:
        if not isinstance(expectation,dict) or not expectation.get('name'):
            results.append({'name':'tool_expectation','status':'EVIDENCE_INSUFFICIENT','reason':'工具标准格式不完整'});continue
        matched=[t for t in tools if t.get('name')==expectation['name']]
        if not matched:
            results.append({'name':expectation['name'],'status':'EVIDENCE_INSUFFICIENT','reason':'轨迹缺少所需调用，无法确认实际执行'});continue
        for t in matched:
            required=expectation.get('required_args',{})
            args=t.get('input',t.get('arguments',{}))
            state='PASS' if isinstance(args,dict) and all(args.get(k)==v for k,v in required.items()) else 'FAIL'
            if state=='PASS' and t.get('status','UNKNOWN') not in {'SUCCESS','NO_DATA','FAILED'}:state='EVIDENCE_INSUFFICIENT'
            results.append({'name':expectation['name'],'call_id':t.get('call_id'),'status':state,
                'reason':'核对声明的工具参数；未验证外部业务事实','observed_status':t.get('status','UNKNOWN')})
    return results

async def score_record(provider,job,record):
    started=time.monotonic();before=provider.call_count;trace_start=len(provider.call_traces)
    checks=tool_checks(record,job.rule_snapshot)
    data=dict(job_id=job.job_id,domain_id=job.domain_id,sample_id=record['sample_id'],attempt=job.attempt,
        event_id=digest([job.job_id,record['sample_id'],job.attempt])[:40],status='COMPLETE',evaluation_state='EVIDENCE_INSUFFICIENT',tool_checks=checks)
    try:
        case=RetrievalCase(case_id=record['sample_id'],query=record['question'],context=record['context'],
            reference_complete=record['reference_complete'],scenario_rules=record['scenario_rules'],
            evidence_context={**record['evidence_context'],'missing_items':record['issues'],'source_type':record.get('source_type','UNKNOWN')},group_id=record['family_id'])
        retrieval={'run_id':job.job_id,'results':[{'chunk_id':e['evidence_id'],**e} for e in record['retrieved_evidence']],
            'tool_evidence':record['tool_evidence']}
        if job.rule_snapshot['agent_kind']=='TOOL_TRACE':
            retrieval['results'].extend({'chunk_id':'tool_'+str(t['call_id']),'document_id':'tool_'+str(t['call_id']),
                'text':json.dumps(t,ensure_ascii=False),'metadata':{k:t[k] for k in ('conversation_id','turn_id','object_ids') if k in t}}
                for t in record['tool_evidence'] if t.get('call_id'))
        docs=[{'document_id':e['evidence_id'],'text':e['text'],'metadata':e['metadata']} for e in record['reference_policy']]
        from .trusted_results import freeze_input
        package=freeze_input(case,retrieval,record['answer'],docs,job.job_id)
        data['input_package']=package
        if record['issues']:
            data['reason']='；'.join(record['issues'])
        elif any(c['status']=='FAIL' for c in checks):
            data.update(evaluation_state='FAIL',reason='轨迹中工具参数与预先声明的必要条件不符。')
        elif any(c['status']=='EVIDENCE_INSUFFICIENT' for c in checks):
            data['reason']='工具调用证据不足。'
        else:
            rubric_data=job.rule_snapshot['rubric']
            rubric=RubricVersion(**rubric_data,content_hash=digest(rubric_data))
            profile={'rubric':rubric.model_dump(mode='json'),'protocol':{'prompt':job.rule_snapshot['judge_prompt'],
                'examples':[],'output_schema':'EXACT_FRAGMENT_ALIASES_V1',
                'wire_contract_version':job.rule_snapshot.get('wire_contract_version')}}
            result=await score_grounded(provider,profile,case,record['answer'],retrieval,docs)
            data['input_package']=retrieval['input_package']
            if result.status=='SUCCESS' and result.judgment:
                judgment=result.judgment
                if any(t.get('status')=='NO_DATA' for t in record['tool_evidence']):
                    judgment=judgment.model_copy(update={'task_resolved':'NO'})
                data.update(judgment=judgment.model_dump(mode='json'),evaluation_state={'PASS':'PASS','FAIL':'FAIL','PENDING':'EVIDENCE_INSUFFICIENT'}[judgment.verdict],reason=judgment.reason)
            elif result.status=='NOT_RUN' or result.error=='INPUT_BUDGET_EXCEEDED':
                data['reason']=result.error or 'EVIDENCE_INSUFFICIENT'
            else:data.update(status='FAILED',evaluation_state='EXECUTION_FAILED',reason=result.error or result.status)
    except (ValueError,TypeError,KeyError):data.update(reason='INPUT_SCHEMA_OR_EVIDENCE_INVALID')
    except ProviderFailure as error:data.update(status='FAILED',evaluation_state='EXECUTION_FAILED',reason=error.code)
    data.update(request_count=provider.call_count-before,provider_call_traces=provider.call_traces[trace_start:],elapsed_ms=round((time.monotonic()-started)*1000,2))
    return InferenceEvent(**data)

async def run_job(store,job_id,key,judge_key=None,provider_factory=ObservedProvider):
    original=store.get('inference_jobs',job_id)
    try:domain_lease=store.acquire_run_lease(original.domain_id,'operation_domains')
    except BlockingIOError:return 'DOMAIN_BUSY'
    lease=None;provider=None
    try:
        try:lease=store.acquire_run_lease(job_id,'inference_jobs')
        except BlockingIOError:return 'JOB_BUSY'
        with store.transaction():
            job=store.get('inference_jobs',job_id)
            if job.status=='COMPLETE':
                events=[e for e in store.list('inference_events') if e.job_id==job_id]
                good={e.sample_id for e in events if e.status=='COMPLETE' and e.evaluation_state!='EXECUTION_FAILED'}
                if set(job.expected_ids)<=good:return 'COMPLETE'
            if job.status=='CANCEL_REQUESTED':
                store.put('inference_jobs',job.model_copy(update={'status':'CANCELLED','finished_at':now()}));return 'CANCELLED'
            if job.attempt>=job.rule_snapshot['max_attempts']:return 'MAX_ATTEMPTS_REACHED'
            job=store.put('inference_jobs',job.model_copy(update={'status':'RUNNING','attempt':job.attempt+1,'started_at':now(),'finished_at':None,'last_error':None}))
        provider=provider_factory(ProviderConfig.model_validate(job.provider_configuration),key,judge_key)
        batch=store.get('evidence_batches',job.batch_id)
        previous=[e for e in store.list('inference_events') if e.job_id==job_id]
        done={e.sample_id for e in previous if e.evaluation_state not in {'EXECUTION_FAILED','NOT_RUN'} and e.status=='COMPLETE'}
        for record in batch.records:
            if record['sample_id'] not in job.expected_ids or record['sample_id'] in done:continue
            current=store.get('inference_jobs',job_id)
            if current.status=='CANCEL_REQUESTED':break
            event=await score_record(provider,job,record)
            with store.transaction():store.put('inference_events',event)
        with store.transaction():
            current=store.get('inference_jobs',job_id)
            covered={e.sample_id for e in store.list('inference_events') if e.job_id==job_id}
            status='CANCELLED' if current.status=='CANCEL_REQUESTED' else 'COMPLETE' if set(job.expected_ids)<=covered else 'PARTIAL'
            store.put('inference_jobs',current.model_copy(update={'status':status,'finished_at':now()}))
        return status
    except BaseException:
        with store.transaction():
            current=store.get('inference_jobs',job_id)
            if current.status=='RUNNING':store.put('inference_jobs',current.model_copy(update={'status':'PARTIAL','last_error':'WORKER_INTERRUPTED_OR_FAILED','finished_at':now(),
                'uncertain_delivery_attempts':sorted(set(current.uncertain_delivery_attempts+[current.attempt]))}))
        return 'PARTIAL'
    finally:
        if provider:await provider.close()
        if lease:lease.close()
        domain_lease.close()

if __name__=='__main__':
    credentials=json.load(sys.stdin)
    if '--score' in sys.argv:
        from .judge_jobs import run_score_job
        worker=run_score_job
    else:worker=run_job
    asyncio.run(worker(JsonStore(sys.argv[1],forbidden_values=tuple(v for v in credentials.values() if v)),sys.argv[2],credentials['key'],credentials.get('judge_key')))
