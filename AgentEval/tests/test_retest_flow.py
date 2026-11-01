"""Real index/run receipts: one confirmation, replay, cancellation and recovery."""
import asyncio
from uuid import uuid4
import pytest
from test_retrieval import fixture,CASES
from experiments import retest_flow,retrieval_service
from experiments.retrieval_background import background

async def baseline(fixture):
    rag,sid,_,index,_,_=fixture
    ev=rag.create_evalset(index.index_id,'UX flow acceptance (scripted provider)',CASES[:1])
    base=await rag.run(sid,ev.retrieval_eval_set_id,retrieval_config={'top_k':1},verify_answers=True)
    inputs={'baseline_run_id':base.run_id,'provider_session_id':sid,'change_type':'TOP_K_CHANGE',
        'after_config':{**base.retrieval_config.model_dump(),'top_k':2},'reason':'系统整理的待验证方案；用户选择检查资料条数。',
        'selected_case_ids':[base.execution_order[0]],'user_confirmed':True,'target_index_id':None,'prepare_index':None}
    return rag,base,inputs

async def finish(rag,identifier):
    for _ in range(160):
        flow=retest_flow.read(rag,identifier)
        if flow.stage in retest_flow.TERMINAL:return flow
        await asyncio.sleep(.1)
    raise AssertionError(retest_flow.read(rag,identifier).model_dump())

def test_one_confirmation_preserves_raw_logs_and_replay_never_repeats(fixture):
    async def exercise():
        rag,base,inputs=await baseline(fixture);identifier=str(uuid4());slots=asyncio.Semaphore(1)
        raw=rag.store.path('retrieval_runs',base.run_id).read_bytes()
        first=await retest_flow.submit(rag,identifier,inputs,slots)
        assert first.stage=='SAVED' and first.confirmed_scope['case_ids']==base.execution_order
        assert first.confirmed_scope['estimated_requests']==2
        assert first.confirmed_scope['cost']=='UNKNOWN'
        result=await finish(rag,identifier)
        assert result.stage=='COMPLETE',result.model_dump()
        run=rag.store.get('retrieval_runs',result.run_id)
        assert run.provider_call_count==2 and run.change_id==result.change_id
        assert result.comparison_id and run.case_results[0]['provider_call_traces']
        assert rag.store.path('retrieval_runs',base.run_id).read_bytes()==raw
        count=len(rag.store.list('retrieval_runs'))
        for _ in range(3):
            assert (await retest_flow.submit(rag,identifier,inputs,slots)).run_id==run.run_id
            assert (await retest_flow.resume(rag,identifier,slots)).run_id==run.run_id
        assert len(rag.store.list('retrieval_runs'))==count
        with pytest.raises(ValueError,match='IDEMPOTENCY_CONFLICT'):
            await retest_flow.submit(rag,identifier,{**inputs,'reason':'different confirmed plan'},slots)
    asyncio.run(exercise())

def test_refresh_reconciles_an_existing_running_receipt(fixture,monkeypatch):
    async def exercise():
        rag,_,inputs=await baseline(fixture);identifier=str(uuid4());slots=asyncio.Semaphore(1)
        gate=asyncio.Event();entered=asyncio.Event();original=retrieval_service.evaluate_answer
        async def held(*args,**kwargs):entered.set();await gate.wait();return await original(*args,**kwargs)
        monkeypatch.setattr(retrieval_service,'evaluate_answer',held)
        await retest_flow.submit(rag,identifier,inputs,slots)
        await asyncio.wait_for(entered.wait(),5)
        await asyncio.sleep(.05)
        await retest_flow.close(rag)  # Orchestrator stopped; existing worker keeps its own receipt.
        flow=retest_flow.read(rag,identifier);assert flow.stage=='UNKNOWN'
        run=background(rag).saved('run_'+identifier);assert run and run.status=='RUNNING'
        gate.set()
        await retest_flow.resume(rag,identifier,slots)
        flow=await finish(rag,identifier)
        assert flow.stage=='COMPLETE' and flow.run_id==run.run_id
        assert rag.store.get('retrieval_runs',run.run_id).provider_call_count==2
        assert len([r for r in rag.store.list('retrieval_runs') if r.request_id=='run_'+identifier])==1
    asyncio.run(exercise())

def test_cancel_stops_new_dispatch_and_preserves_partial_records(fixture,monkeypatch):
    async def exercise():
        rag,_,inputs=await baseline(fixture);identifier=str(uuid4());slots=asyncio.Semaphore(1)
        gate=asyncio.Event();entered=asyncio.Event();original=retrieval_service.evaluate_answer
        async def held(*args,**kwargs):entered.set();await gate.wait();return await original(*args,**kwargs)
        monkeypatch.setattr(retrieval_service,'evaluate_answer',held)
        await retest_flow.submit(rag,identifier,inputs,slots);await asyncio.wait_for(entered.wait(),5)
        await retest_flow.cancel(rag,identifier);gate.set()
        result=await finish(rag,identifier)
        assert result.stage=='CANCELLED'
        run=rag.store.get('retrieval_runs',result.run_id)
        assert run.status=='PARTIAL' and run.provider_call_count==0
        assert len(run.case_results)==1 and result.comparison_id
    asyncio.run(exercise())

