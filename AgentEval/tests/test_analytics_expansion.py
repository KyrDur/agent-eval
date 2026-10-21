from contextlib import asynccontextmanager
from datetime import datetime,timedelta,timezone
import json,time,uuid
from pathlib import Path
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from experiments.analytics import AnalyticsStore,AnalyticsMiddleware,PAGES,response_outcome,business_event
from experiments import analytics_v2 as v2

@pytest.fixture
def runtime(tmp_path):
 store=AnalyticsStore(tmp_path/'analytics');app=FastAPI();app.state.analytics=store
 app.state.workspaces=SimpleNamespace(cookie='test-cookie',origin='https://test.example',known=lambda token:token if token in {'browser-a','browser-b'} else None)
 app.add_middleware(AnalyticsMiddleware)
 @app.post('/experiments/chat-turns')
 def chat():return {'turn_id':'PRIVATE-BUSINESS-ID','status':'SUCCESS','answer':'PRIVATE ANSWER'}
 @app.post('/experiments/interview-attempts')
 def interview():return {'attempt_id':str(uuid.uuid4()),'answer':'PRIVATE ANSWER'}
 @app.post('/experiments/provider-sessions/session/test-tools')
 def tools():return {'tool_call_capability':'VERIFIED'}
 with TestClient(app,base_url='https://test.example') as client:
  client.cookies.set('test-cookie','browser-a');yield client,store

def row(stage='submitted',op='op-a',action='chat.send',**extra):
 return dict(stage=stage,action=action,page='chat',page_visit='page-a',session='visit-a',event_id=str(uuid.uuid4()),placement='ChatPage.control_10',path='RETRIEVAL',entry='in_page',material='unknown',role='main',context='unknown',reason='none',state='none',operation=op,retry_of='',duration_ms=0,**extra)

def headers(op='op-a',action='chat.send'):
 return {'X-AE-Operation':op,'X-AE-Action':action,'X-AE-Page':'chat','X-AE-Visit':'page-a','X-AE-Session':'visit-a','X-AE-Placement':'ChatPage.control_10','X-AE-Path':'RETRIEVAL','X-AE-Entry':'in_page'}

def test_client_whitelist_and_no_business_forgery(runtime):
 client,store=runtime
 for bad in [dict(row(),stage='result'),dict(row(),stage='received'),dict(row(),outcome='SUCCESS'),dict(row(),action='PRIVATE LABEL'),dict(row(),reason='PRIVATE ERROR'),dict(row(),material='PRIVATE RESUME'),dict(row(),operation='PRIVATE OBJECT/ID'),dict(row(),duration_ms=True)]:
  assert client.post('/experiments/analytics/interactions',json={'events':[bad]}).status_code==422
 assert store.report()['expansion']['conversions']==[]
 assert client.post('/experiments/analytics/interactions',json={'events':[row()]},headers={'Origin':'https://evil.example'}).status_code==403

def test_complete_correlated_and_replayed_results_are_not_new_completions(runtime):
 client,store=runtime
 client.post('/experiments/analytics/interactions',json={'events':[row('interaction'),row()]})
 client.post('/experiments/chat-turns',headers=headers(),json={'message':'PRIVATE USER INPUT'})
 client.post('/experiments/chat-turns',headers=headers(),json={'message':'PRIVATE USER INPUT'})
 client.post('/experiments/analytics/interactions',json={'events':[row(op='op-b')]})
 client.post('/experiments/chat-turns',headers=headers('op-b'))
 r=store.report();c=r['expansion']['conversions'][0]
 assert (c['submitted'],c['received'],c['completed'],c['duplicate'])==(2,2,1,1)
 assert next(r for r in r['events'] if r['name']=='chat')['count']==1
 with store.connect() as db:
  raw=json.dumps([tuple(r) for r in db.execute('SELECT * FROM stages')]+[tuple(r) for r in db.execute('SELECT * FROM events')])
 assert all(secret not in raw for secret in ['PRIVATE','browser-a','op-a','page-a','visit-a'])

