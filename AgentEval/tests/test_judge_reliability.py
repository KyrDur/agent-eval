"""Isolated fixed-answer recovery, no commercial inference or source artifact writes."""
import asyncio
import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from experiments.canonical import digest
from experiments.store import JsonStore
from experiments.providers import ProviderConfig, ProviderSessions, ProviderFailure
from experiments.retrieval_models import RetrievalCase, RetrievalConfig, RetrievalRun
from experiments.trusted_results import freeze_input
from experiments.scoring_profiles import resolve_profile, INITIAL_ID
from experiments.judge_contract import EXAMPLE, validate_wire, JudgeValidationError
from experiments.judge_jobs import JudgeJobService, JudgeAttempt, load_answer, run_score_job
from experiments.evidence_judge import normalize_alias_judgment, alias_sample_input
from experiments.calibration_models import RubricVersion
from evaluation.models import CaseResult, TurnEvidence

@pytest.fixture
def environment(tmp_path):
    store=JsonStore(tmp_path/'store');providers=ProviderSessions(store)
    config=ProviderConfig(provider='openai-compatible',base_url='http://127.0.0.1:19191/v1',model='isolated-fixture',max_tokens=4096,max_calls=20)
    session=providers.create(config,'fixture-credential-only-123')
    store.put('provider_sessions',session.model_copy(update={'status':'READY','text_connection_status':'READY'}))
    profile=resolve_profile(store,INITIAL_ID,config)
    docs=[{'document_id':'spec','text':'书桌是刨花板，承重30公斤。'}]
    cases=[RetrievalCase(case_id=sid,query='书桌是什么材质？',reference_complete=True,scenario_rules={'template_id':'POLICY_RAG'}) for sid in ('a','b')]
    run=RetrievalRun(run_type='BASELINE',status='COMPLETE',provider_session_id=session.provider_session_id,
        provider_configuration_snapshot=config.model_dump(),provider_readiness_snapshot={},retrieval_config=RetrievalConfig(),verify_answers=True,
        controls={'scoring_profile':profile,'eval_set_snapshot':{'cases':[c.model_dump(mode='json') for c in cases]},
            'knowledge_snapshot':{'documents':docs}},execution_order=['a','b'],runtime_end_check={'reliable_isolation':True})
    rows=[];answers=[]
    for c in cases:
        row={'case_id':c.case_id,'query':c.query,'partition':'DEBUG','status':'SUCCESS',
            'results':[{'chunk_id':'r1','document_id':'spec','text':docs[0]['text']}], 'metrics':{}}
        row['input_package']=freeze_input(c,row,'书桌是刨花板，承重30公斤。',docs,run.run_id)
        rows.append(row)
        answers.append(CaseResult(case_id=c.case_id,execution_status='SUCCESS',judge_status='FAILED',judge_error='JUDGMENT_SCHEMA_INVALID',
            original_status='INVALID',original_reason='原始失败保留',
            turn_evidence=[TurnEvidence(turn=1,question=c.query,response='书桌是刨花板，承重30公斤。',execution_status='SUCCESS')]))
    run=store.put('retrieval_runs',run.model_copy(update={'case_results':rows,'answer_results':answers}))
    rag=NS(store=store,providers=providers)
    return JudgeJobService(rag),run,session

class Scripted:
    script=[];calls=[]
    def __init__(self,config,key,judge_key=None):
        self.config=config;self.call_count=0;self.call_traces=[];self._sdk=NS(last_usage=None,last_finish_reason=None)
    def client(self,role):
        assert role=='judge', 'Agent must never execute during fixed-answer recovery'
        async def create(**kwargs):
            self.call_count+=1;type(self).calls.append(kwargs)
            value=deepcopy(type(self).script.pop(0))
            if isinstance(value,Exception):raise value
            stop=value.pop('_stop','end_turn') if isinstance(value,dict) else 'end_turn'
            raw=json.dumps(value,ensure_ascii=False) if isinstance(value,dict) else value
            self.call_traces.append({'call_id':str(self.call_count),'operation':'JUDGE','status':'SUCCESS',
                'model_inputs':kwargs,'model_outputs':{'content':[{'type':'text','text':raw}],'stop_reason':stop}})
            return NS(content=[NS(type='text',text=raw)],stop_reason=stop)
        return NS(messages=NS(create=create))
    async def close(self):pass

def execute(manager,job,script):
    Scripted.script=deepcopy(script);Scripted.calls=[]
    return asyncio.run(run_score_job(manager.store,job.job_id,'fixture-credential-only-123',provider_factory=Scripted))

def null_output():
    bad=deepcopy(EXAMPLE);bad['dimensions']['actionability']['score']=None
    return bad

@pytest.mark.parametrize('score',[0,1,2,'NA','INSUFFICIENT'])
def test_valid_wire_scores(score):
    raw=deepcopy(EXAMPLE);raw['dimensions']['actionability']['score']=score
    assert validate_wire(raw)['dimensions']['actionability']['score']==score

