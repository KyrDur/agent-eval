"""Interaction and operation stages, separate from the original outcome metric.

The only identifiers stored are visitor-scoped HMACs. Client data never writes a
received/result stage. Free text and arbitrary labels fail closed.
"""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib,hmac,json,re,secrets,time
from pathlib import Path

CONTRACT=json.loads(Path(__file__).with_name('analytics_contract.json').read_text())
STAGES={'page_enter','available','interaction','exposure','unavailable','edit_start','validation_blocked','submitted','transport_error','client_wait','material_view','copy_success','download_trigger'}
ENTRIES={'direct','home','guide','navigation','history','return','in_page'}
PATHS={'RETRIEVAL','AGENT_BEHAVIOR'}
STATES={'none','expand','collapse','select','deselect','change'}
FIELDS={'stage','action','page','page_visit','session','event_id','placement','path','entry','material','role','context','reason','state','operation','retry_of','duration_ms'}
UI_FIELDS={'ui_variant','layout','content','example_kind','issue_kind','reveal','preparation_flow'}
UI_ENUMS={'ui_variant':'ui_variants','layout':'layouts','content':'contents','example_kind':'example_kinds','issue_kind':'issue_kinds','reveal':'reveals'}
UI_COLUMNS='id,ui_variant,layout,content,example_kind,issue_kind,reveal,preparation_flow'
UUID=re.compile(r'[A-Za-z0-9-]{1,64}')
FLOW_UUID=re.compile(r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}',re.I)
EXTRA_LABELS={
 'session_save':'模型会话保存','tools_probe':'工具格式探针','judge_bind':'Judge 绑定',
 'chat_draft':'对话测试草稿保存','decision_save':'修改判断保存','change_save':'修改草稿保存',
 'change_rollback':'恢复规则','review_save':'人工复核保存','conclusion_save':'实验结论保存',
 'evidence_save':'项目事实整理 / 确认','narrative_preview':'叙事证据预览',
 'materials_edit':'材料编辑保存','materials_regenerate':'材料段落重新生成',
 'interview_save':'面试练习保存','rewrite_preview':'查询改写预览','repeat_run':'重复运行',
}
EXACT={
 '/experiments/provider-sessions':('session_save','setup.save'),
 '/experiments/knowledge-datasets':('knowledge_save','knowledge.save'),
 '/experiments/chat-turns':('chat','chat.send'),
 '/experiments/ai/knowledge':('knowledge_generate','knowledge.generate'),
 '/experiments/ai/tests':('tests_generate','tests.generate'),
 '/experiments/ai/trace':('trace_analyze','trace.analyze'),
 '/experiments/retrieval-evalsets':('tests_save','tests.save'),'/experiments/evalsets':('tests_save','tests.save'),
 '/experiments/retrieval-runs':('run','run.baseline'),'/experiments/retrieval-run-tasks':('run','run.baseline'),'/experiments/runs':('run','run.baseline'),
 '/experiments/retrieval-comparisons':('compare','comparison.create'),'/experiments/comparisons':('compare','comparison.create'),
 '/experiments/decisions':('decision_save','change.diagnose'),
 '/experiments/retrieval-changes':('change_save','change.propose'),'/experiments/changes':('change_save','change.record'),
 '/experiments/retrieval-rewrite-preview':('rewrite_preview','change.preview'),
 '/experiments/retrieval-repeats':('repeat_run','run.repeat'),
 '/experiments/career/evidence':('evidence_save','career.evidence'),
 '/experiments/career/narrative/preview':('narrative_preview','career.preview'),
 '/experiments/career/materials':('materials_generate','career.generate'),
 '/experiments/career/materials/v2':('materials_generate','career.generate'),
 '/experiments/interview-attempts':('interview_save','interview.save'),
}
PATTERNS=[
 (r'/experiments/provider-sessions/[^/]+/test','api_connect','setup.test'),
 (r'/experiments/provider-sessions/[^/]+/test-tools','tools_probe','setup.tools'),
 (r'/experiments/provider-sessions/[^/]+/judge','judge_bind','judge.bind'),
 (r'/experiments/knowledge-datasets/[^/]+/index','knowledge_index','knowledge.index'),
 (r'/experiments/chat-turns/[^/]+/test-draft','chat_draft','chat.draft'),
 (r'/experiments/(retrieval-runs|runs)/[^/]+/reviews','review_save','review.save'),
 (r'/experiments/decisions/[^/]+/confirm','decision_save','change.confirm'),
 (r'/experiments/(retrieval-changes|changes)/[^/]+/apply','change_apply','change.apply'),
 (r'/experiments/changes/[^/]+/rollback','change_rollback','change.rollback'),
 (r'/experiments/retrieval-comparisons/[^/]+/conclusions','conclusion_save','conclusion.save'),
 (r'/experiments/career/materials/[^/]+/edit','materials_edit','career.edit'),
 (r'/experiments/career/materials/[^/]+/regenerate-section','materials_regenerate','career.regenerate'),
]