def test_browser_scoped_operation_ids_and_exclusion(runtime):
 client,store=runtime
 for identity in ['browser-a','browser-b']:
  client.cookies.set('test-cookie',identity)
  client.post('/experiments/analytics/interactions',json={'events':[row()]})
  client.post('/experiments/chat-turns',headers=headers())
 assert store.report()['expansion']['conversions'][0]['completed']==2
 store.exclude('browser-a',True)
 assert store.report()['expansion']['conversions'][0]['completed']==1
 assert store.report(include_excluded=True)['expansion']['conversions'][0]['completed']==2

def test_blocked_offline_waiting_and_unobserved_are_distinct(runtime):
 client,store=runtime
 records=[row('interaction',op='blocked'),dict(row('validation_blocked',op='blocked'),reason='unconfirmed'),row(op='pending'),row(op='offline'),dict(row('transport_error',op='offline'),reason='network')]
 client.post('/experiments/analytics/interactions',json={'events':records})
 stats=store.report()['expansion']['conversions'][0]
 assert stats['submitted']==2 and stats['received']==0 and stats['completed']==0 and stats['waiting']==1 and stats['unobserved']==1 and stats['blocked']==1 and stats['failed']==0
 with store.connect() as db:db.execute("UPDATE stages SET timestamp=? WHERE stage='submitted'",((datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat(),))
 assert store.report()['expansion']['conversions'][0]['unobserved']==2

def test_ctr_uses_exposed_browsers_and_copy_is_not_a_view(runtime):
 client,store=runtime
 client.post('/experiments/analytics/interactions',json={'events':[row('exposure',op=''),row('interaction',op='')]})
 client.cookies.set('test-cookie','browser-b')
 client.post('/experiments/analytics/interactions',json={'events':[row('interaction',op='')]})
 buttons=store.report()['expansion']['buttons'][0]
 assert buttons['visitors']==2 and buttons['exposed_browsers']==1 and buttons['exposed_clicked_browsers']==1 and buttons['click_rate']==1
 records=[dict(row('copy_success',op='',action='career.copy'),material='resume'),dict(row('material_view',op='',action='career.open'),material='project')]
 client.post('/experiments/analytics/interactions',json={'events':records})
 groups={r['material']:r for r in store.report()['expansion']['materials']}
 assert groups['project']['views']==1 and groups['resume']['views']==0 and groups['resume']['copy_success']==1
 assert groups['all']['generated']==0 and groups['interview']['views']==0

def test_batch_dedup_capacity_and_business_results_survive_click_flood(runtime):
 client,store=runtime;batch=[row('interaction',op='') for _ in range(32)]
 assert client.post('/experiments/analytics/interactions',json={'events':batch}).status_code==200
 assert client.post('/experiments/analytics/interactions',json={'events':batch}).status_code==200
 with store.connect() as db:assert db.execute('SELECT COUNT(*) FROM stages').fetchone()[0]==32
 started=time.monotonic();accepted=0
 for _ in range(60):
  r=client.post('/experiments/analytics/interactions',json={'events':[row('interaction',op='') for _ in range(32)]})
  accepted+=r.status_code==200
 assert 5<accepted<60
 assert client.post('/experiments/chat-turns',headers=headers()).status_code==200
 assert store.report()['events'][0]['count']==1
 with store.connect() as db:assert db.execute("SELECT COUNT(*) FROM stages WHERE stage='result'").fetchone()[0]==1
 # Two parallel tabs compete for the final batch; only one can reserve capacity.
 from concurrent.futures import ThreadPoolExecutor
 from threading import Barrier
 for _ in range(55):assert v2.client_batch(store,'browser-b',[row('interaction',op='') for _ in range(32)])
 gate=Barrier(2)
 def concurrent_batch(_):
  batch=[row('interaction',op='') for _ in range(32)];gate.wait()
  return v2.client_batch(store,'browser-b',batch)
 with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(concurrent_batch,range(2)))==1
 with store.connect() as db:assert db.execute('SELECT COUNT(*) FROM stages WHERE visitor=?',(store.visitor('browser-b'),)).fetchone()[0]==1792
 assert time.monotonic()-started<15