@pytest.mark.parametrize('score',[None,True,False,'0','1','2',1.0,[],{}])
def test_invalid_scores_keep_exact_path_and_actual(score):
    raw=deepcopy(EXAMPLE);raw['dimensions']['actionability']['score']=score
    with pytest.raises(JudgeValidationError) as caught:validate_wire(raw)
    assert caught.value.issues[0]['field_path']=='dimensions.actionability.score'
    assert caught.value.issues[0]['actual']==score

def test_missing_dimensions_and_na_rubric_and_bad_alias(environment):
    manager,run,_=environment
    raw=deepcopy(EXAMPLE);del raw['dimensions']['relevance']
    with pytest.raises(JudgeValidationError):validate_wire(raw)
    _,_,sample,_,_=load_answer(manager.store,run.run_id,'a')
    rubric=RubricVersion.model_validate(run.controls['scoring_profile']['rubric']);_,aliases=alias_sample_input(sample)
    raw=deepcopy(EXAMPLE);raw['dimensions']['faithfulness']['score']='NA'
    with pytest.raises(JudgeValidationError) as caught:normalize_alias_judgment(raw,aliases,sample,rubric,True)
    assert caught.value.issues[0]['code']=='NA_NOT_ALLOWED'
    raw=deepcopy(EXAMPLE);raw['dimensions']['relevance']['answer_fragment_ids']=['A999']
    with pytest.raises(ValueError,match='FRAGMENT_ID_INVALID'):normalize_alias_judgment(raw,aliases,sample,rubric,True)

def test_null_recovery_immutable_first_valid_subset_and_csv_and_chat(environment):
    manager,run,session=environment;path=manager.store.path('retrieval_runs',run.run_id);before=path.read_bytes()
    job=manager.create(run.run_id,['a'],session.provider_session_id,'request-one')
    assert execute(manager,job,[null_output(),EXAMPLE])=='COMPLETE'
    view=manager.view(job.job_id);report=view['report'];ends=[e for e in view['events'] if e.phase=='FINISHED']
    assert len(Scripted.calls)==2 and len(ends)==2
    assert 'previous_validation_issues' in json.loads(Scripted.calls[1]['messages'][0]['content'])
    assert report.summary['case_count']==1 and report.summary['pass_rate']['denominator']==1
    assert report.summary['unknown_usage_requests']==2 and report.summary['agent_calls']==0
    assert report.adoption_manifest[0]['attempt_count']==2
    assert report.adoption_manifest[0]['adopted_attempt_id']==max(ends,key=lambda e:e.number).attempt_id
    assert path.read_bytes()==before
    assert manager.create(run.run_id,['a'],session.provider_session_id,'request-one').job_id==job.job_id
    assert len(Scripted.calls)==2
    from experiments.retrieval_export import export_score_report
    file=export_score_report(manager.rag,report.report_id)
    rows=list(csv.DictReader(io.StringIO(file.content.decode('utf-8-sig'))))
    assert len(rows)==1 and rows[0]['整次通过分母（勿累加）']=='1' and rows[0]['新评分协议']==job.protocol_hash
    from experiments.evaluation_chat import EvaluationChatService
    chat=EvaluationChatService(manager.rag)
    sources=chat.sources(chat.scope(run.run_id,None,None,report.report_id))
    assert sources['score_report']['summary']==report.summary
    assert 'run_overview' not in sources
    with pytest.raises(ValueError):chat.sources(chat.scope(run.run_id,None,'b',report.report_id))
    with pytest.raises(ValueError):manager.store.put('score_reports',report)
    with pytest.raises(ValueError):manager.store.put('judge_attempts',ends[0])

@pytest.mark.parametrize('kind',['FAIL','AUTH_FAILED','OUTPUT_TRUNCATED'])
def test_fail_auth_and_truncation_do_not_retry(environment,kind):
    manager,run,session=environment;job=manager.create(run.run_id,['a'],session.provider_session_id,'request-'+kind)
    raw=deepcopy(EXAMPLE)
    if kind=='FAIL':raw['dimensions']['relevance']['score']=0
    if kind=='OUTPUT_TRUNCATED':raw['_stop']='max_tokens'
    execute(manager,job,[ProviderFailure(kind) if kind=='AUTH_FAILED' else raw])
    assert len(Scripted.calls)==1
    report=manager.view(job.job_id)['report']
    if kind=='FAIL':assert report.adoption_manifest[0]['evaluation_state']=='FAIL'
    if kind=='OUTPUT_TRUNCATED':assert report.adoption_manifest[0]['result']['error']=='OUTPUT_TRUNCATED'