def route_event(method,path):
 if method=='GET' and re.fullmatch(r'/experiments/career/materials/[^/]+/export',path):return 'materials_fetch','career.fetch'
 if method!='POST':return None
 return EXACT.get(path) or next(((name,action) for pattern,name,action in PATTERNS if re.fullmatch(pattern,path)),None)

def error_category(status,data,outcome):
 if outcome in {'SUCCESS','WAITING','DUPLICATE'}:return 'none'
 # Inspect only a fixed error code; never keep the response or error text.
 code=data.get('error') or data.get('status') if isinstance(data,dict) else None
 if isinstance(data,dict) and isinstance(data.get('detail'),str):code=data['detail']
 if not isinstance(code,str):code=''
 if code in {'AUTH_FAILED','CREDENTIAL_UNAVAILABLE'} or status in {401,403}:return 'authentication'
 if code in {'RATE_LIMITED','CALL_BUDGET_EXCEEDED'} or status==429:return 'rate_limit'
 if code=='TIMEOUT' or status==504:return 'timeout'
 if code=='NETWORK_ERROR':return 'network'
 if status in {409,422}:return 'precondition'
 if status>=500:return 'service'
 return 'execution' if outcome in {'FAILED','PARTIAL'} else 'unknown'

def initialize(store):
 with store.connect() as db:
  db.executescript('''CREATE TABLE IF NOT EXISTS stages (
   id TEXT PRIMARY KEY,timestamp TEXT NOT NULL,day TEXT NOT NULL,visitor TEXT NOT NULL,
   session TEXT NOT NULL,page_visit TEXT NOT NULL,operation TEXT NOT NULL,retry_of TEXT NOT NULL,
   stage TEXT NOT NULL,action TEXT NOT NULL,page TEXT NOT NULL,placement TEXT NOT NULL,
   path TEXT NOT NULL,entry TEXT NOT NULL,material TEXT NOT NULL,role TEXT NOT NULL,
   context TEXT NOT NULL,reason TEXT NOT NULL,state TEXT NOT NULL,outcome TEXT NOT NULL,
   duration_ms INTEGER NOT NULL);
   CREATE INDEX IF NOT EXISTS stages_window ON stages(day,visitor);
   CREATE INDEX IF NOT EXISTS stages_operations ON stages(visitor,operation,stage);
   CREATE TABLE IF NOT EXISTS completion_claims (key TEXT PRIMARY KEY);
  ''')
  db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',('expansion_started_at',datetime.now(timezone.utc).isoformat()))
  db.execute('CREATE TABLE IF NOT EXISTS stage_ui (id TEXT PRIMARY KEY,ui_variant TEXT NOT NULL,layout TEXT NOT NULL,content TEXT NOT NULL,example_kind TEXT NOT NULL,issue_kind TEXT NOT NULL,reveal TEXT NOT NULL,preparation_flow TEXT NOT NULL)')
  db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',('visual_started_at',datetime.now(timezone.utc).isoformat()))

