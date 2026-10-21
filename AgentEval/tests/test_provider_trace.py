"""Real transport validation and safe, case-bound diagnostic evidence."""
import asyncio
import json
from copy import deepcopy
import httpx
import pytest
from experiments.provider_trace import snapshot
from experiments.provider_transport import ObservedProvider
from experiments.providers import ProviderConfig, ProviderFailure
from experiments.store import safe_artifact
from experiments.practice_models import ChatTurn
from experiments.practice_service import PracticeService
from test_retrieval import fixture


def test_trace_redacts_nested_credentials_and_bounds_without_changing_request():
    key='private-test-credential-123456'
    data={'system':'请检查 '+key,'messages':[{'role':'user','content':'x'*15000}],
          'parameters':{'authorization':'Bearer '+key,'apiKey':key},key:'dynamic field'}
    original=deepcopy(data)
    result=snapshot(data,(key,))
    assert data==original and result['redacted'] and result['truncated']
    assert key not in json.dumps(result) and len(result['data']['messages'][0]['content'])<12100
    safe_artifact(result,(key,))


@pytest.mark.parametrize('usage',[{'prompt_tokens':12,'completion_tokens':3},None])
def test_actual_usage_or_unknown_never_internal_placeholder_zero(usage):
    async def check():
        p=ObservedProvider(ProviderConfig(provider='openai-compatible',model='test',base_url='http://127.0.0.1:1/v1'),'private-key-123456')
        def respond(request):
            body={'object':'chat.completion','id':'real-id','model':'returned-test',
                  'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'有效回答'}}]}
            if usage is not None:body['usage']=usage
            return httpx.Response(200,json=body)
        await p._sdk._http.aclose()
        p._sdk._http=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            await p.client('general').messages.create(system='RAG_ANSWER_V1: 测试',messages=[{'role':'user','content':'问题'}])
            event=p.call_traces[0]
            assert event['status']=='SUCCESS' and event['operation']=='ANSWER' and event['latency_ms']>=0
            assert event['model_inputs']['messages'][0]['content']=='问题'
            assert event['model_outputs']['content'][0]['text']=='有效回答'
            assert event['usage']==({'input_tokens':12,'output_tokens':3,'total_tokens':15} if usage else None)
            assert len(p.observations)==1 and 'model_inputs' not in p.observations[0]
        finally:await p.close()
    asyncio.run(check())


def test_failure_trace_is_not_successful_response_evidence_and_usage_is_unknown():
    async def check():
        key='private-key-123456'
        p=ObservedProvider(ProviderConfig(provider='openai-compatible',model='test',base_url='http://127.0.0.1:1/v1'),key)
        def respond(request):return httpx.Response(401,json={'error':{'message':'Bearer '+key}})
        await p._sdk._http.aclose();p._sdk._http=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            with pytest.raises(ProviderFailure,match='AUTH_FAILED'):
                await p.client('general').messages.create(system='RAG_ANSWER_V1: 测试',messages=[{'role':'user','content':'问题'}])
            assert not p.observations
            assert p.call_traces[0]['status']=='FAILED' and p.call_traces[0]['error']=='AUTH_FAILED'
            assert p.call_traces[0]['usage'] is None and p.call_traces[0]['model_outputs'] is None
            safe_artifact(p.call_traces,(key,))
        finally:await p.close()
    asyncio.run(check())


def test_multiple_cases_keep_their_own_calls_and_stage_times(fixture):
    rag,sid,_,index,_,key=fixture
    ev=rag.create_evalset(index.index_id,'diagnostic test',[
        {'case_id':'d1','query':'拆了还能退吗？','relevant_document_ids':['opened']},
        {'case_id':'d2','query':'钱什么时候回到卡里？','relevant_document_ids':['refund']},
    ])
    run=asyncio.run(rag.run(sid,ev.retrieval_eval_set_id,retrieval_config={'query_rewrite':True,'rerank':True},verify_answers=True))
    assert run.status=='COMPLETE'
    seen=set()
    for row in run.case_results:
        calls=row['provider_call_traces']
        assert [c['operation'] for c in calls]==['QUERY_REWRITE','RERANK','ANSWER','JUDGE']
        assert all(c['case_id']==row['case_id'] and c['usage']['total_tokens']==2 for c in calls)
        ids={c['call_id'] for c in calls}
        assert not seen & ids;seen |= ids
        assert [s['operation'] for s in row['steps']]==['QUERY_REWRITE','RETRIEVAL','RERANK']
        assert all(s['status']=='SUCCESS' and s['latency_ms']>=0 for s in row['steps'])
        assert row['case_latency_ms']>=row['latency_ms']
    safe_artifact(run.model_dump(mode='json'),(key,))


def test_independent_judge_trace_keeps_actual_usage_and_redacts_both_credentials():
    async def check():
        general_key,judge_key='general-private-credential','judge-private-credential'
        judge=ProviderConfig(provider='openai-compatible',model='independent-judge',base_url='http://127.0.0.1:1/v1')
        config=ProviderConfig(provider='openai-compatible',model='general',base_url='http://127.0.0.1:1/v1',
            judge_provider_session_id='independent_judge',judge_provider_configuration=judge.model_dump())
        p=ObservedProvider(config,general_key,judge_key)
        def respond(request):
            assert request.headers['Authorization']=='Bearer '+judge_key
            return httpx.Response(200,json={'object':'chat.completion','id':'judge-id','model':'independent-judge',
                'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'评测输出'}}],
                'usage':{'prompt_tokens':12,'completion_tokens':3}})
        await p._judge._sdk._http.aclose();p._judge._sdk._http=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            await p.client('judge').messages.create(system='测试 Judge',messages=[{'role':'user','content':general_key}])
            event=p.call_traces[0]
            assert event['requested_model']=='independent-judge' and event['operation']=='JUDGE'
            assert event['usage']['total_tokens']==15 and event['content_redacted']
            safe_artifact(p.call_traces,(general_key,judge_key))
        finally:await p.close()
    asyncio.run(check())


def test_old_chat_shape_stays_unchanged_when_new_traces_were_never_recorded(fixture):
    rag,sid,_,index,_,_=fixture
    turn=asyncio.run(PracticeService(rag).chat(sid,index.index_id,'拆了还能退吗？'))
    new=turn.model_dump(mode='json')
    assert new['provider_call_traces']
    old={k:v for k,v in new.items() if k!='provider_call_traces'}
    loaded=ChatTurn.model_validate(old)
    assert loaded.provider_call_traces==[]
    assert loaded.model_dump(mode='json')==old
