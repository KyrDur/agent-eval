import asyncio
import json
from types import SimpleNamespace
import httpx
import pytest
from experiments import site_provider as site
from experiments.providers import ProviderSessions
from experiments.store import JsonStore

@pytest.fixture
def shared(tmp_path, monkeypatch):
    key='synthetic-shared-credential-only'
    path=tmp_path/'private-key';path.write_text(key)
    monkeypatch.setenv('AGENTEVAL_SITE_API_KEY_FILE',str(path))
    monkeypatch.setattr(site,'_cached',None)
    monkeypatch.setattr(site,'_lock',asyncio.Lock())
    return key

@pytest.mark.parametrize('value,expected',[(True,'AVAILABLE'),(False,'NO_BALANCE'),(None,'CHECK_FAILED')])
def test_balance_uses_official_endpoint_without_returning_account_details(shared,monkeypatch,value,expected):
    calls=[]
    def handler(request):
        calls.append(request)
        assert str(request.url)=='https://api.deepseek.com/user/balance'
        assert request.headers['authorization']=='Bearer '+shared
        return httpx.Response(200,json={'is_available':value,'balance_infos':[{'total_balance':'123'}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(site.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    async def exercise():
        result=await site.check();assert result['status']==expected
        assert shared not in json.dumps(result) and '123' not in json.dumps(result)
        await site.check();assert len(calls)==1
    asyncio.run(exercise())

def test_no_config_or_failed_balance_never_creates_a_session(monkeypatch):
    monkeypatch.delenv('AGENTEVAL_SITE_API_KEY_FILE',raising=False)
    monkeypatch.setattr(site,'service',lambda:pytest.fail('must not create a session'))
    assert asyncio.run(site.connect())=={'status':'NOT_CONFIGURED','available':False}
    async def no_balance():return {'status':'NO_BALANCE','available':False}
    monkeypatch.setattr(site,'availability',no_balance)
    assert asyncio.run(site.connect())['status']=='NO_BALANCE'

def test_shared_sessions_stay_private_and_key_never_persists(shared,monkeypatch,tmp_path):
    providers=ProviderSessions(JsonStore(tmp_path/'artifacts'))
    monkeypatch.setattr(site,'service',lambda:SimpleNamespace(providers=providers))
    async def available():return {'status':'AVAILABLE','available':True}
    async def tested(identifier):return {'status':'SUCCESS'}
    monkeypatch.setattr(site,'availability',available);monkeypatch.setattr(providers,'test',tested)
    first=asyncio.run(site.connect());second=asyncio.run(site.connect())
    assert first['session']['provider_session_id']==second['session']['provider_session_id']
    assert shared not in json.dumps(first)
    assert all(shared not in p.read_text() for p in (tmp_path/'artifacts').rglob('*.json'))
    other=ProviderSessions(JsonStore(tmp_path/'other'))
    with pytest.raises(FileNotFoundError):other.get(first['session']['provider_session_id'])