@pytest.mark.parametrize('script',[['{bad',EXAMPLE],[ProviderFailure('TIMEOUT'),EXAMPLE],[null_output(),null_output()]])
def test_bounded_parse_timeout_and_repeated_format_recovery(environment,script):
    manager,run,session=environment;job=manager.create(run.run_id,['a'],session.provider_session_id,'recover')
    execute(manager,job,script)
    assert len(Scripted.calls)==2 and not Scripted.script
    view=manager.view(job.job_id)
    assert len(view['events'])==4 and view['report'].summary['case_count']==1
    execute(manager,manager.store.get('score_jobs',job.job_id),[])
    assert not Scripted.calls

@pytest.mark.parametrize('requests,tokens',[(1,None),(2,1)])
def test_budget_stops_recovery_and_survives_new_worker(environment,requests,tokens):
    manager,run,session=environment;job=manager.create(run.run_id,['a'],session.provider_session_id,'budget',request_budget=requests,token_budget=tokens)
    execute(manager,job,[null_output()])
    count=manager.view(job.job_id)['report'].summary['request_reservations']
    assert len(Scripted.calls)==(1 if requests==1 else 0)
    execute(manager,manager.store.get('score_jobs',job.job_id),[])
    assert manager.view(job.job_id)['report'].summary['request_reservations']==count
    assert not Scripted.calls

def test_concurrent_clicks_and_request_conflict(environment):
    manager,run,session=environment
    def create(i):return manager.create(run.run_id,['a'],session.provider_session_id,'click-'+str(i))
    with ThreadPoolExecutor(max_workers=4) as pool:jobs=list(pool.map(create,range(4)))
    assert len({j.job_id for j in jobs})==1
    execute(manager,jobs[0],[EXAMPLE])
    assert create(3).job_id==jobs[0].job_id
    with pytest.raises(ValueError,match='IDEMPOTENCY_CONFLICT'):manager.create(run.run_id,['b'],session.provider_session_id,'click-3')

def test_interrupted_delivery_not_repeated_and_completed_cases_skipped(environment):
    manager,run,session=environment;job=manager.create(run.run_id,['a','b'],session.provider_session_id,'interrupted')
    answer=manager.store.get('answer_artifacts',job.answer_ids[0]);attempt='uncertain'
    start=JudgeAttempt(event_id=attempt+'_start',attempt_id=attempt,job_id=job.job_id,case_id='a',answer_id=answer.answer_id,
        answer_hash=answer.answer_hash,protocol_hash=job.protocol_hash,number=1,trigger='USER_FIXED_ANSWER_RESCORE',phase='STARTED',reserved_requests=1,reserved_tokens=32768)
    manager.store.put('judge_attempts',start)
    assert execute(manager,job,[EXAMPLE])=='PARTIAL'
    assert len(Scripted.calls)==1
    view=manager.view(job.job_id);report=view['report']
    assert any(e.phase=='UNKNOWN' for e in view['events'])
    assert report.summary['uncertain_delivery_requests']==1 and report.summary['actual_requests'] is None
    assert report.summary['coverage']['numerator']==1 and report.summary['case_count']==2
    execute(manager,view['job'],[])
    assert not Scripted.calls

def test_holdout_unexecuted_and_tampered_sources_are_blocked(environment):
    manager,run,session=environment
    with pytest.raises(ValueError,match='RESULT_RECONCILIATION_INCOMPLETE'):
        manager.create(run.run_id,['unexecuted'],session.provider_session_id,'unexecuted')
    raw=run.model_dump(mode='json')
    raw['controls']['eval_set_snapshot']['cases'][0]['partition']='HOLDOUT'
    raw['run_id']='holdout-source'
    manager.store.put('retrieval_runs',RetrievalRun.model_validate(raw))
    with pytest.raises(ValueError,match='HOLDOUT_LOCKED'):load_answer(manager.store,'holdout-source','a')
    raw=run.model_dump(mode='json');raw['run_id']='tampered-source'
    raw['case_results'][0]['input_package']['current_answer']='altered'
    manager.store.put('retrieval_runs',RetrievalRun.model_validate(raw))
    with pytest.raises(ValueError,match='SOURCE_HASH_MISMATCH'):load_answer(manager.store,'tampered-source','a')

def test_report_comparison_never_mix_protocol_or_scope(environment):
    manager,run,session=environment
    a=manager.create(run.run_id,['a'],session.provider_session_id,'protocol-a',max_attempts=1)
    execute(manager,a,[EXAMPLE]);left=manager.view(a.job_id)['report']
    b=manager.create(run.run_id,['a'],session.provider_session_id,'protocol-b',max_attempts=2)
    execute(manager,b,[EXAMPLE]);right=manager.view(b.job_id)['report']
    comparison=manager.compare(left.report_id,right.report_id)
    assert not comparison['comparable'] and comparison['reasons']==['SCORING_PROTOCOL_MISMATCH']
    assert not comparison['agent_improvement_established']
    c=manager.create(run.run_id,['b'],session.provider_session_id,'scope-b',max_attempts=1)
    execute(manager,c,[EXAMPLE]);other=manager.view(c.job_id)['report']
    assert manager.compare(left.report_id,other.report_id)['reasons']==['SCORING_SCOPE_MISMATCH']