def hashed(store,identity,value):
 return hmac.new(store.salt,(identity+':'+value).encode(),hashlib.sha256).hexdigest() if value else ''

def validate(row,pages):
 if not isinstance(row,dict) or set(row) not in (FIELDS,FIELDS|UI_FIELDS):return False
 if any(not isinstance(v,str) for k,v in row.items() if k!='duration_ms'):return False
 if type(row['duration_ms']) is not int or not 0<=row['duration_ms']<=3600000:return False
 if row['stage'] not in STAGES or row['action'] not in CONTRACT['actions'] or row['page'] not in pages:return False
 if any(not UUID.fullmatch(row[k]) for k in ('page_visit','session','event_id')):return False
 if any(row[k] and not UUID.fullmatch(row[k]) for k in ('operation','retry_of')):return False
 for key,values in [('placement',CONTRACT['placements']),('path',PATHS),('entry',ENTRIES),('material',CONTRACT['materials']),('role',CONTRACT['roles']),('context',CONTRACT['contexts']),('reason',CONTRACT['reasons']),('state',STATES)]:
  if row[key] not in values:return False
 for key,catalog in UI_ENUMS.items():
  if row.get(key,'unknown') not in CONTRACT[catalog]:return False
 if row.get('preparation_flow') and (not FLOW_UUID.fullmatch(row['preparation_flow']) or row['action'] not in {'knowledge.save','knowledge.index'}):return False
 if row['stage'] in {'submitted','validation_blocked','transport_error','client_wait'} and (not row['operation'] or row['action'] not in CONTRACT['core']):return False
 return True

def write(store,identity,row,*,stage=None,outcome='',event_id=None):
 stamp=datetime.now(timezone.utc)
 # Every correlation token is salted and scoped to the workspace identity.
 values=(event_id or hashed(store,identity,row['event_id']),stamp.isoformat(),stamp.astimezone(__import__('experiments.analytics',fromlist=['SHANGHAI']).SHANGHAI).date().isoformat(),store.visitor(identity),
  hashed(store,identity,row.get('session','')),hashed(store,identity,row.get('page_visit','')),hashed(store,identity,row.get('operation','')),hashed(store,identity,row.get('retry_of','')),
  stage or row['stage'],row['action'],row.get('page',''),row.get('placement','api'),row.get('path','RETRIEVAL'),row.get('entry','direct'),row.get('material','unknown'),row.get('role','unknown'),row.get('context','unknown'),row.get('reason','none'),row.get('state','none'),outcome,row.get('duration_ms',0))
 return values

def insert_stage(db,store,identity,row,**options):
 values=write(store,identity,row,**options)
 db.execute('INSERT OR IGNORE INTO stages VALUES ('+','.join('?'*21)+')',values)
 dims=tuple(row.get(key,'unknown') if row.get(key,'unknown') in CONTRACT[catalog] else 'unknown' for key,catalog in UI_ENUMS.items())
 flow=row.get('preparation_flow','')
 flow=hashed(store,identity,flow) if FLOW_UUID.fullmatch(flow) and row['action'] in {'knowledge.save','knowledge.index'} else ''
 db.execute('INSERT OR IGNORE INTO stage_ui ('+UI_COLUMNS+') VALUES ('+','.join('?'*8)+')',(values[0],*dims,flow))

def client_batch(store,identity,rows):
 since=time.time()-60
 cutoff=datetime.fromtimestamp(since,timezone.utc).isoformat()
 with store.connect() as db:
  # Serialize the capacity check and insert so parallel tabs cannot overrun it.
  db.execute('BEGIN IMMEDIATE')
  count=db.execute("SELECT COUNT(*) FROM stages WHERE visitor=? AND timestamp>=? AND stage NOT IN ('received','result')",(store.visitor(identity),cutoff)).fetchone()[0]
  if count+len(rows)>1800:return False
  for row in rows:insert_stage(db,store,identity,row)
 return True

