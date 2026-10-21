"""Synthetic acceptance only: no real users, commercial calls, or production records."""
import asyncio
import csv
import io
import json
from copy import deepcopy
from datetime import datetime,timezone
from types import SimpleNamespace as NS
import pytest
from experiments.store import JsonStore
from experiments.providers import ProviderConfig,ProviderSessions,ProviderFailure
from experiments.operations_service import OperationsService
from experiments.operations_models import InferenceEvent
from experiments.domain_worker import run_job,tool_checks
from experiments.retrieval_models import RetrievalCase
from experiments.trusted_results import freeze_input,sample_flow
from experiments.evidence_judge import normalize_alias_judgment,alias_sample_input
from experiments.calibration_models import CalibrationSample,RubricVersion
from evaluation.calibration import RUBRIC_TEMPLATE,final_verdict
from experiments.canonical import digest
from experiments.input_budget import preflight
from test_agent_eval_practice import env as rag_env

class LocalJudge:
    """In-memory protocol fixture. It does not estimate Judge accuracy."""
    calls=0;fail=False
    def __init__(self,config,key,judge_key=None):self.config=config;self.call_count=0;self.call_traces=[]
    def client(self,role):
        assert role=='judge'
        async def create(**kwargs):
            self.call_count+=1;LocalJudge.calls+=1
            if LocalJudge.fail:raise ProviderFailure('RATE_LIMITED')
            s=json.loads(kwargs['messages'][0]['content'])['sample'];catalog=s['fragment_catalog']
            a=[v['fragment_id'] for v in catalog if v['scope']=='ANSWER'][:1]
            p=[v['fragment_id'] for v in catalog if v['scope']=='REFERENCE'][:1]
            r=[v['fragment_id'] for v in catalog if v['scope']=='RETRIEVED'][:1]
            dims={k:{'score':2,'answer_fragment_ids':a,'evidence_fragment_ids':r if k=='faithfulness' and r else p,'reason':'Synthetic protocol fixture.'} for k in RUBRIC_TEMPLATE['dimensions']}
            value={'dimensions':dims,'critical_errors':[],'error_tags':[],'task_resolved':'YES','faithful_to_available':'YES',
                'task_failure_reasons':[],'insufficient_items':[],'reason':'Synthetic fixture; not a quality claim.'}
            return NS(content=[NS(type='text',text=json.dumps(value))])
        return NS(messages=NS(create=create))
    async def close(self):pass

@pytest.fixture
def ops(tmp_path):
    store=JsonStore(tmp_path/'artifacts');providers=ProviderSessions(store)
    session=providers.create(ProviderConfig(provider='openai-compatible',base_url='http://127.0.0.1:8129/v1',model='fixture',max_tokens=1024),'synthetic-memory-key')
    store.put('provider_sessions',session.model_copy(update={'status':'READY','text_connection_status':'READY'}))
    value=OperationsService(NS(store=store,providers=providers));LocalJudge.calls=0;LocalJudge.fail=False
    value.save_domain(domain_id='after_sales',name='售后合成样例',business_scope='退货与售后政策咨询',template_id='POLICY_RAG',agent_kind='RAG')
    value.sid=session.provider_session_id
    return value

def records():
    return [dict(sample_id='a',question='定制能退吗？',answer='定制商品不支持无理由退货。',business_domain='after_sales',reference_complete=True,
        reference_policy=[{'evidence_id':'p','text':'定制商品不支持无理由退货。'}],retrieved_evidence=[{'evidence_id':'r','text':'定制商品不支持无理由退货。'}],family_id='custom')]

def batch(ops,rows=None,parent=None):
    content=json.dumps(rows or records(),ensure_ascii=False)
    p=ops.preview('after_sales',content)
    return ops.save_batch('after_sales',content,'json',{},'NECESSARY','合成批次','synthetic-fixture-actor','合成范围核对；不是真人标注',
        [{'sample_id':r['sample_id'],'state':'INCLUDE','reason':'属于合成售后场景'} for r in p['records']],parent,p['preview_hash'])

def execute(ops,b,request='fixture'):
    j=ops.create_job(b.batch_id,ops.sid,request)
    asyncio.run(run_job(ops.store,j.job_id,'synthetic-memory-key',provider_factory=LocalJudge))
    return ops.view(j.job_id)

