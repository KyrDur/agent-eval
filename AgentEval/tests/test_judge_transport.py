"""Real adapter with an isolated HTTP transport, no vendor traffic."""
import asyncio
import json
import httpx
import pytest
from experiments.providers import ProviderConfig,ProviderFailure
from experiments.provider_transport import ObservedProvider
from experiments.judge_contract import response_format

@pytest.mark.parametrize('finish,stop',[('stop','end_turn'),('length','max_tokens'),('tool_calls','tool_use')])
@pytest.mark.parametrize('has_usage',[True,False])
def test_finish_reason_and_unknown_usage_are_preserved(finish,stop,has_usage):
    async def exercise():
        cfg=ProviderConfig(provider='openai-compatible',model='fixture',max_tokens=32)
        provider=ObservedProvider(cfg,'isolated-secret-1234')
        await provider._sdk._http.aclose()
        def reply(request):
            msg={'role':'assistant','content':'OK'}
            if finish=='tool_calls':msg.update(content=None,tool_calls=[{'id':'tool1','type':'function','function':{'name':'echo','arguments':'{"value":"x"}'}}])
            data={'id':'fixture-response','object':'chat.completion','model':'fixture-revision','choices':[{'index':0,'finish_reason':finish,'message':msg}]}
            if has_usage:data['usage']={'prompt_tokens':5,'completion_tokens':3}
            return httpx.Response(200,json=data)
        provider._sdk._http=httpx.AsyncClient(transport=httpx.MockTransport(reply))
        kwargs={}
        if finish=='tool_calls':kwargs['tools']=[{'name':'echo','description':'echo','input_schema':{'type':'object','properties':{'value':{'type':'string'}},'required':['value']}}]
        response=await provider.client('judge').messages.create(system='fixture',messages=[{'role':'user','content':'test'}],**kwargs)
        assert response.stop_reason==stop
        trace=provider.call_traces[0]
        assert trace['model_outputs']['provider_finish_reason']==finish
        assert trace['model_outputs']['stop_reason']==stop
        assert (trace['usage']['total_tokens'] if has_usage else trace['usage'])==(8 if has_usage else None)
        assert 'isolated-secret-1234' not in json.dumps(trace)
        await provider.close()
    asyncio.run(exercise())

@pytest.mark.parametrize('mode',['text','json_object','json_schema'])
def test_actual_format_is_in_transport_snapshot_and_budget(mode):
    async def exercise():
        cfg=ProviderConfig(provider='openai-compatible',model='fixture',judge_output_mode=mode,max_tokens=32)
        provider=ObservedProvider(cfg,'isolated-secret-1234');await provider._sdk._http.aclose();bodies=[]
        def reply(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(200,json={'id':'r','object':'chat.completion','model':'fixture','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'{}'}}]})
        provider._sdk._http=httpx.AsyncClient(transport=httpx.MockTransport(reply))
        spec=response_format(mode)
        await provider.client('judge').messages.create(system='fixture',messages=[{'role':'user','content':'test'}],**({'response_format':spec} if spec else {}))
        assert bodies[0].get('response_format')==spec
        assert provider.call_traces[0]['model_inputs'].get('response_format')==spec
        assert provider.call_traces[0]['input_budget']['input_upper_bound']>0
        await provider.close()
    asyncio.run(exercise())

def test_unsupported_structured_format_never_silently_falls_back():
    async def exercise():
        cfg=ProviderConfig(provider='openai-compatible',model='fixture',judge_output_mode='json_schema')
        provider=ObservedProvider(cfg,'isolated-secret-1234');await provider._sdk._http.aclose();calls=[]
        def reply(request):
            calls.append(request)
            return httpx.Response(400,json={'error':{'code':'unsupported_parameter','param':'response_format'}})
        provider._sdk._http=httpx.AsyncClient(transport=httpx.MockTransport(reply))
        with pytest.raises(ProviderFailure,match='FORMAT_MODE_UNSUPPORTED'):
            await provider.client('judge').messages.create(system='fixture',messages=[{'role':'user','content':'test'}],response_format=response_format('json_schema'))
        assert len(calls)==1
        assert provider.call_traces[0]['error']=='FORMAT_MODE_UNSUPPORTED'
        await provider.close()
    asyncio.run(exercise())