def request_metadata(request,name,action,pages):
 headers=request.headers;op=headers.get('x-ae-operation','')
 if not UUID.fullmatch(op):return None
 declared=headers.get('x-ae-action','')
 accepted={action}
 if name=='knowledge_generate':accepted.add('knowledge.regenerate')
 if name=='session_save':accepted.add('judge.save')
 if name=='api_connect':accepted.add('judge.connect')
 if name=='judge_bind':accepted.add('judge.restore')
 if name=='run':accepted.add('run.retest')
 if name=='evidence_save':accepted.add('career.confirm')
 action=declared if declared in accepted else action
 row=dict(stage='received',action=action,operation=op,event_id=op,reason='none',state='none',duration_ms=0,retry_of='')
 for field,default,allowed in [('page','',pages),('placement','api',CONTRACT['placements']),('path','RETRIEVAL',PATHS),('entry','direct',ENTRIES),('material','unknown',CONTRACT['materials']),('role','unknown',CONTRACT['roles']),('context','unknown',CONTRACT['contexts'])]:
  value=headers.get('x-ae-'+field,'');row[field]=value if value in allowed else default
 for field,header in [('page_visit','visit'),('session','session'),('retry_of','retry')]:
  value=headers.get('x-ae-'+header,'');row[field]=value if UUID.fullmatch(value) else ''
 for field,header,catalog in [('ui_variant','ui','ui_variants'),('layout','layout','layouts')]:
  value=headers.get('x-ae-'+header,'');row[field]=value if value in CONTRACT[catalog] else 'unknown'
 flow=headers.get('x-ae-flow','')
 row['preparation_flow']=flow if action in {'knowledge.save','knowledge.index'} and FLOW_UUID.fullmatch(flow) else ''
 return row

def received(store,identity,row):
 with store.connect() as db:insert_stage(db,store,identity,row,stage='received',event_id=hashed(store,identity,row['operation']+':received'))

def result(store,identity,row,outcome,duration_ms,reason,claim=None):
 row={**row,'duration_ms':duration_ms,'reason':reason}
 with store.connect() as db:
  if claim and outcome in {'SUCCESS','PARTIAL'}:
   if not db.execute('INSERT OR IGNORE INTO completion_claims VALUES (?)',(claim,)).rowcount:outcome='DUPLICATE'
  insert_stage(db,store,identity,row,stage='result',outcome=outcome,event_id=hashed(store,identity,row['operation']+':result'))