def test_dnt_and_historical_unknowns(runtime):
 client,store=runtime
 assert client.post('/experiments/analytics/interactions',headers={'DNT':'1'},json={'events':[row()]}).json()['recorded'] is False
 client.post('/experiments/chat-turns',headers={**headers(),'DNT':'1'})
 assert not store.report()['expansion']['conversions']
 store.record('browser-a','chat',source='historical')
 assert store.report(source='historical')['events'][0]['count']==1
 assert not store.report(source='historical')['expansion']['buttons']

def test_restart_migration_preserves_identity_old_rows_and_start(tmp_path):
 store=AnalyticsStore(tmp_path);store.record('browser-a','chat',event_id='old')
 before=store.report();salt=store.salt
 again=AnalyticsStore(tmp_path)
 assert again.salt==salt and again.report()['events']==before['events'] and again.report()['started_at']==before['started_at'] and again.report()['expansion']['started_at']==before['expansion']['started_at']

def test_outcome_mappings_are_real_server_states():
 assert response_outcome('tools_probe',200,{'tool_call_capability':'VERIFIED'})==('tools_probe','SUCCESS')
 assert response_outcome('tools_probe',200,{'tool_call_capability':'UNSUPPORTED'})==('tools_probe','FAILED')
 assert response_outcome('repeat_run',200,{'summary':{'attempts':[{'status':'COMPLETE'},{'status':'FAILED'}]}})==('repeat_run','PARTIAL')
 paths={'/provider-sessions':'session_save','/provider-sessions/id/judge':'judge_bind','/chat-turns/id/test-draft':'chat_draft','/retrieval-runs/id/reviews':'review_save','/retrieval-comparisons/id/conclusions':'conclusion_save','/career/evidence':'evidence_save','/career/narrative/preview':'narrative_preview','/career/materials/id/edit':'materials_edit','/career/materials/id/regenerate-section':'materials_regenerate','/interview-attempts':'interview_save'}
 for path,event in paths.items():assert business_event('POST','/experiments'+path)==event

def test_partial_unknown_and_retry_flow(runtime):
 client,store=runtime
 v2.client_batch(store,'browser-a',[row(op='one'),dict(row(op='two'),retry_of='one')])
 for op,outcome in [('one','PARTIAL'),('two','SUCCESS')]:
  metadata=v2.request_metadata(SimpleNamespace(headers={k.lower():v for k,v in headers(op).items()}),'chat','chat.send',PAGES)
  v2.received(store,'browser-a',metadata);v2.result(store,'browser-a',metadata,outcome,500,'execution' if outcome=='PARTIAL' else 'none')
 c=store.report()['expansion']['conversions'][0]
 assert c['partial']==1 and c['completed']==1 and c['retries']==1 and c['retry_completed']==1
 assert store.report()['expansion']['reuse']['repeat_completion_browsers']==0


def test_upgrade_from_original_schema_keeps_legacy_rows_and_exclusions(tmp_path):
 import sqlite3,secrets
 root=tmp_path/'analytics';root.mkdir();(root/'salt').write_bytes(secrets.token_bytes(32))
 with sqlite3.connect(root/'events.sqlite3') as db:
  db.executescript("CREATE TABLE events (id TEXT PRIMARY KEY,timestamp TEXT NOT NULL,day TEXT NOT NULL,visitor TEXT NOT NULL,session TEXT NOT NULL,name TEXT NOT NULL,outcome TEXT NOT NULL,page TEXT NOT NULL,referrer TEXT NOT NULL,source TEXT NOT NULL,duration_ms INTEGER NOT NULL); CREATE TABLE excluded (visitor TEXT PRIMARY KEY); CREATE TABLE settings (key TEXT PRIMARY KEY,value TEXT);")
  db.execute('INSERT INTO settings VALUES (?,?)',('started_at','2026-10-11T09:35:13+00:00'))
  stamp=datetime.now(timezone.utc).isoformat();day=datetime.now(timezone(timedelta(hours=8))).date().isoformat()
  db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)',('old',stamp,day,'old-hmac','old-session','chat','SUCCESS','','','live',123))
  db.execute('INSERT INTO excluded VALUES (?)',('old-hmac',))
 store=AnalyticsStore(root)
 assert store.report()['events']==[] and store.report(include_excluded=True)['events'][0]['count']==1
 assert store.report()['started_at']=='2026-10-11T09:35:13+00:00'
 assert store.report()['expansion']['buttons']==[]