def test_missing_policy_cannot_pass_even_with_all_max_model_scores(ops):
    rows=records();rows[0].update(reference_complete=False,reference_policy=[],retrieved_evidence=[])
    value=execute(ops,batch(ops,rows))
    row=value['rows'][0]
    assert row['evaluation_state']=='EVIDENCE_INSUFFICIENT'
    assert row['event'].judgment['dimensions']['conditions']['score']=='INSUFFICIENT'
    assert value['summary']['coverage']=={'numerator':0,'denominator':1,'value':0}
    assert value['summary']['pass_rate']['value'] is None
    with pytest.raises(ValueError,match='REVIEW_EVIDENCE_REQUIRED'):
        ops.review(value['job'].job_id,'a','PASS','Cannot invent missing reference','fixture')

def test_declared_fallback_can_pass_without_policy_but_task_state_is_separate(ops):
    ops.save_domain(domain_id='after_sales',name='诚实兜底',business_scope='未知政策的边界',template_id='MISSING_KNOWLEDGE',agent_kind='RAG')
    rows=records();rows[0].update(answer='资料不足，请提供订单号后转交核验。',reference_policy=[],retrieved_evidence=[],reference_complete=False)
    view=execute(ops,batch(ops,rows))
    assert view['rows'][0]['evaluation_state']=='PASS'
    assert view['rows'][0]['event'].judgment is not None

def test_ingest_maps_fields_cleans_internal_tools_keeps_original_and_unknown_scope(ops):
    raw=[{'id':'one','q':'  定制商品能退吗？  ','response':'原回答保持\n不改。','domain':'other',
        'conversation_id':'c','turn_id':'t','tools':[{'name':'orders','call_id':'call-1','conversation_id':'c','turn_id':'t','input':{},'system_prompt':'INTERNAL_ONLY'}],
        'tool_results':[{'call_id':'call-1','output':{'status':'NO_DATA','instructions':'INTERNAL_RESULT','orders':[]}}]}]
    content=json.dumps(raw+raw)
    p=ops.preview('after_sales',content,mapping={'sample_id':'id','question':'q','answer':'response','business_domain':'domain'})
    assert p['processing']['raw_count']==2 and p['processing']['unique_count']==1
    r=p['records'][0];assert r['answer']==raw[0]['response'] and r['scope']['state']=='PENDING'
    assert 'INTERNAL' not in json.dumps(r['tool_evidence'])
    assert r['tool_evidence'][0]['output']['status']=='NO_DATA'
    assert len(r['provenance']['removed_internal_fields'])==2
    assert raw[0]['tools'][0]['system_prompt']=='INTERNAL_ONLY'

def test_scope_confirmation_is_frozen_and_repair_preserves_answer(ops):
    b=batch(ops)
    changed=records();changed[0]['answer']='把错误删掉'
    with pytest.raises(ValueError,match='REPAIR_FROZEN_ANSWER_CHANGED'):batch(ops,changed,b.batch_id)
    changed=records();changed[0]['reference_policy'][0]['text']='修订的政策原文'
    child=batch(ops,changed,b.batch_id)
    assert child.parent_batch_id==b.batch_id
    assert ops.store.get('evidence_batches',b.batch_id).records[0]['reference_policy'][0]['text']!=child.records[0]['reference_policy'][0]['text']
    assert not ops.store.list('operations_reviews')
    with pytest.raises(ValueError,match='Immutable'):ops.store.put('evidence_batches',b)

def test_job_is_idempotent_reconciled_and_csv_uses_same_current_review(ops):
    b=batch(ops);view=execute(ops,b);job=view['job']
    assert ops.create_job(b.batch_id,ops.sid,'fixture').job_id==job.job_id
    assert LocalJudge.calls==1 and view['summary']['pass_rate']['value']==1
    ops.review(job.job_id,'a','FAIL','合成复核指出实际错误，仅验证版本流程','fixture')
    current=ops.view(job.job_id);assert current['summary']['pass_rate']['value']==0
    rows=list(csv.DictReader(io.StringIO(ops.csv(job.job_id).decode('utf-8-sig'))))
    assert rows[0]['机器判定']=='PASS' and rows[0]['当前有效判定']=='FAIL'
    assert rows[0]['通过分子']=='0' and rows[0]['通过分母']=='1'
    assert LocalJudge.calls==1
    with pytest.raises(ValueError,match='IDEMPOTENCY_CONFLICT'):ops.create_job(b.batch_id,ops.sid,'fixture',{'different':'window'})