def summarize(store,days,include_excluded,source):
 from .analytics import SHANGHAI
 from datetime import timedelta
 today=datetime.now(SHANGHAI).date();since=(today-timedelta(days=days-1)).isoformat()
 with store.connect() as db:
  started=db.execute("SELECT value FROM settings WHERE key='expansion_started_at'").fetchone()[0]
  visual_started=db.execute("SELECT value FROM settings WHERE key='visual_started_at'").fetchone()[0]
  where='day>=? AND day<=?'+('' if include_excluded else ' AND visitor NOT IN (SELECT visitor FROM excluded)')
  dims=','.join("COALESCE(u."+key+",'"+('' if key=='preparation_flow' else 'unknown')+"') AS "+key for key in UI_COLUMNS.split(',')[1:])
  rows=[dict(r) for r in db.execute('SELECT s.*,'+dims+' FROM stages s LEFT JOIN stage_ui u ON u.id=s.id WHERE '+where,(since,today.isoformat()))] if source=='live' else []
 from .analytics_ui import summarize_ui
 if source=='historical':
  return dict(version=2,collected=False,started_at=started,window=dict(since=since,until=today.isoformat(),identity='anonymous_browser',cohort='not_collected'),buttons=[],conversions=[],barriers=[],durations=[],materials=[],workflow=[],result_contexts=[],entries=[],reuse=None,unmatched_receipts=None,visual=summarize_ui([],visual_started,False))
 buttons=defaultdict(list);ops=defaultdict(list);materials=defaultdict(list);barriers=defaultdict(int);durations=defaultdict(list)
 for row in rows:
  if row['stage'] in {'interaction','exposure','unavailable','edit_start','available'}:buttons[(row['page'],row['action'],row['placement'],row['path'])].append(row)
  if row['operation']:ops[(row['visitor'],row['operation'])].append(row)
  if row['material']!='unknown':materials[row['material']].append(row)
  if row['stage'] in {'unavailable','validation_blocked','transport_error'} or row['stage']=='result' and row['outcome'] in {'FAILED','PARTIAL','UNKNOWN'}:barriers[(row['action'],row['stage'],row['reason'])]+=1
  if row['stage'] in {'result','client_wait'}:durations[(row['action'],'server' if row['stage']=='result' else 'browser')].append(row['duration_ms'])
 button_rows=[]
 for (page,action,placement,path),group in sorted(buttons.items()):
  clicked={r['visitor'] for r in group if r['stage']=='interaction'};exposed={r['visitor'] for r in group if r['stage']=='exposure'}
  button_rows.append(dict(page=page,action=action,placement=placement,path=path,clicks=sum(r['stage']=='interaction' for r in group),visitors=len(clicked),exposures=sum(r['stage']=='exposure' for r in group),exposed_browsers=len(exposed),exposed_clicked_browsers=len(clicked&exposed),click_rate=len(clicked&exposed)/len(exposed) if exposed else None,available_browsers=len({r['visitor'] for r in group if r['stage']=='available'}),unavailable_browsers=len({r['visitor'] for r in group if r['stage']=='unavailable'}),edit_starts=sum(r['stage']=='edit_start' for r in group)))
 conversions=defaultdict(lambda:defaultdict(int));cohort=[]
 for key,group in ops.items():
  submission=next((r for r in group if r['stage']=='submitted'),None)
  if not submission:continue # Old clients and dropped submission telemetry are not invented cohort members.
  action=submission['action'];stats=conversions[action];stats['submitted']+=1
  stats['clicked']+=any(r['stage']=='interaction' for r in group)
  stats['received']+=any(r['stage']=='received' for r in group)
  outcome=next((r['outcome'] for r in group if r['stage']=='result'),None)
  status={'SUCCESS':'completed','FAILED':'failed','PARTIAL':'partial','UNKNOWN':'unknown','DUPLICATE':'duplicate','WAITING':'waiting'}.get(outcome)
  if not status:status='unobserved' if any(r['stage']=='transport_error' for r in group) or (datetime.now(timezone.utc)-datetime.fromisoformat(submission['timestamp'])).total_seconds()>300 else 'waiting'
  stats[status]+=1
  retry=bool(submission['retry_of']);stats['retries']+=retry;stats['retry_completed']+=retry and status=='completed';cohort.append((key,submission,status))
 # Show blocked clicks independently; do not divide today's successes by today's clicks.
 for row in rows:
  if row['stage']=='validation_blocked':conversions[row['action']]['blocked']+=1
 conversion_rows=[dict(action=action,**{key:stats.get(key,0) for key in ['clicked','submitted','received','completed','partial','failed','waiting','unobserved','unknown','duplicate','blocked','retries','retry_completed']}) for action,stats in sorted(conversions.items())]
 material_rows=[]
 for material in ['project','resume','interview','all','evidence']:
  group=materials[material];counts={}
  for metric,stage,actions in [('views','material_view',None),('edit_starts','interaction',{'career.begin_edit'}),('copy_success','copy_success',None),('download_trigger','download_trigger',None),('practice_starts','edit_start',{'interviewpractice.edit_start'}),('question_open','interaction',{'interview.question'}),('outline_open','interaction',{'interview.outline'})]:
   subset=[r for r in group if r['stage']==stage and (actions is None or r['action'] in actions) and r['state']!='collapse'];counts[metric]=len(subset);counts[metric+'_browsers']=len({r['visitor'] for r in subset})
  for metric,action in [('saved','career.edit'),('regenerated','career.regenerate'),('generated','career.generate'),('fetched','career.fetch'),('practice_saved','interview.save')]:
   subset=[r for r in group if r['stage']=='result' and r['action']==action and r['outcome']=='SUCCESS'];counts[metric]=len(subset);counts[metric+'_browsers']=len({r['visitor'] for r in subset})
  material_rows.append(dict(material=material,**counts))
 context_rows=defaultdict(list);entry_rows=defaultdict(list)
 for r in rows:
  if r['stage']=='result':context_rows[(r['action'],r['role'],r['context'],r['material'],r['outcome'])].append(r)
  if r['stage']=='page_enter':entry_rows[(r['page'],r['entry'],r['path'])].append(r)
 result_contexts=[dict(action=a,role=role,context=context,material=material,outcome=outcome,count=len(group),browsers=len({r['visitor'] for r in group})) for (a,role,context,material,outcome),group in sorted(context_rows.items())]
 entries=[dict(page=page,entry=entry,path=path,count=len(group),browsers=len({r['visitor'] for r in group})) for (page,entry,path),group in sorted(entry_rows.items())]
 duration_rows=[]
 for (action,clock),samples in sorted(durations.items()):
  samples.sort();duration_rows.append(dict(action=action,clock=clock,count=len(samples),p50_ms=samples[int((len(samples)-1)*.5)],p95_ms=samples[int((len(samples)-1)*.95)],max_ms=samples[-1]))
 # Browser observation window, with any-stage reach and ordered transitions kept distinct.
 workflow=[('api_connect',{'setup.test'}),('index',{'knowledge.index'}),('chat_tests',{'chat.send','tests.save'}),('baseline',{'run.baseline'}),('change',{'change.apply'}),('retest',{'run.retest'}),('compare',{'comparison.create'}),('materials',{'career.generate'})]
 success=[r for r in rows if r['stage']=='result' and r['outcome']=='SUCCESS']
 people={r['visitor'] for r in success};cursor={v:'' for v in people};ordered=set(people);flow=[]
 for stage,actions in workflow:
  matching=[r for r in success if r['action'] in actions];reach={r['visitor'] for r in matching};next_ordered=set()
  for visitor in ordered:
   times=[r['timestamp'] for r in matching if r['visitor']==visitor and r['timestamp']>=cursor[visitor]]
   if times:cursor[visitor]=min(times);next_ordered.add(visitor)
  ordered=next_ordered;flow.append(dict(stage=stage,reached_browsers=len(reach),ordered_browsers=len(ordered)))
 visits=defaultdict(list)
 for r in success:
  if r['action']!='career.fetch':visits[r['visitor']].append(r)
 repeated=sum(len({r['operation'] for r in group})>=2 for group in visits.values())
 returning=sum(len({r['session'] for r in group if r['session']})>=2 for group in visits.values())
 return dict(started_at=started,version=2,collected=True,visual=summarize_ui(rows,visual_started,True),window=dict(since=since,until=today.isoformat(),identity='anonymous_browser',cohort='submitted_operation',unknown_after_seconds=300),
  buttons=button_rows,conversions=conversion_rows,barriers=[dict(action=a,stage=s,reason=r,count=n) for (a,s,r),n in sorted(barriers.items())],durations=duration_rows,result_contexts=result_contexts,entries=entries,materials=material_rows,workflow=flow,
  reuse=dict(core_browsers=len(visits),repeat_completion_browsers=repeated,returning_session_browsers=returning),
  unmatched_receipts=sum(r['stage']=='received' and not any(x['stage']=='submitted' for x in ops[(r['visitor'],r['operation'])]) for r in rows))
