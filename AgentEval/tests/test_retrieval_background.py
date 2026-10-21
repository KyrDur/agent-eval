"""Long evaluation survives a short HTTP connection; GET never repeats calls."""
import asyncio
from uuid import uuid4
from fastapi import FastAPI
import httpx
import pytest
from test_retrieval import fixture,CASES
from experiments import api,retrieval_service
from experiments.retrieval_api import router
from experiments.retrieval_background import background

def environment(fixture,monkeypatch):
    rag,sid,_,index,_,_=fixture
    ev=rag.create_evalset(index.index_id,'Background API acceptance',CASES[:1])
    monkeypatch.setattr(rag.experiments,'retrieval',rag,raising=False)
    monkeypatch.setattr(api,'_service_provider',lambda:rag.experiments)
    app=FastAPI();app.include_router(router)
    app.state.retrieval_slots=asyncio.Semaphore(1)
    body={'provider_session_id':sid,'retrieval_eval_set_id':ev.retrieval_eval_set_id,
          'request_id':str(uuid4()),'verify_answers':True}
    return app,rag,body

def test_http_returns_before_model_finishes_and_polling_and_replay_do_not_repeat(fixture,monkeypatch):
    async def exercise():
        app,rag,body=environment(fixture,monkeypatch)
        gate=asyncio.Event();entered=asyncio.Event();original=retrieval_service.evaluate_answer
        async def held(*args,**kwargs):
            entered.set();await gate.wait();return await original(*args,**kwargs)
        monkeypatch.setattr(retrieval_service,'evaluate_answer',held)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as client:
            accepted=await asyncio.wait_for(client.post('/experiments/retrieval-run-tasks',json=body),2)
            assert accepted.status_code==202,accepted.text
            identifier=accepted.json()['run_id'];await asyncio.wait_for(entered.wait(),2)
            path=rag.store.path('retrieval_runs',identifier);before=path.read_bytes()
            for _ in range(3):
                current=await client.get('/experiments/retrieval-runs/'+identifier)
                assert current.json()['run']['status']=='RUNNING'
                assert current.json()['run']['provider_call_count']==0
            assert path.read_bytes()==before
            repeated=await client.post('/experiments/retrieval-run-tasks',json=body)
            assert repeated.json()['run_id']==identifier
            conflict=await client.post('/experiments/retrieval-run-tasks',json={**body,'verify_answers':False})
            assert conflict.status_code==409 and conflict.json()['detail']=='IDEMPOTENCY_CONFLICT'
            busy=await client.post('/experiments/retrieval-run-tasks',json={**body,'request_id':str(uuid4())})
            assert busy.status_code==409 and busy.json()['detail']=='WORKSPACE_BUSY'
            task=background(rag).pending[body['request_id']][2]
        # The client's connection is gone, but the accepted task still owns its lease.
        gate.set();await asyncio.wait_for(task,10)
        finished=rag.store.get('retrieval_runs',identifier)
        assert finished.status=='COMPLETE' and finished.provider_call_count==2
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as client:
            repeated=await client.post('/experiments/retrieval-run-tasks',json=body)
            assert repeated.json()['run_id']==identifier and repeated.json()['provider_call_count']==2
        assert not background(rag).pending and not app.state.retrieval_slots.locked()
    asyncio.run(exercise())

def test_disconnect_before_acceptance_does_not_cancel_task(fixture,monkeypatch):
    async def exercise():
        app,rag,body=environment(fixture,monkeypatch);body['verify_answers']=False
        entered=asyncio.Event();gate=asyncio.Event();original=rag.run
        async def held(**arguments):
            entered.set();await gate.wait();return await original(**arguments)
        monkeypatch.setattr(rag,'run',held)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as client:
            request=asyncio.create_task(client.post('/experiments/retrieval-run-tasks',json=body))
            await asyncio.wait_for(entered.wait(),2)
            task=background(rag).pending[body['request_id']][2]
            request.cancel()
            with pytest.raises(asyncio.CancelledError):await request
            assert not task.done()
            gate.set();await asyncio.wait_for(task,10)
        run=next(r for r in rag.store.list('retrieval_runs') if r.request_id==body['request_id'])
        assert run.status=='COMPLETE' and run.provider_call_count==0
    asyncio.run(exercise())

def test_shutdown_preserves_partial_progress_and_releases_capacity(fixture,monkeypatch):
    async def exercise():
        app,rag,body=environment(fixture,monkeypatch)
        entered=asyncio.Event()
        async def held(*args,**kwargs):entered.set();await asyncio.Event().wait()
        monkeypatch.setattr(retrieval_service,'evaluate_answer',held)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as client:
            response=await client.post('/experiments/retrieval-run-tasks',json=body)
            await asyncio.wait_for(entered.wait(),2)
            await background(rag).close()
        run=rag.store.get('retrieval_runs',response.json()['run_id'])
        assert run.status=='PARTIAL' and len(run.case_results)==1 and run.provider_call_count==0
        assert not background(rag).pending and not app.state.retrieval_slots.locked()
    asyncio.run(exercise())

def test_validation_error_is_returned_and_does_not_leak_a_slot(fixture,monkeypatch):
    async def exercise():
        app,rag,body=environment(fixture,monkeypatch)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as client:
            response=await client.post('/experiments/retrieval-run-tasks',json={**body,'retrieval_eval_set_id':'missing'})
            assert response.status_code==404
        assert not background(rag).pending and not app.state.retrieval_slots.locked()
    asyncio.run(exercise())