def test_invalid_scope_never_starts_index_or_paid_run(fixture):
    async def exercise():
        rag,_,inputs=await baseline(fixture)
        before=len(rag.store.list('retrieval_runs'))
        with pytest.raises(ValueError,match='FLOW_CHANGE_SCOPE_INVALID'):
            await retest_flow.submit(rag,str(uuid4()),{**inputs,'after_config':{**inputs['after_config'],'rerank':True}},asyncio.Semaphore(1))
        with pytest.raises(ValueError,match='FLOW_SCOPE_INVALID'):
            await retest_flow.submit(rag,str(uuid4()),{**inputs,'selected_case_ids':['not-in-baseline']},asyncio.Semaphore(1))
        assert len(rag.store.list('retrieval_runs'))==before
    asyncio.run(exercise())

def test_chunk_preparation_reuses_the_existing_index_receipt(fixture):
    async def exercise():
        rag,base,inputs=await baseline(fixture);old=base.controls['index_snapshot'];identifier=str(uuid4())
        inputs.update(change_type='CHUNKING_CHANGE',after_config=base.retrieval_config.model_dump(),prepare_index={
            'dataset_id':old['knowledge_dataset_id'],'version':old['knowledge_version'],
            'chunk_config':{**old['chunk_config'],'algorithm':'source-section-v1'},'embedding_model':old['embedding_snapshot']['model']})
        await retest_flow.submit(rag,identifier,inputs,asyncio.Semaphore(1));result=await finish(rag,identifier)
        assert result.stage=='COMPLETE',result.model_dump()
        assert result.index_job_id and result.index_id
        job=rag.store.get('index_builds',result.index_job_id)
        assert job.request_id=='idx_'+identifier and job.status=='READY'
        assert rag.store.get('retrieval_runs',result.run_id).controls['knowledge_snapshot']==base.controls['knowledge_snapshot']
    asyncio.run(exercise())


def test_two_tabs_cannot_start_two_sequences_for_the_same_baseline(fixture,monkeypatch):
    async def exercise():
        rag,_,inputs=await baseline(fixture);identifier=str(uuid4());slots=asyncio.Semaphore(1)
        gate=asyncio.Event();entered=asyncio.Event();original=retrieval_service.evaluate_answer
        async def held(*args,**kwargs):entered.set();await gate.wait();return await original(*args,**kwargs)
        monkeypatch.setattr(retrieval_service,'evaluate_answer',held)
        await retest_flow.submit(rag,identifier,inputs,slots);await asyncio.wait_for(entered.wait(),5)
        with pytest.raises(ValueError,match='WORKSPACE_BUSY'):
            await retest_flow.submit(rag,str(uuid4()),inputs,slots)
        gate.set();assert (await finish(rag,identifier)).stage=='COMPLETE'
    asyncio.run(exercise())


def test_source_positions_are_checked_against_exact_unicode_original():
    from experiments.rag_evidence import coverage,SourceEvidence
    docs=[{'document_id':'p','text':'😀政策：七日内可退。'}]
    with pytest.raises(ValueError):SourceEvidence(document_id='p',quote='七日内',source_start=4)
    wrong={'facts':[{'fact_id':'f','description':'七日内','alternatives':[[{'document_id':'p','quote':'七日内','source_start':0,'source_end':3,'offset_unit':'UNICODE_CODEPOINT'}]]}]}
    assert coverage(wrong,docs)['included_count']==0


def test_legacy_pending_retest_blocks_a_new_flow_until_its_receipt_finishes(fixture,monkeypatch):
    async def exercise():
        rag,base,inputs=await baseline(fixture);slots=asyncio.Semaphore(2)
        change=rag.propose_change(base.run_id,'TOP_K_CHANGE',inputs['after_config'],inputs['reason'],inputs['selected_case_ids'],True)
        rag.apply(change.change_id)
        gate=asyncio.Event();entered=asyncio.Event();original=retrieval_service.evaluate_answer
        async def held(*args,**kwargs):entered.set();await gate.wait();return await original(*args,**kwargs)
        monkeypatch.setattr(retrieval_service,'evaluate_answer',held)
        request_id=str(uuid4())
        await background(rag).submit({'provider_session_id':inputs['provider_session_id'],'retrieval_eval_set_id':base.controls['eval_set_snapshot']['retrieval_eval_set_id'],
            'run_type':'RETEST','parent_run_id':base.run_id,'change_id':change.change_id,'verify_answers':True,'request_id':request_id},slots)
        await asyncio.wait_for(entered.wait(),5)
        with pytest.raises(ValueError,match='WORKSPACE_BUSY'):
            await retest_flow.submit(rag,str(uuid4()),inputs,slots)
        task=background(rag).pending[request_id][2];gate.set();await asyncio.wait_for(task,10)
    asyncio.run(exercise())
