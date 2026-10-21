"""First-party operational analytics. No request bodies, IPs, keys or free text.

Disabled unless AGENTEVAL_ANALYTICS_DIR is configured. Business outcomes come
from the actual server response, not clicks. The report requires a separate
read-only admin token; anonymous workspace cookies never authorize it.
"""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit
import uuid
from . import analytics_v2 as expansion
from . import learning_analytics

from starlette.requests import Request
from starlette.responses import JSONResponse

PAGES = frozenset({'welcome', 'setup', 'knowledge', 'chat', 'define', 'evaluate',
                   'improve', 'compare', 'career', 'history', 'calibration','learning'})
LABELS = {
    'page_view': '页面浏览', 'api_connect': 'API 连接',
    'knowledge_generate': 'AI 生成知识', 'knowledge_save': '知识保存',
    'knowledge_index': '知识索引', 'chat': 'Agent 聊天',
    'tests_generate': 'AI 生成题目', 'tests_save': '测试题保存',
    'baseline': '初测', 'retest': '复测', 'run': '评测',
    'trace_analyze': 'AI 分析轨迹', 'change_apply': '应用修改',
    'compare': '比较结果', 'materials_generate': '材料生成',
    'materials_fetch': '取得导出内容', 'export_download': '触发材料下载',
    'export_copy': '材料复制成功',
}
LEGACY_CORE_EVENTS=frozenset(LABELS)-{'page_view','export_download','export_copy','materials_fetch'}
LABELS.update(expansion.EXTRA_LABELS)
CLIENT_EVENTS = {'page_view', 'export_download', 'export_copy'}
OUTCOMES = {'SUCCESS', 'FAILED', 'PARTIAL', 'UNKNOWN'}
SHANGHAI = timezone(timedelta(hours=8))


def business_event(method, path):
    """Identifiers stay in memory and are never logged."""
    result = expansion.route_event(method,path)
    return result[0] if result else None


def response_outcome(name, status, data):
    if not 200 <= status < 300:
        return name, 'FAILED'
    if not isinstance(data, dict):
        return name, 'UNKNOWN'
    if name == 'tools_probe':
        return name, 'SUCCESS' if data.get('tool_call_capability') == 'VERIFIED' else 'FAILED'
    if name == 'api_connect':
        return name, 'SUCCESS' if data.get('status') == 'SUCCESS' else 'FAILED'
    if name == 'chat':
        return name, 'SUCCESS' if data.get('status') == 'SUCCESS' else 'FAILED'
    if name == 'run':
        name = {'BASELINE': 'baseline', 'RETEST': 'retest'}.get(data.get('run_type'), 'run')
        return name, {'COMPLETE': 'SUCCESS', 'PARTIAL': 'PARTIAL', 'FAILED': 'FAILED'}.get(data.get('status'), 'UNKNOWN')
    if name == 'change_apply':
        return name, 'SUCCESS' if data.get('implemented_status') == 'APPLIED' else 'FAILED'
    if name == 'repeat_run':
        attempts=data.get('summary',{}).get('attempts',[])
        complete=sum(row.get('status')=='COMPLETE' for row in attempts)
        return name, 'SUCCESS' if attempts and complete==len(attempts) else 'PARTIAL' if complete else 'FAILED'
    if name == 'change_rollback':
        return name, 'SUCCESS' if data.get('rollback_status') == 'ROLLED_BACK' else 'UNKNOWN'
    return name, 'SUCCESS'


def referrer_host(value):
    try:
        url = urlsplit(value)
        host = url.hostname or ''
        return host.lower() if url.scheme in {'http', 'https'} and re.fullmatch(r'[A-Za-z0-9.-]{1,253}', host) else ''
    except (ValueError, TypeError):
        return ''


