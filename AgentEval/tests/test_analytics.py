"""Outcomes, deduplication, privacy and admin access are product requirements."""
from contextlib import asynccontextmanager
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest

from experiments.analytics import AnalyticsStore, AnalyticsMiddleware, response_outcome

@pytest.fixture
def analytics(tmp_path):
    token = tmp_path/'admin-token'
    token.write_text('synthetic-admin-token-for-tests-only-123456789')
    return AnalyticsStore(tmp_path/'analytics', token)

def test_aggregate_dedup_and_browser_exclusion(analytics):
    analytics.record('browser-a','page_view',session='visit-a',event_id='one',page='chat',referrer='https://example.com/private?q=secret')
    analytics.record('browser-a','page_view',session='visit-a',event_id='one',page='chat')
    analytics.record('browser-a','chat','SUCCESS')
    analytics.record('browser-a','chat','FAILED')
    analytics.record('browser-b','page_view',session='visit-b',page='welcome')
    r = analytics.report()
    assert r['totals']=={'pageviews':2,'visitors':2,'visits':2,'active_users':1}
    assert {x['referrer'] for x in r['referrers']}=={'example.com',''}
    analytics.exclude('browser-a',True)
    assert analytics.report()['totals']=={'pageviews':1,'visitors':1,'visits':1,'active_users':0}
    assert analytics.report(include_excluded=True)['totals']['pageviews']==2
    analytics.exclude('browser-a',False)
    assert analytics.report()['totals']['pageviews']==2
    with analytics.connect() as db:
        raw=json.dumps([tuple(r) for r in db.execute('SELECT * FROM events')])
        assert 'browser-a' not in raw and 'private' not in raw and 'secret' not in raw

def test_operation_outcome_is_not_http_success(analytics):
    assert response_outcome('api_connect',200,{'status':'AUTH_FAILED'})==('api_connect','FAILED')
    assert response_outcome('chat',200,{'status':'FAILED'})==('chat','FAILED')
    assert response_outcome('run',200,{'run_type':'BASELINE','status':'PARTIAL'})==('baseline','PARTIAL')
    assert response_outcome('run',200,{'run_type':'RETEST','status':'COMPLETE','answer_metrics':{'failed':8}})==('retest','SUCCESS')
    assert response_outcome('materials_generate',409,{'detail':'NARRATIVE_VALIDATION_FAILED'})==('materials_generate','FAILED')
    analytics.record('a','chat',source='historical')
    assert analytics.report()['events']==[]
    assert analytics.report(source='historical')['events'][0]['count']==1

def test_timezone_boundary_is_beijing(analytics):
    analytics.record('a','chat',timestamp='2026-10-10T16:01:00+00:00')
    with analytics.connect() as db:
        assert db.execute('SELECT day FROM events').fetchone()[0]=='2026-10-11'

@pytest.fixture
def client(analytics):
    app=FastAPI()
    app.state.analytics=analytics
    app.state.workspaces=SimpleNamespace(cookie='test-cookie',origin='https://example.test',known=lambda value:'browser-a' if value=='valid' else None)
    app.add_middleware(AnalyticsMiddleware)
    @app.post('/experiments/chat-turns')
    def chat():return {'turn_id':'same-immutable-turn','status':'SUCCESS','answer':'PRIVATE MODEL OUTPUT','api_key':'PRIVATE KEY'}
    @app.post('/experiments/provider-sessions/test-provider/test')
    def connect():return {'status':'AUTH_FAILED','private':'NOT FOR LOGGING'}
    @app.post('/experiments/career/materials/v2')
    def materials():
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'NARRATIVE_VALIDATION_FAILED'},status_code=409)
    with TestClient(app,base_url='https://example.test') as c:
        c.cookies.set('test-cookie','valid')
        yield c

