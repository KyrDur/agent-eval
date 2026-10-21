"""Synthetic lifecycle fixtures only; HUMAN here tests logic, never real research labels."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.skill_loader import SkillManager
from experiments.service import ExperimentService
from experiments.store import JsonStore
from experiments.providers import ProviderConfig, ProviderFailure
from experiments.calibration_service import CalibrationService
from experiments.calibration_models import CalibrationSample, CalibrationResult, Judgment
from experiments.calibration_api import router
from experiments.api import configure,install_validation_handler
from evaluation.calibration import check_judgment,score_answer,RUBRIC_TEMPLATE
from evaluation.calibration_metrics import metrics_with_slices
from test_agent_eval_practice import env as rag_env
from test_anonymous_workspaces import environment as isolated_env,boot

ROOT=Path(__file__).resolve().parents[1]

def sample(question='电池购买八个月损坏如何维修？',partition='CALIBRATION',group='battery',**overrides):
    return {'group_id':group,'partition':partition,'question':question,'answer':'六个月保修，超期可申请付费维修，需订单号和故障照片。',
        'retrieved_evidence':[{'evidence_id':'battery_chunk','document_id':'battery','text':'六个月保修，超期可申请付费维修，需订单号和故障照片。'}],
        'reference_policy':[{'evidence_id':'battery','document_id':'battery','text':'六个月保修，超期可申请付费维修，需订单号和故障照片。'}],
        'reference_complete':True,'origin':'CONSTRUCTED','provenance':{'fixture':'NOT_REAL_RESEARCH'},**overrides}

def judgment(value='PASS',critical=False):
    score=2 if value=='PASS' else 0 if value=='FAIL' else 'INSUFFICIENT'
    return {'dimensions':{k:{'score':score,'answer_quotes':['六个月保修'],
        'citations':[{'scope':'RETRIEVED' if k=='faithfulness' else 'REFERENCE','evidence_id':'battery_chunk' if k=='faithfulness' else 'battery','quote':'六个月保修'}],
        'reason':'Synthetic fixture reason, not human evidence.'} for k in ('faithfulness','conditions','relevance','actionability')},
        'critical_errors':['UNSUPPORTED_PROMISE'] if critical else [],'error_tags':[],
        'verdict':value,'task_resolved':'YES' if value=='PASS' else 'NO','faithful_to_available':'YES' if value=='PASS' else 'NO',
        'task_failure_reasons':[],'insufficient_items':['fixture missing context'] if value=='PENDING' else [],'reason':'Synthetic fixture.'}

class ScriptedProvider:
    instances=[]
    gate=None
    output=None
    error=None
    def __init__(self,config,key,judge_key=None):
        self.config=config;self.call_count=0;self.observations=[];self._sdk=SimpleNamespace(last_usage=None)
        self.instances.append(self)
    def client(self,role):
        assert role=='judge' # No Agent generation path.
        async def create(**kwargs):
            self.call_count+=1
            payload=json.loads(kwargs['messages'][0]['content'])
            assert 'partition' not in payload['sample'] and 'Agent version' not in payload['sample']
            if self.gate: await self.gate.wait()
            if self.error: raise ProviderFailure(self.error)
            output=self.output or judgment()
            return SimpleNamespace(content=[SimpleNamespace(type='text',text=output if isinstance(output,str) else json.dumps(output))])
        return SimpleNamespace(messages=SimpleNamespace(create=create))
    async def close(self): pass

@pytest.fixture
def env(tmp_path):
    shutil.copytree(ROOT/'skills',tmp_path/'skills')
    manager=SkillManager(tmp_path/'skills');manager.load_strict()
    exp=ExperimentService(JsonStore(tmp_path/'artifacts'),manager)
    cal=CalibrationService(exp);exp.calibration=cal;cal.provider_factory=ScriptedProvider
    ScriptedProvider.instances=[];ScriptedProvider.output=None;ScriptedProvider.error=None;ScriptedProvider.gate=None
    session=exp.providers.create(ProviderConfig(provider='openai-compatible',base_url='http://127.0.0.1:8129/v1',model='synthetic-calibration-fixture',max_tokens=4096,max_calls=100),'fixture-memory-key')
    exp.store.put('provider_sessions',session.model_copy(update={'status':'READY','text_connection_status':'READY'}))
    dataset=cal.create_dataset('Synthetic fixture only',[sample(),sample('如何申请开具发票？','HOLDOUT','invoice')],[],True,'Reduce critical false pass','Bound request budget')
    rubric=cal.create_rubric()
    return SimpleNamespace(exp=exp,cal=cal,dataset=dataset,rubric=rubric,sid=session.provider_session_id)

def annotate(env,s,actor='synthetic-annotator',source='CODEX',value='PASS'):
    blind=env.cal.open_blind(env.dataset.dataset_id,s.sample_id,env.rubric.rubric_id,actor)
    return env.cal.annotate(env.dataset.dataset_id,s.sample_id,env.rubric.rubric_id,actor,source,'BLIND',judgment(value),False,blind['blind_access_id'])

def protocol(env,variant='J1',parent=None):
    return env.cal.create_protocol(env.dataset.dataset_id,env.rubric.rubric_id,env.sid,variant,variant,
        'Synthetic protocol hypothesis.',parent_protocol_id=parent)

def run(env,p,request='fixture-request',repetitions=1,budget=10):
    return asyncio.run(env.cal.run(env.dataset.dataset_id,env.rubric.rubric_id,p.protocol_id,env.sid,request,repetitions,budget))

def test_frozen_artifacts_and_fixed_answer_only(env):
    p=protocol(env);r=run(env,p)
    original=env.cal.store.get('calibration_runs',r['run_id'])
    assert r['request_count']==1 and original.sample_snapshot[0].answer==env.dataset.samples[0].answer
    assert original.metrics['cost']['usage'] is None
    for group,obj in [('calibration_datasets',env.dataset),('calibration_rubrics',env.rubric),('calibration_protocols',p),('calibration_runs',original)]:
        with pytest.raises(ValueError):env.cal.store.put(group,obj)
    assert not env.exp.store.list('retrieval_runs')

@pytest.mark.parametrize('change',[{'question':'电池购买八个月损坏如何维修？','group':'different'},
    {'question':'电池购买八个月损坏怎么维修？','group':'different'}, {'question':'完全不同的提问','group':'battery'}])
def test_related_answers_cannot_cross_partitions(env,change):
    with pytest.raises(ValueError,match='CROSS_PARTITION_FAMILY'):
        env.cal.create_dataset('bad split',[sample(),sample(change['question'],'HOLDOUT',change['group'])],[],True,'metric','cost')

def test_blind_view_hides_scores_and_machine_views_record_exposure(env):
    p=protocol(env);r=run(env,p);sid=env.dataset.samples[0].sample_id
    view=env.cal.run_view(r['run_id'],'synthetic-annotator')
    assert view['results']==[] and view['hidden_sample_count']==1
    blind=env.cal.open_blind(env.dataset.dataset_id,sid,env.rubric.rubric_id,'synthetic-annotator')
    assert set(blind['sample'])=={'question','context','answer','expected_facts','reference_complete','retrieved_evidence','reference_policy'}
    a=env.cal.annotate(env.dataset.dataset_id,sid,env.rubric.rubric_id,'synthetic-annotator','HUMAN','BLIND',judgment(),False,blind['blind_access_id'])
    assert a.independent
    env.cal.run_view(r['run_id'],'synthetic-annotator')
    later=annotate(env,env.dataset.samples[0],source='HUMAN')
    assert later.seen_machine and not later.independent
    assert env.cal.reference(env.dataset.dataset_id,env.rubric.rubric_id)[sid]['annotation_ids']==[a.annotation_id]

def test_ai_and_codex_do_not_enter_human_denominators(env):
    for source in ('AI','CODEX'):annotate(env,env.dataset.samples[0],actor=source,source=source)
    p=protocol(env);r=run(env,p)
    metrics=env.cal.run_view(r['run_id'],'CODEX')['metrics']
    assert metrics['coverage']['denominator']==1 and metrics['agreement']['denominator']==0
    assert metrics['health']['HUMAN_UNRESOLVED']==1

def test_human_disagreement_requires_adjudication_and_keeps_original_agreement(env):
    s=env.dataset.samples[0]
    a=annotate(env,s,actor='synthetic-a',source='HUMAN');b=annotate(env,s,actor='synthetic-b',source='HUMAN',value='FAIL')
    assert env.cal.reference(env.dataset.dataset_id,env.rubric.rubric_id)[s.sample_id]['state']=='DISAGREEMENT'
    env.cal.adjudicate(env.dataset.dataset_id,s.sample_id,env.rubric.rubric_id,[a.annotation_id,b.annotation_id],'synthetic-adjudicator','HUMAN',judgment(),'fixture adjudication')
    assert env.cal.reference(env.dataset.dataset_id,env.rubric.rubric_id)[s.sample_id]['state']=='ADJUDICATED'
    assert env.cal.human_agreement(env.dataset.dataset_id,env.rubric.rubric_id)['binary_agreement_before_adjudication']['value']==0

def test_invalid_quotes_parsing_and_interface_failures_are_separate(env):
    p=protocol(env);s=env.dataset.samples[0]
    async def evaluate():
        provider=ScriptedProvider(p.provider_configuration,'unused')
        ScriptedProvider.output='{bad JSON'
        parse=await score_answer(provider,p,env.rubric,s,1)
        ScriptedProvider.output=judgment();ScriptedProvider.output['dimensions']['faithfulness']['citations'][0]['quote']='not in frozen evidence'
        content=await score_answer(provider,p,env.rubric,s,1)
        ScriptedProvider.error='RATE_LIMITED'
        interface=await score_answer(provider,p,env.rubric,s,1)
        return parse,content,interface
    a,b,c=asyncio.run(evaluate())
    assert [r.status for r in (a,b,c)]==['PARSE_ERROR','CONTENT_INVALID','INTERFACE_ERROR']
    assert all(r.judgment is None for r in (a,b,c))

def test_denominators_all_failures_and_drill_down_recalculate():
    samples=[CalibrationSample.model_validate(sample(f'fixture {i}',group=f'g{i}',diagnostic=i==1)) for i in range(7)]
    hv=['PASS','FAIL','PASS','FAIL',None,'PENDING','FAIL'];mv=['PASS','PASS','FAIL','PENDING',None,None,'FAIL']
    refs={s.sample_id:{'state':'SINGLE','judgment':judgment(hv[i],critical=i in (1,3)) if hv[i] else None} for i,s in enumerate(samples)}
    results=[CalibrationResult(sample_id=s.sample_id,repetition=1,status='SUCCESS' if mv[i] else 'PARSE_ERROR' if i==4 else 'INTERFACE_ERROR',
        judgment=Judgment.model_validate(judgment(mv[i])) if mv[i] else None,request_count=1) for i,s in enumerate(samples)]
    m=metrics_with_slices(samples,results,refs,1)
    assert (m['agreement']['numerator'],m['agreement']['denominator'])==(2,4)
    assert (m['false_pass']['numerator'],m['false_pass']['denominator'])==(1,3)
    assert (m['false_fail']['numerator'],m['false_fail']['denominator'])==(1,2)
    assert (m['coverage']['numerator'],m['coverage']['denominator'])==(4,7)
    assert m['health']['PARSE_ERROR']==m['health']['INTERFACE_ERROR']==1
    assert m['health']['EVIDENCE_INSUFFICIENT']==1 and m['by_distribution']['diagnostic']['sample_count']==1
    assert len(m['coverage']['denominator_ids'])==7
    assert m['by_distribution']['actual_natural']['coverage']['value'] is None

def test_duplicate_submission_and_budget_have_no_extra_requests(env):
    p=protocol(env)
    with pytest.raises(ValueError,match='REQUEST_BUDGET_INVALID'): run(env,p,repetitions=2,budget=1)
    assert not ScriptedProvider.instances
    a=run(env,p);b=run(env,p)
    assert a['run_id']==b['run_id'] and sum(x.call_count for x in ScriptedProvider.instances)==1
    with pytest.raises(ValueError,match='IDEMPOTENCY_CONFLICT'):run(env,p,repetitions=2)

def test_bound_judge_lower_budget_rejected_before_calls_or_holdout_lock(env):
    child=env.exp.providers.create(ProviderConfig(provider='openai-compatible',base_url='http://127.0.0.1:8129/v1',
        model='child-fixture',max_calls=1),'child-fixture-memory-key')
    env.exp.store.put('provider_sessions',child.model_copy(update={'status':'READY','text_connection_status':'READY'}))
    bound=env.exp.providers.bind_judge(env.sid,child.provider_session_id)
    env.exp.store.put('provider_sessions',bound.model_copy(update={'status':'READY','text_connection_status':'READY'}))
    env.sid=bound.provider_session_id
    p1=protocol(env);p2=protocol(env,'J2',p1.protocol_id)
    with pytest.raises(ValueError,match='REQUEST_BUDGET_INVALID'):run(env,p1,repetitions=2,budget=2)
    with pytest.raises(ValueError,match='REQUEST_BUDGET_INVALID'):
        env.cal.lock(env.dataset.dataset_id,env.rubric.rubric_id,p1.protocol_id,p2.protocol_id,'fixture',2,4,'synthetic-annotator')
    assert not ScriptedProvider.instances and not env.cal.store.list('calibration_validations')

def test_concurrent_duplicate_returns_running_identity(env):
    p=protocol(env)
    async def exercise():
        ScriptedProvider.gate=asyncio.Event()
        first=asyncio.create_task(env.cal.run(env.dataset.dataset_id,env.rubric.rubric_id,p.protocol_id,env.sid,'concurrent',1,5))
        await asyncio.sleep(.02)
        duplicate=await env.cal.run(env.dataset.dataset_id,env.rubric.rubric_id,p.protocol_id,env.sid,'concurrent',1,5)
        assert duplicate['status']=='RUNNING'
        ScriptedProvider.gate.set();result=await first
        assert result['run_id']==duplicate['run_id']
    asyncio.run(exercise())
    assert sum(x.call_count for x in ScriptedProvider.instances)==1

def test_holdout_lock_final_budget_release_pending_report_and_no_reuse(env):
    for s in env.dataset.samples:annotate(env,s)
    p1=protocol(env);p2=protocol(env,'J2',p1.protocol_id)
    a=run(env,p1,'base');b=run(env,p2,'candidate')
    comparison=env.cal.compare(a['run_id'],b['run_id'],'synthetic-annotator')
    assert comparison.comparable and comparison.single_component_change and not comparison.attributable
    lock=env.cal.lock(env.dataset.dataset_id,env.rubric.rubric_id,p1.protocol_id,p2.protocol_id,'fixture selection',1,2,'synthetic-annotator')
    with pytest.raises(ValueError,match='REFERENCE_LOCKED'):annotate(env,env.dataset.samples[0])
    with pytest.raises(ValueError,match='CANDIDATE_LOCKED'):protocol(env,'J2')
    final=asyncio.run(env.cal.validate(lock.validation_id,env.sid,env.sid,'synthetic-annotator'))
    assert final.status=='COMPLETE' and final.released_at and len(final.run_ids)==2
    second=asyncio.run(env.cal.validate(lock.validation_id,env.sid,env.sid,'synthetic-annotator'))
    assert second==final and sum(x.call_count for x in ScriptedProvider.instances)==4
    with pytest.raises(ValueError,match='INDEPENDENT_HUMAN_REFERENCE_REQUIRED'):
        env.cal.conclude(final.comparison_id,'ADOPT','fixture','synthetic-annotator',final.validation_id)
    conclusion=env.cal.conclude(final.comparison_id,'KEEP_BASELINE','No real human research.','synthetic-annotator',final.validation_id)
    assert conclusion.research_status=='PENDING'
    export=env.cal.export(conclusion.conclusion_id)
    assert 'PENDING' in export['markdown'] and export['json']['report_snapshot']['access_records']
    assert 'fixture-memory-key' not in json.dumps(export)
    with pytest.raises(ValueError,match='HOLDOUT_ALREADY_EXPOSED'):
        env.cal.create_dataset('reused',[sample('如何申请开具发票？','HOLDOUT','new-id')],[],True,'metric','cost')

def test_rubric_changed_blocks_comparable_claim_and_requires_new_labels(env):
    annotate(env,env.dataset.samples[0]);p1=protocol(env);a=run(env,p1,'a')
    definition=deepcopy(RUBRIC_TEMPLATE);definition['rules']['minimum_scores']['relevance']=2
    r2=env.cal.create_rubric(definition,env.rubric.rubric_id)
    p2=env.cal.create_protocol(env.dataset.dataset_id,r2.rubric_id,env.sid,'new scale','J1','changed scale')
    b=asyncio.run(env.cal.run(env.dataset.dataset_id,r2.rubric_id,p2.protocol_id,env.sid,'b',1,10))
    with pytest.raises(ValueError,match='ANNOTATION_REQUIRED_BEFORE_RESULTS'):
        env.cal.compare(a['run_id'],b['run_id'],'synthetic-annotator')
    blind=env.cal.open_blind(env.dataset.dataset_id,env.dataset.samples[0].sample_id,r2.rubric_id,'synthetic-annotator')
    env.cal.annotate(env.dataset.dataset_id,env.dataset.samples[0].sample_id,r2.rubric_id,'synthetic-annotator','CODEX','BLIND',judgment(),False,blind['blind_access_id'])
    comp=env.cal.compare(a['run_id'],b['run_id'],'synthetic-annotator')
    assert not comp.comparable and 'RUBRIC_ID_CHANGED' in comp.reasons
    assert comp.metrics_after['agreement']['denominator']==0

def test_http_routes_reject_holdout_run_and_generic_artifact_leak(env):
    from experiments import api
    previous=api._service_provider
    configure(lambda:env.exp)
    app=FastAPI();app.include_router(router);app.include_router(api.router);install_validation_handler(app)
    try:
        with TestClient(app) as client:
            response=client.get('/experiments/calibration/template');assert response.status_code==200
            response=client.post('/experiments/calibration/runs',json={'dataset_id':env.dataset.dataset_id,
                'rubric_id':env.rubric.rubric_id,'protocol_id':'none','provider_session_id':env.sid,'request_id':'x',
                'budget':10,'partition':'HOLDOUT'})
            assert response.status_code==422
            assert client.get('/experiments/artifacts/calibration_runs').status_code==404
            assert client.get('/experiments/calibration_runs/any').status_code==404
    finally:configure(previous)

def test_historical_run_copies_original_answer_and_policy_not_current_knowledge(rag_env):
    rag=rag_env.rag
    ev=rag.create_evalset(rag_env.index.index_id,'historical fixture',[{'case_id':'opened','query':'拆了还能退吗？','relevant_document_ids':['opened']}])
    run=asyncio.run(rag.run(rag_env.sid,ev.retrieval_eval_set_id,verify_answers=True))
    rag.knowledge.create([{'document_id':'opened','text':'This is a different current policy.'}],'new version',rag_env.k.knowledge_dataset_id)
    cal=CalibrationService(rag_env.exp)
    dataset=cal.create_dataset('frozen historical fixture',[],[{'run_id':run.run_id,'case_id':'opened','group_id':'opened',
        'partition':'CALIBRATION','origin':'CONSTRUCTED','source_viewer':'original-viewer'}],True,'metric','cost')
    s=dataset.samples[0]
    assert s.answer==run.answer_results[0].turn_evidence[0].response
    assert s.reference_policy[0].text==rag_env.docs[0]['text']
    assert s.retrieved_evidence[0].text==run.case_results[0]['results'][0]['text']
    assert cal.exposed(dataset,s,'original-viewer') and not cal.exposed(dataset,s,'new-independent-annotator')
    assert not cal.store.list('calibration_annotations')

def test_two_workspaces_cannot_read_each_others_calibration(isolated_env):
    app,registry,a,b=isolated_env;app.include_router(router);boot(a);boot(b)
    app.router.routes.sort(key=lambda r:0 if r.path.startswith('/experiments/calibration/') else 1)
    response=a.post('/experiments/calibration/datasets',json={'name':'private calibration','samples':[sample()],
        'selections':[],'group_review_confirmed':True,'priority_metric':'metric','acceptable_cost':'cost'})
    assert response.status_code==200
    did=response.json()['dataset_id']
    assert b.get('/experiments/calibration/datasets/'+did).status_code==404
    assert b.get('/experiments/calibration/history').json()['datasets']==[]
    rubric=a.post('/experiments/calibration/rubrics',json={}).json()
    assert b.post('/experiments/calibration/blind-sessions',json={'dataset_id':did,
        'sample_id':response.json()['samples'][0]['sample_id'],'rubric_id':rubric['rubric_id'],'annotator_id':'other'}).status_code==404