class AnalyticsStore:
    def __init__(self, root, admin_token_file=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        salt = self.root / 'salt'
        if not salt.exists():
            fd = os.open(salt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(secrets.token_bytes(32))
        self.salt = salt.read_bytes()
        self.admin_token_file = Path(admin_token_file) if admin_token_file else None
        self.database = self.root / 'events.sqlite3'
        with self.connect() as db:
            db.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, day TEXT NOT NULL,
                visitor TEXT NOT NULL, session TEXT NOT NULL, name TEXT NOT NULL,
                outcome TEXT NOT NULL, page TEXT NOT NULL, referrer TEXT NOT NULL,
                source TEXT NOT NULL, duration_ms INTEGER NOT NULL);
              CREATE INDEX IF NOT EXISTS events_day ON events(day);
              CREATE INDEX IF NOT EXISTS events_visitor_time ON events(visitor,timestamp);
              CREATE TABLE IF NOT EXISTS excluded (visitor TEXT PRIMARY KEY);
              CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            ''')
            db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('started_at', datetime.now(timezone.utc).isoformat()))
        self.database.chmod(0o600)
        expansion.initialize(self)
        learning_analytics.initialize(self)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def visitor(self, identity):
        return hmac.new(self.salt, identity.encode('ascii'), hashlib.sha256).hexdigest()

    def authorized(self, value):
        try:
            expected = self.admin_token_file.read_text().strip() if self.admin_token_file else ''
            return len(expected) >= 32 and hmac.compare_digest(value, 'Bearer ' + expected)
        except OSError:
            return False

    def exclude(self, identity, excluded):
        with self.connect() as db:
            if excluded:
                db.execute('INSERT OR IGNORE INTO excluded VALUES (?)', (self.visitor(identity),))
            else:
                db.execute('DELETE FROM excluded WHERE visitor=?', (self.visitor(identity),))

    def is_excluded(self, identity):
        with self.connect() as db:
            return bool(db.execute('SELECT 1 FROM excluded WHERE visitor=?', (self.visitor(identity),)).fetchone())

    def client_capacity(self, identity):
        since=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
        with self.connect() as db:
            count=db.execute("SELECT COUNT(*) FROM events WHERE visitor=? AND timestamp>=? AND source='live' AND name IN ('page_view','export_copy','export_download')",(self.visitor(identity),since)).fetchone()[0]
        return count < 120

    def record(self, identity, name, outcome='SUCCESS', *, event_id=None, page='',
               referrer='', session='', source='live', duration_ms=0, timestamp=None):
        if name not in LABELS or outcome not in OUTCOMES or source not in {'live', 'historical'}:
            raise ValueError('Unsupported analytics event')
        stamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00')) if timestamp else datetime.now(timezone.utc)
        if stamp.tzinfo is None:
            raise ValueError('Analytics timestamp needs timezone')
        visitor = self.visitor(identity)
        session_hash = hmac.new(self.salt, (visitor + session).encode(), hashlib.sha256).hexdigest() if session else ''
        with self.connect() as db:
            inserted=db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?)', (
                event_id or str(uuid.uuid4()), stamp.astimezone(timezone.utc).isoformat(),
                stamp.astimezone(SHANGHAI).date().isoformat(), visitor, session_hash,
                name, outcome, page if page in PAGES else '', referrer_host(referrer),
                source, max(0, min(int(duration_ms), 3600000))))
            return bool(inserted.rowcount)

    def report(self, days=7, include_excluded=False, source='live'):
        if not 1 <= days <= 90 or source not in {'live', 'historical'}:
            raise ValueError('Invalid report range')
        today = datetime.now(SHANGHAI).date()
        since = (today - timedelta(days=days-1)).isoformat()
        where = 'day>=? AND day<=? AND source=?'
        if not include_excluded:
            where += ' AND visitor NOT IN (SELECT visitor FROM excluded)'
        params = (since, today.isoformat(), source)
        with self.connect() as db:
            rows = [dict(r) for r in db.execute(f'''SELECT name,outcome,COUNT(*) AS count,
                COUNT(DISTINCT visitor) AS visitors FROM events WHERE {where} GROUP BY name,outcome''', params)]
            daily = [dict(r) for r in db.execute(f'''SELECT day,
                SUM(name='page_view') AS pageviews, COUNT(DISTINCT CASE WHEN name='page_view' THEN visitor END) AS visitors,
                SUM(name!='page_view' AND outcome='SUCCESS') AS successful_actions
                FROM events WHERE {where} GROUP BY day ORDER BY day''', params)]
            pages = [dict(r) for r in db.execute(f'''SELECT page,COUNT(*) AS pageviews,COUNT(DISTINCT visitor) AS visitors
                FROM events WHERE {where} AND name='page_view' GROUP BY page ORDER BY pageviews DESC''', params)]
            referrers = [dict(r) for r in db.execute(f'''SELECT referrer,COUNT(*) AS pageviews FROM events
                WHERE {where} AND name='page_view' GROUP BY referrer ORDER BY pageviews DESC LIMIT 20''', params)]
            totals = dict(db.execute(f'''SELECT SUM(name='page_view') AS pageviews,
                COUNT(DISTINCT CASE WHEN name='page_view' THEN visitor END) AS visitors,
                COUNT(DISTINCT CASE WHEN name='page_view' AND session!='' THEN session END) AS visits,
                COUNT(DISTINCT CASE WHEN name IN ({','.join(chr(39)+name+chr(39) for name in sorted(LEGACY_CORE_EVENTS))})
                  AND outcome='SUCCESS' THEN visitor END) AS active_users FROM events WHERE {where}''', params).fetchone())
            excluded = db.execute('SELECT COUNT(*) FROM excluded').fetchone()[0]
            started = db.execute("SELECT value FROM settings WHERE key='started_at'").fetchone()[0]
        for r in rows:
            r['label'] = LABELS[r['name']]
        return {'timezone':'Asia/Shanghai', 'days':days, 'source':source,
                'since':since, 'until':today.isoformat(), 'started_at':started,
                'include_excluded':include_excluded, 'excluded_browsers':excluded,
                'totals':{k:v or 0 for k,v in totals.items()}, 'events':rows,
                'daily':daily, 'pages':pages, 'referrers':referrers,
                'expansion':expansion.summarize(self,days,include_excluded,source),
                'learning':learning_analytics.summarize(self,days,include_excluded) if source=='live' else None}


class AnalyticsMiddleware:
    """Runs outside workspace middleware; does not weaken its isolation."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        store = getattr(scope['app'].state, 'analytics', None)
        path, method = scope['path'], scope['method']
        if store is None:
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        if path == '/experiments/analytics/report':
            if method != 'GET' or not store.authorized(request.headers.get('authorization', '')):
                return await JSONResponse({'detail':'Unauthorized'}, status_code=401, headers={'Cache-Control':'no-store'})(scope, receive, send)
            try:
                result = await asyncio.to_thread(store.report, int(request.query_params.get('days', '7')),
                    request.query_params.get('include_excluded') == '1', request.query_params.get('source', 'live'))
            except (ValueError, TypeError):
                return await JSONResponse({'detail':'Invalid range'}, status_code=422)(scope, receive, send)
            return await JSONResponse(result, headers={'Cache-Control':'no-store'})(scope, receive, send)
        registry = getattr(scope['app'].state, 'workspaces', None)
        identity = registry.known(request.cookies.get(registry.cookie)) if registry else 'local-development'
        origin = request.headers.get('origin')
        trusted = not registry or (origin in {None, registry.origin} and request.headers.get('sec-fetch-site') != 'cross-site')
        if path.startswith('/experiments/analytics/'):
            if not identity or not trusted:
                return await JSONResponse({'detail':'Workspace required'}, status_code=403)(scope, receive, send)
            if path == '/experiments/analytics/preference' and method == 'GET':
                result = {'excluded': await asyncio.to_thread(store.is_excluded, identity), 'contract_version': expansion.CONTRACT['version']}
            elif path == '/experiments/analytics/preference' and method == 'POST':
                data = await self.small_json(request)
                if not isinstance(data, dict) or set(data) != {'excluded'} or type(data['excluded']) is not bool:
                    return await JSONResponse({'detail':'Invalid preference'}, status_code=422)(scope, receive, send)
                await asyncio.to_thread(store.exclude, identity, data['excluded'])
                result = {**data, 'contract_version': expansion.CONTRACT['version']}
            elif path == '/experiments/analytics/interactions' and method == 'POST':
                data = await self.small_json(request, 49152)
                if (not isinstance(data,dict) or set(data)!={'events'} or not isinstance(data['events'],list)
                    or not 1<=len(data['events'])<=32 or not all(expansion.validate(row,PAGES) for row in data['events'])):
                    return await JSONResponse({'detail':'Invalid events'},status_code=422)(scope,receive,send)
                if request.headers.get('dnt') != '1':
                    try:
                        accepted=await asyncio.to_thread(expansion.client_batch,store,identity,data['events'])
                    except Exception:
                        return await JSONResponse({'detail':'Unavailable'},status_code=503)(scope,receive,send)
                    if not accepted:
                        return await JSONResponse({'detail':'Rate limited'},status_code=429)(scope,receive,send)
                result={'recorded':request.headers.get('dnt') != '1'}
            elif path == '/experiments/analytics/events' and method == 'POST':
                data = await self.small_json(request)
                allowed = {'name', 'page', 'session', 'referrer', 'event_id'}
                if (not isinstance(data, dict) or set(data)-allowed or not all(isinstance(v,str) for v in data.values()) or data.get('name') not in CLIENT_EVENTS
                    or data.get('page', '') not in PAGES or not re.fullmatch(r'[A-Za-z0-9-]{1,64}', data.get('session', ''))
                    or not re.fullmatch(r'[A-Za-z0-9-]{1,64}', data.get('event_id', ''))
                    or not isinstance(data.get('referrer',''), str) or len(data.get('referrer','')) > 300):
                    return await JSONResponse({'detail':'Invalid event'}, status_code=422)(scope, receive, send)
                if request.headers.get('dnt') != '1':
                    if not await asyncio.to_thread(store.client_capacity, identity):
                        return await JSONResponse({'detail':'Rate limited'},status_code=429)(scope,receive,send)
                    event_id = hashlib.sha256((identity+data['event_id']).encode()).hexdigest()
                    await asyncio.to_thread(store.record, identity, data['name'], event_id=event_id,
                        page=data.get('page',''), session=data['session'], referrer=data.get('referrer',''))
                result = {'recorded': request.headers.get('dnt') != '1'}
            else:
                return await JSONResponse({'detail':'Not found'}, status_code=404)(scope, receive, send)
            return await JSONResponse(result, headers={'Cache-Control':'no-store'})(scope, receive, send)
        if path.startswith('/experiments/learning/') and method=='POST' and identity and trusted and request.headers.get('dnt')!='1':
            body=bytearray();status=500;overflow=False
            async def capture_learning(message):
                nonlocal status,overflow
                if message['type']=='http.response.start':status=message['status']
                elif message['type']=='http.response.body':
                    chunk=message.get('body',b'')
                    if len(body)+len(chunk)<=1024*1024:body.extend(chunk)
                    else:overflow=True
                await send(message)
            await self.app(scope,receive,capture_learning)
            if 200<=status<300 and not overflow:
                try:await asyncio.to_thread(learning_analytics.record,store,identity,json.loads(body).get('analytics_event'))
                except Exception:pass
            return
        name = business_event(method, path)
        if not name or not identity or not trusted or request.headers.get('dnt') == '1':
            return await self.app(scope, receive, send)
        route=expansion.route_event(method,path)
        metadata=expansion.request_metadata(request,name,route[1],PAGES)
        if metadata:
            try:await asyncio.to_thread(expansion.received,store,identity,metadata)
            except Exception:pass
        status, body, overflow = 500, bytearray(), False
        started = time.monotonic()
        async def capture(message):
            nonlocal status, overflow
            if message['type'] == 'http.response.start':
                status = message['status']
            elif message['type'] == 'http.response.body':
                if len(body) + len(message.get('body', b'')) <= 8*1024*1024:
                    body.extend(message.get('body', b''))
                else:
                    overflow = True
            await send(message)
        try:
            await self.app(scope, receive, capture)
        finally:
            try:
                data = json.loads(body) if body and not overflow else None
                event, outcome = response_outcome(name, status, data)
                # Preserve the original metric and deduplicate only immutable completions.
                fields={'session_save':('provider_session_id',),'judge_bind':('provider_session_id',),
                    'knowledge_save':('knowledge_dataset_id','version'),'tests_save':('retrieval_eval_set_id','eval_set_id','version','eval_set_version'),
                    'chat':('turn_id',),'knowledge_generate':('draft_id',),'tests_generate':('draft_id',),'trace_analyze':('draft_id',),
                    'baseline':('run_id',),'retest':('run_id',),'run':('run_id',),'knowledge_index':('index_id',),
                    'compare':('comparison_id',),'materials_generate':('material_id',),'materials_edit':('material_id',),
                    'materials_regenerate':('material_id',),'change_apply':('change_id',),'change_save':('change_id',),
                    'change_rollback':('change_id',),'decision_save':('decision_id','status','confirmed_at'),
                    'evidence_save':('evidence_object_id',),'review_save':('review_id',),'conclusion_save':('conclusion_id',),
                    'interview_save':('attempt_id',),'chat_draft':('case_id',),'repeat_run':('report_id',)}
                identifier=':'.join(str(data[k]) for k in fields.get(event,()) if isinstance(data,dict) and data.get(k) is not None)
                key=hashlib.sha256((identity+event+identifier).encode()).hexdigest() if identifier and outcome in {'SUCCESS','PARTIAL'} else None
                duration=round((time.monotonic()-started)*1000)
                await asyncio.to_thread(store.record,identity,event,outcome,event_id=key,duration_ms=duration)
                if metadata:
                    final_outcome=outcome
                    if event=='trace_analyze' and isinstance(data,dict):
                        sources=data.get('sources',{})
                        if isinstance(sources,dict):
                            run=sources.get('run',{})
                            metadata['context']='comparison' if 'comparison' in sources else {'BASELINE':'baseline_trace','RETEST':'retest_trace'}.get(run.get('run_type') if isinstance(run,dict) else None,'unknown')
                    if event in {'baseline','retest','run'} and isinstance(data,dict) and data.get('status') in {'CREATED','PENDING','RUNNING','QUEUED'}:final_outcome='WAITING'
                    if event in {'baseline','retest'}:metadata['action']='run.'+event
                    await asyncio.to_thread(expansion.result,store,identity,metadata,final_outcome,min(duration,3600000),expansion.error_category(status,data,final_outcome),key)

            except Exception:
                # Never log exception/request/response contents or break product operations.
                pass

    @staticmethod
    async def small_json(request, limit=2048):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > limit:
                return None
        try:
            return json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return None