def test_missing_and_duplicate_records_do_not_publish_whole_batch_rate(ops):
    b=batch(ops);j=ops.create_job(b.batch_id,ops.sid,'missing')
    assert ops.view(j.job_id)['summary']['pass_rate']['value'] is None
    event=InferenceEvent(job_id=j.job_id,domain_id=j.domain_id,sample_id='a',attempt=1,status='COMPLETE',evaluation_state='PASS')
    with ops.store.transaction():
        ops.store.put('inference_events',event)
        ops.store.put('inference_events',event.model_copy(update={'event_id':'duplicate-event'}))
        ops.store.put('inference_jobs',j.model_copy(update={'status':'COMPLETE'}))
    s=ops.view(j.job_id)['summary'];assert s['duplicate_ids']==['a'] and not s['complete'] and s['pass_rate']['value'] is None

def test_failed_retries_keep_events_and_do_not_duplicate_independent_sample(ops):
    b=batch(ops);LocalJudge.fail=True;view=execute(ops,b)
    assert view['rows'][0]['evaluation_state']=='EXECUTION_FAILED'
    LocalJudge.fail=False
    asyncio.run(run_job(ops.store,view['job'].job_id,'synthetic-memory-key',provider_factory=LocalJudge))
    final=ops.view(view['job'].job_id)
    assert final['summary']['independent_samples']==1 and final['summary']['actual_requests']==2
    assert final['summary']['pass_rate']['value']==1 and len(final['events'])==2
    assert final['job'].attempt==2

def test_domain_lease_does_not_block_other_domain_and_cancel_makes_no_requests(ops):
    b=batch(ops);a=ops.create_job(b.batch_id,ops.sid,'locked')
    ops.save_domain(domain_id='billing',name='账单域',business_scope='账单政策',template_id='POLICY_RAG',agent_kind='RAG')
    lock=ops.store.acquire_run_lease('after_sales','operation_domains')
    try:assert asyncio.run(run_job(ops.store,a.job_id,'key',provider_factory=LocalJudge))=='DOMAIN_BUSY'
    finally:lock.close()
    ops.cancel(a.job_id)
    assert asyncio.run(run_job(ops.store,a.job_id,'key',provider_factory=LocalJudge))=='CANCELLED'
    assert LocalJudge.calls==0

def test_full_request_preflight_counts_tools_rules_and_output_before_network():
    with pytest.raises(ProviderFailure,match='INPUT_BUDGET_EXCEEDED'):
        preflight({'system':'规则'*500,'messages':[{'role':'user','content':'x'}],'tools':[{'description':'tool'*500}],'max_tokens':4096},5000)
    assert preflight({'messages':[{'role':'user','content':'短问题'}],'max_tokens':50},1024)['allowed']

def test_scope_repair_is_not_agent_improvement_and_daily_window_idempotent(ops,monkeypatch):
    b=batch(ops);v=execute(ops,b)
    rows=records();rows[0]['reference_policy'][0]['text']='补充后的参考'
    child=batch(ops,rows,b.batch_id);v2=execute(ops,child,'second')
    comparison=ops.compare(v['job'].job_id,v2['job'].job_id)
    assert 'EVIDENCE_OR_SCOPE_CHANGED' in comparison['change_reasons']
    assert not comparison['agent_quality_improvement_established']
    plan=ops.save_schedule(domain_id='after_sales',batch_id=b.batch_id,provider_session_id=ops.sid,name='合成日级计划',timezone='Asia/Shanghai',hour=9)
    async def no_network(*args,**kwargs):pass
    monkeypatch.setattr(ops,'dispatch',no_network)
    at=datetime(2026,10,18,2,tzinfo=timezone.utc)
    asyncio.run(ops.tick(at));asyncio.run(ops.tick(at))
    jobs=[j for j in ops.store.list('inference_jobs') if j.window]
    assert len(jobs)==1 and jobs[0].window['source_kind']=='FROZEN_BATCH_REPLAY'
    assert jobs[0].window['start']!=jobs[0].window['end']
    ops.save_schedule(domain_id='after_sales',batch_id=b.batch_id,provider_session_id=ops.sid,name=plan.name,timezone=plan.timezone,hour=9,enabled=False,replaces_plan_id=plan.plan_id)
    assert not ops.schedules()[0].enabled

