"""Single-case trials never become batch comparisons or rewrite sealed baselines."""
import asyncio
from uuid import uuid4
import pytest
from test_retrieval import fixture, CASES
from experiments import retest_flow
from experiments.rag_case_execution import run_cases

async def finish(rag,identifier):
    for _ in range(200):
        value=retest_flow.read(rag,identifier)
        if value.stage in retest_flow.TERMINAL:return value
        await asyncio.sleep(.05)
    raise AssertionError(retest_flow.read(rag,identifier).model_dump())

def test_trial_then_explicit_full_run_reuses_plan_but_reruns_every_case(fixture):
    async def exercise():
        rag,sid,_,index,_,_=fixture
        ev=rag.create_evalset(index.index_id,'Single then batch',CASES[:2])
        base=await rag.run(sid,ev.retrieval_eval_set_id,retrieval_config={'top_k':1},verify_answers=True)
        original=rag.store.path('retrieval_runs',base.run_id).read_bytes()
        inputs={'baseline_run_id':base.run_id,'provider_session_id':sid,'change_type':'TOP_K_CHANGE',
            'after_config':{**base.retrieval_config.model_dump(),'top_k':2},'reason':'先验证本题再检查其他题',
            'selected_case_ids':[base.execution_order[1]],'user_confirmed':True,'target_index_id':None,'prepare_index':None,'execution_mode':'TRIAL'}
        capacity=asyncio.Semaphore(1);trial_id=str(uuid4())
        await retest_flow.submit(rag,trial_id,inputs,capacity)
        trial=await finish(rag,trial_id)
        assert trial.stage=='COMPLETE' and trial.comparison_id is None
        assert trial.confirmed_scope['case_ids']==inputs['selected_case_ids']
        run=rag.store.get('retrieval_trial_runs',trial.run_id)
        assert run.execution_order==inputs['selected_case_ids'] and run.provider_call_count==2
        assert len(run.case_results)==len(run.answer_results)==1
        assert run.experiment_identity['operation']=='SINGLE_CASE_TRIAL'
        assert not any(r.run_id==run.run_id for r in rag.store.list('retrieval_runs'))
        assert rag.view(run.run_id,_group='retrieval_trial_runs')['trusted_result']['sample_flow']['coverage']['denominator']==1
        assert (await retest_flow.submit(rag,trial_id,inputs,capacity)).run_id==run.run_id
        full_inputs={**inputs,'execution_mode':'FULL','trial_flow_id':trial_id}
        with pytest.raises(ValueError,match='TRIAL_PLAN_CHANGED'):
            await retest_flow.submit(rag,str(uuid4()),{**full_inputs,'after_config':{**inputs['after_config'],'top_k':3}},capacity)
        full_id=str(uuid4());await retest_flow.submit(rag,full_id,full_inputs,capacity)
        full=await finish(rag,full_id)
        assert full.stage=='COMPLETE',full.model_dump()
        assert full.change_id==trial.change_id and full.comparison_id
        full_run=rag.store.get('retrieval_runs',full.run_id)
        assert full_run.execution_order==base.execution_order and full_run.provider_call_count==4
        assert full_run.runtime_end_check['case_concurrency']==3
        assert rag.store.path('retrieval_runs',base.run_id).read_bytes()==original
    asyncio.run(exercise())

def test_three_case_parallel_bound_and_no_orphaned_tasks_on_cancel():
    async def exercise():
        active=0;peak=0;finished=[]
        async def work(item):
            nonlocal active,peak
            active+=1;peak=max(peak,active)
            try:await asyncio.sleep(.02);finished.append(item)
            finally:active-=1
        await run_cases(range(8),work)
        assert peak==3 and sorted(finished)==list(range(8)) and active==0
        async def interrupt(item):
            nonlocal active
            active+=1
            try:
                if item==0:await asyncio.sleep(.01);raise asyncio.CancelledError()
                await asyncio.sleep(1)
            finally:active-=1
        with pytest.raises(asyncio.CancelledError):await run_cases(range(8),interrupt)
        assert active==0
    asyncio.run(exercise())

def test_parallel_run_keeps_one_global_budget_and_each_cases_own_trace(fixture):
    async def exercise():
        rag,sid,_,index,_,_=fixture
        ev=rag.create_evalset(index.index_id,'Shared budget',CASES[:4])
        run=await rag.run(sid,ev.retrieval_eval_set_id,verify_answers=True,_request_limit=3)
        assert run.provider_call_count<=3
        calls=[call for row in run.case_results for call in row['provider_call_traces']]
        assert len(calls)==run.provider_call_count
        for row in run.case_results:
            assert all(c['case_id']==row['case_id'] for c in row['provider_call_traces'])
        assert run.execution_order==[c.case_id for c in sorted(ev.cases,key=lambda c:c.case_id)]
        assert [c['case_id'] for c in run.case_results]==run.execution_order
    asyncio.run(exercise())