def test_admin_token_is_separate_and_no_content_saved(client,analytics):
    assert client.get('/experiments/analytics/report').status_code==401
    assert client.get('/experiments/analytics/report',headers={'Authorization':'Bearer valid'}).status_code==401
    auth={'Authorization':'Bearer synthetic-admin-token-for-tests-only-123456789'}
    assert client.get('/experiments/analytics/report',headers=auth).status_code==200
    assert client.get('/experiments/analytics/report?days=1000',headers=auth).status_code==422
    client.post('/experiments/chat-turns',json={'message':'PRIVATE INPUT','api_key':'PRIVATE KEY'})
    client.post('/experiments/chat-turns',json={'message':'PRIVATE INPUT'})
    client.post('/experiments/provider-sessions/test-provider/test')
    client.post('/experiments/career/materials/v2')
    rows=analytics.report()['events']
    assert {(r['name'],r['outcome'],r['count']) for r in rows}=={('chat','SUCCESS',1),('api_connect','FAILED',1),('materials_generate','FAILED',1)}
    with analytics.connect() as db:
        raw=json.dumps([tuple(r) for r in db.execute('SELECT * FROM events')])
        assert 'PRIVATE' not in raw and 'same-immutable-turn' not in raw

def test_client_cannot_forge_business_success_or_other_browser(client,analytics):
    body={'name':'chat','page':'chat','session':'test-session','event_id':'one'}
    assert client.post('/experiments/analytics/events',json=body).status_code==422
    body['name']='page_view'
    assert client.post('/experiments/analytics/events',json={**body,'api_key':'secret'}).status_code==422
    assert client.post('/experiments/analytics/events',json=body,headers={'Origin':'https://evil.test'}).status_code==403
    assert client.post('/experiments/analytics/events',json=body).status_code==200
    assert client.post('/experiments/analytics/events',json=body).status_code==200
    assert analytics.report()['totals']['pageviews']==1
    assert client.post('/experiments/analytics/preference',json={'excluded':True}).status_code==200
    assert analytics.report()['totals']['pageviews']==0
    assert client.post('/experiments/analytics/preference',json={'excluded':'true'}).status_code==422
    client.cookies.clear()
    assert client.post('/experiments/analytics/events',json=body).status_code==403

def test_do_not_track(client,analytics):
    body={'name':'page_view','page':'welcome','session':'a','event_id':'a'}
    assert client.post('/experiments/analytics/events',json=body,headers={'DNT':'1'}).json()['recorded'] is False
    client.post('/experiments/chat-turns',headers={'DNT':'1'})
    assert analytics.report()['events']==[]

def test_real_product_workspace_and_analytics_coexist(tmp_path,monkeypatch):
    from experiments import api
    from experiments.app import app
    previous=api._service_provider
    token=tmp_path/'admin'
    token.write_text('synthetic-admin-token-for-tests-only-123456789')
    for key,value in {'AGENTEVAL_ANALYTICS_DIR':str(tmp_path/'analytics'),
        'AGENTEVAL_ANALYTICS_TOKEN_FILE':str(token),'AGENTEVAL_ANONYMOUS_WORKSPACES':'1',
        'AGENTEVAL_WORKSPACE_DIR':str(tmp_path/'workspaces'),'AGENTEVAL_PUBLIC_ORIGIN':'https://example.test',
        'AGENTEVAL_COOKIE_SECURE':'1'}.items():monkeypatch.setenv(key,value)
    try:
        with TestClient(app,base_url='https://example.test') as client:
            assert client.get('/experiments/workspace').status_code==200
            assert client.get('/experiments/analytics/report').status_code==401
            assert client.post('/experiments/knowledge-datasets',json={'name':'Test simulated knowledge',
                'documents':[{'document_id':'refund','title':'退款','text':'这是模拟业务资料。'}]}).status_code==200
            r=client.post('/experiments/analytics/events',json={'name':'page_view','page':'knowledge','session':'one','event_id':'one'})
            assert r.status_code==200
            report=app.state.analytics.report()
            assert report['totals']['pageviews']==1
            assert report['totals']['active_users']==1
            assert report['events'][0]['name']=='knowledge_save'
    finally:
        api._service_provider=previous