def test_sampling_records_source_denominator_and_reason_not_fake_human_labels(ops):
    rows=records();rows.append({**deepcopy(rows[0]),'sample_id':'b','question':'其他政策？','reference_complete':False,'reference_policy':[]})
    v=execute(ops,batch(ops,rows));p=ops.sample(v['job'].job_id,1,'stable-seed')
    assert p.random_count==1 and p.source_count==2
    item=next(v for v in p.selections if v['sample_id']=='b')
    assert 'FAILURE_OR_ABSTENTION' in item['reasons']
    assert not ops.store.list('calibration_annotations')

def test_tool_trace_checks_params_and_links_are_not_simulated_business_execution(ops):
    r=records()[0];r['tool_evidence']=[{'call_id':'c','name':'order_lookup','input':{'order_id':'B'},'status':'NO_DATA'}]
    r['tool_expectations']=[{'name':'order_lookup','required_args':{'order_id':'A'}}]
    checks=tool_checks(r,{'agent_kind':'TOOL_TRACE','rules':{}})
    assert checks[0]['status']=='FAIL'
    assert tool_checks(r,{'agent_kind':'RAG'})[0]['status']=='NOT_APPLICABLE'

def test_actual_provider_budget_rejection_occurs_before_counting_or_network():
    from experiments.provider_transport import ObservedProvider
    async def probe():
        provider=ObservedProvider(ProviderConfig(provider='openai-compatible',base_url='http://127.0.0.1:9/v1',model='synthetic',context_window_tokens=1024),'synthetic-memory-key')
        try:
            with pytest.raises(ProviderFailure,match='INPUT_BUDGET_EXCEEDED'):
                await provider.client('judge').messages.create(system='规则'*1000,messages=[{'role':'user','content':'问题'}])
            assert provider.call_count==0 and provider.call_traces==[]
        finally:await provider.close()
    asyncio.run(probe())


def test_released_unseen_validation_can_close_rag_issue_with_frozen_prompt_change(rag_env):
    # Local HTTP Agent/Judge fixture only; no claim of Agent quality or human research.
    from test_agent_eval_practice import knowledge_pair
    from test_issue_workflow import plan,report
    from experiments.calibration_service import CalibrationService
    from experiments.retrieval_validation import RetrievalValidationService
    from experiments.retrieval_runtime import ANSWER_PROMPT
    a,b,change,index=knowledge_pair(rag_env)
    rag=rag_env.rag;cal=CalibrationService(rag_env.exp)
    base=asyncio.run(rag.run(rag_env.sid,change.target_eval_set_id,verify_answers=True,scoring_profile_id='initial-evidence-v1'))
    src=cal.issue_source(base.run_id,'opened','fixture')
    issue=cal.create_issue(src['dataset_id'],'opened',base.run_id,'fixture','合成生成策略验证','AGENT','fixture','只验证运行关联和未见证据闭环',source_type='RETRIEVAL_RUN',repair_plan=plan('opened'))
    event=cal.update_issue(issue.issue_id,'fixture','REPRODUCED','本地合成复现')
    event=cal.update_issue(issue.issue_id,'fixture','CHANGED','单独修改回答策略',previous_event_id=event.event_id,change_summary='回答 Prompt 增加核对条件提示')
    config={**base.retrieval_config.model_dump(),'answer_prompt':ANSWER_PROMPT+'\n请逐项核对适用条件。'}
    prompt=rag.apply(rag.propose_change(base.run_id,'ANSWER_PROMPT_CHANGE',config,'合成策略修改验收',['opened'],True).change_id)
    retest=asyncio.run(rag.run(rag_env.sid,change.target_eval_set_id,run_type='RETEST',parent_run_id=base.run_id,change_id=prompt.change_id,verify_answers=True))
    comp=rag.compare(base.run_id,retest.run_id)
    assert comp.comparable and comp.single_recorded_change
    assert any(t.get('model_inputs',{}).get('system')==config['answer_prompt'] for row in retest.case_results for t in row.get('provider_call_traces',[]))
    assert prompt.observed_diff[0]['path']=='answer_prompt'
    validations=RetrievalValidationService(rag)
    lock=validations.lock(comp.comparison_id,'合成未见验证关联',20)
    with pytest.raises(ValueError,match='HOLDOUT_LOCKED'):
        cal.update_issue(issue.issue_id,'fixture','RETESTED','锁定未解封不能使用',previous_event_id=event.event_id,verification_run_id=lock.validation_id,outcome='FIXED',verification_report={**report(),'unseen_sample_ids':['custom-exception']},evidence_level='UNSEEN')
    final=asyncio.run(validations.execute(lock.validation_id,rag_env.sid))
    assert final['status']=='COMPLETE'
    tested=cal.update_issue(issue.issue_id,'fixture','RETESTED','已解封的合成未见证据',previous_event_id=event.event_id,verification_run_id=lock.validation_id,outcome='FIXED',verification_report={**report(),'unseen_sample_ids':['custom-exception']},evidence_level='UNSEEN')
    closed=cal.update_issue(issue.issue_id,'fixture','CLOSED','限定合成验收范围',previous_event_id=tested.event_id,closure_type='FIXED')
    assert closed.evidence_level=='UNSEEN'