def test_index_trial_and_full_batch_build_the_alternate_index_only_once(fixture):
    async def exercise():
        rag,sid,_,index,_,_=fixture
        ev=rag.create_evalset(index.index_id,'Chunk trial',CASES[:2])
        base=await rag.run(sid,ev.retrieval_eval_set_id,retrieval_config={'top_k':1})
        inputs={'baseline_run_id':base.run_id,'provider_session_id':sid,'change_type':'CHUNKING_CHANGE',
            'after_config':base.retrieval_config.model_dump(),'reason':'更换切法后先试本题','selected_case_ids':[base.execution_order[0]],
            'user_confirmed':True,'target_index_id':None,'execution_mode':'TRIAL',
            'prepare_index':{'dataset_id':index.knowledge_dataset_id,'version':index.knowledge_version,
                'chunk_config':{**index.chunk_config.model_dump(),'algorithm':'source-section-v1'},'embedding_model':index.embedding_snapshot['model']}}
        capacity=asyncio.Semaphore(1);identifier=str(uuid4())
        await retest_flow.submit(rag,identifier,inputs,capacity);trial=await finish(rag,identifier)
        assert trial.stage=='COMPLETE',trial.model_dump()
        jobs=len(rag.store.list('index_builds'))
        full_id=str(uuid4())
        await retest_flow.submit(rag,full_id,{**inputs,'execution_mode':'FULL','trial_flow_id':identifier},capacity)
        full=await finish(rag,full_id)
        assert full.stage=='COMPLETE',full.model_dump()
        assert full.change_id==trial.change_id and len(rag.store.list('index_builds'))==jobs
    asyncio.run(exercise())

def test_old_program_allows_exploratory_trial_but_never_formal_comparison(fixture,monkeypatch):
    from experiments import retrieval_service,scoring_profiles
    async def exercise():
        rag,sid,_,index,_,_=fixture
        ev=rag.create_evalset(index.index_id,'Old program trial',CASES[:2])
        base=await rag.run(sid,ev.retrieval_eval_set_id,retrieval_config={'top_k':1},verify_answers=True,
            scoring_profile_id=scoring_profiles.INITIAL_ID)
        original=rag.store.path('retrieval_runs',base.run_id).read_bytes()
        current={**retrieval_service.implementation_snapshot(),'test_runtime_revision':'next'}
        monkeypatch.setattr(retrieval_service,'implementation_snapshot',lambda:current)
        monkeypatch.setattr(scoring_profiles,'ALIAS_PROMPT',scoring_profiles.ALIAS_PROMPT+'\n当前程序协议修复。')
        inputs={'baseline_run_id':base.run_id,'provider_session_id':sid,'change_type':'TOP_K_CHANGE',
            'after_config':{**base.retrieval_config.model_dump(),'top_k':2},'reason':'只探索当前题，不把旧评分差异当改善',
            'selected_case_ids':[base.execution_order[0]],'user_confirmed':True,'target_index_id':None,'prepare_index':None,'execution_mode':'TRIAL'}
        identifier=str(uuid4());capacity=asyncio.Semaphore(1)
        await retest_flow.submit(rag,identifier,inputs,capacity)
        flow=await finish(rag,identifier)
        assert flow.stage=='COMPLETE',flow.model_dump()
        run=rag.store.get('retrieval_trial_runs',flow.run_id)
        assert len(run.case_results)==1 and run.provider_call_count==2 and flow.comparison_id is None
        assert run.controls['evaluation_scope']['historical_reference_only'] is True
        assert run.experiment_identity['comparison_eligible'] is False
        assert 'retrieval_implementation' in run.experiment_identity['baseline_control_changes']
        assert 'scoring_profile.protocol' in run.experiment_identity['baseline_control_changes']
        assert run.controls['retrieval_implementation']==current
        assert run.controls['scoring_profile']!=base.controls['scoring_profile']
        assert 'HISTORICAL_BASELINE_REFERENCE_ONLY' in run.warnings
        with pytest.raises(ValueError,match='BASELINE_IMPLEMENTATION_CHANGED'):
            await retest_flow.submit(rag,str(uuid4()),{**inputs,'execution_mode':'FULL','trial_flow_id':identifier},capacity)
        assert rag.store.path('retrieval_runs',base.run_id).read_bytes()==original
    asyncio.run(exercise())

def test_exploratory_trial_does_not_relax_data_or_rubric_controls():
    from experiments.retrieval_service import trial_reference_controls
    old={'retrieval_implementation':{'a':'old'},'knowledge_snapshot':{'version':1},
        'scoring_profile':{'profile_id':'frozen','rubric':{'hash':'old'},'protocol':{'prompt':'old'},'content_hash':'old'}}
    new={'retrieval_implementation':{'a':'new'},'knowledge_snapshot':{'version':2},
        'scoring_profile':{'profile_id':'frozen','rubric':{'hash':'new'},'protocol':{'prompt':'new'},'content_hash':'new'}}
    reference,changes=trial_reference_controls(old,new)
    assert reference!=new
    assert reference['knowledge_snapshot']==old['knowledge_snapshot']
    assert reference['scoring_profile']['rubric']==old['scoring_profile']['rubric']
    assert old['scoring_profile']['protocol']['prompt']=='old'