def test_input_budget_abstention_is_distinct_from_transport_failure():
    from experiments.trusted_results import result_state
    a=NS(execution_status='FAILED',judge_status='NOT_RUN',judge_error=None,evaluation_error=None,
        turn_evidence=[NS(execution_error='INPUT_BUDGET_EXCEEDED')])
    assert result_state(a,{'check':{'status':'PASS'}})=='EVIDENCE_INSUFFICIENT'
    a.turn_evidence=[NS(execution_error='NETWORK_ERROR')]
    assert result_state(a,{'check':{'status':'PASS'}})=='EXECUTION_FAILED'


def test_proved_failure_survives_unknown_policy_and_missing_package_never_passes():
    from experiments.trusted_results import result_state
    a=NS(execution_status='SUCCESS',judge_status='SUCCESS',evaluation_error=None,hard_rule_violations=[],
        human_evaluation_state=None,final_status='FAIL',evidence_evaluation={'judgment':{'verdict':'FAIL','critical_errors':[]}})
    assert result_state(a,{'check':{'status':'EVIDENCE_INSUFFICIENT'}})=='FAIL'
    a.final_status='PASS';a.evidence_evaluation={}
    assert result_state(a,None)=='EVIDENCE_INSUFFICIENT'


def test_worker_recovery_records_unknown_delivery_and_other_domain_can_run(ops):
    b=batch(ops);j=ops.create_job(b.batch_id,ops.sid,'orphan')
    with ops.store.transaction():ops.store.put('inference_jobs',j.model_copy(update={'status':'RUNNING','attempt':1}))
    asyncio.run(ops.tick(datetime(2026,10,18,2,tzinfo=timezone.utc)))
    view=ops.view(j.job_id)
    assert view['job'].status=='PARTIAL'
    assert not view['summary']['request_accounting_complete']
    assert view['summary']['actual_requests'] is None and view['summary']['known_request_minimum']==0
    ops.save_domain(domain_id='billing',name='其他域',business_scope='账单范围',template_id='POLICY_RAG',agent_kind='RAG')
    content=json.dumps(records());p=ops.preview('billing',content)
    other=ops.save_batch('billing',content,'json',{},'NECESSARY','其他域','fixture','独立域测试',[{'sample_id':'a','state':'INCLUDE','reason':'独立域合成核对'}],preview_hash=p['preview_hash'])
    other_job=ops.create_job(other.batch_id,ops.sid,'other-domain')
    lock=ops.store.acquire_run_lease('after_sales','operation_domains')
    try:assert asyncio.run(run_job(ops.store,other_job.job_id,'synthetic-memory-key',provider_factory=LocalJudge))=='COMPLETE'
    finally:lock.close()
    assert ops.view(other_job.job_id)['summary']['pass_rate']['value']==1


def test_csv_header_integrity_and_tool_business_description_are_preserved(ops):
    from experiments.evidence_ingest import parse
    with pytest.raises(ValueError,match='IMPORT_CSV_HEADERS_INVALID'):parse('question,question\na,b','csv')
    with pytest.raises(ValueError,match='IMPORT_RECORDS_INVALID'):parse('7','json')
    rows=records();rows[0]['tools']=[{'call_id':'c','name':'lookup','status':'SUCCESS','output':{'description':'业务条件：定制不可退','system_prompt':'内部提示词'}}]
    content=json.dumps(rows);preview=ops.preview('after_sales',content,mapping={'question':''})
    record=preview['records'][0]
    assert record['question']=='定制能退吗?' and record['provenance']['question_normalized']
    assert record['tool_evidence'][0]['output']['description']=='业务条件：定制不可退'
    assert 'system_prompt' not in record['tool_evidence'][0]['output']


def test_daily_schedule_save_is_idempotent_and_revisions_replace_one_slot(ops):
    b=batch(ops)
    payload=dict(domain_id='after_sales',batch_id=b.batch_id,provider_session_id=ops.sid,name='合成每天计划',timezone='Asia/Shanghai',hour=9)
    first=ops.save_schedule(**payload);again=ops.save_schedule(**payload)
    assert first.plan_id==again.plan_id and len(ops.schedules())==1
    revised=ops.save_schedule(**{**payload,'name':'修订后的计划名称'})
    assert revised.replaces_plan_id==first.plan_id and ops.schedules()==[revised]
    assert len(ops.store.list('daily_plans'))==2
    with pytest.raises(ValueError,match='SCHEDULE_TIMEZONE_INVALID'):ops.save_schedule(**{**payload,'timezone':'not/a/timezone'})


def test_main_rag_abstention_review_and_csv_preserve_original_event(rag_env):
    from test_agent_eval_practice import knowledge_pair
    from experiments.retrieval_export import export_run
    base,_,_,_=knowledge_pair(rag_env)
    path=rag_env.exp.store.path('retrieval_runs',base.run_id);before=path.read_bytes()
    review=rag_env.rag.review(base.run_id,'opened','EVIDENCE_INSUFFICIENT','合成复核：需要补充业务对象信息后再判断。','contract-fixture')
    assert review.effective_result.human_evaluation_state=='EVIDENCE_INSUFFICIENT'
    assert review.effective_result.original_status==base.answer_results[0].original_status
    view=rag_env.rag.view(base.run_id)
    assert view['trusted_result']['cases'][0]['evaluation_state']=='EVIDENCE_INSUFFICIENT'
    assert view['answer_metrics']['valid']==0 and view['answer_metrics']['pass_rate'] is None
    rows=list(csv.DictReader(io.StringIO(export_run(rag_env.rag,base.run_id).content.decode('utf-8-sig'))))
    assert rows[0]['人工复核结果']==rows[0]['当前有效判定']=='证据不足'
    assert path.read_bytes()==before


def test_review_revisions_count_one_current_disagreement_not_all_events(ops):
    view=execute(ops,batch(ops));jid=view['job'].job_id
    ops.review(jid,'a','FAIL','合成复核一','fixture')
    assert ops.view(jid)['summary']['human_disagreements']==1
    ops.review(jid,'a','PASS','合成复核二：核对完整参考后纠正','fixture')
    summary=ops.view(jid)['summary']
    assert summary['human_review_count']==1 and summary['human_disagreements']==0
    assert len(ops.store.list('operations_reviews'))==2


def test_import_existing_rag_uses_frozen_policies_not_current_knowledge(rag_env):
    from test_agent_eval_practice import knowledge_pair
    from experiments.operations_service import OperationsService
    base,_,_,_=knowledge_pair(rag_env)
    op=OperationsService(rag_env.exp);before=rag_env.exp.store.path('retrieval_runs',base.run_id).read_bytes()
    result=op.from_rag(base.run_id)
    assert not result['answer_regenerated']
    assert [r['sample_id'] for r in result['records']]==base.execution_order
    assert all(r['sample_id']!='custom-exception' for r in result['records'])
    assert result['records'][0]['reference_policy'][0]['text']==base.controls['knowledge_snapshot']['documents'][0]['text']
    assert result['records'][0]['answer']==base.answer_results[0].turn_evidence[-1].response
    assert rag_env.exp.store.path('retrieval_runs',base.run_id).read_bytes()==before
