from pathlib import Path
import json
from experiments.analytics import AnalyticsStore
from experiments.analytics_history import import_snapshots, summarize_logs
from experiments.canonical import digest

def test_history_is_read_only_separate_deduplicated_and_no_body_import(tmp_path):
    directory=tmp_path/'workspaces'/('a'*64)
    directory.mkdir(parents=True)
    (directory/'workspace.json').write_text('{"version":1}')
    path=directory/'artifacts/chat_turns/one.json'
    path.parent.mkdir(parents=True)
    data={'created_at':'2026-10-11T01:00:00Z','status':'SUCCESS','message':'PRIVATE CHAT','answer':'PRIVATE OUTPUT'}
    path.write_text(json.dumps({'sha256':digest(data),'artifact':data}))
    before=path.read_bytes()
    analytics=AnalyticsStore(tmp_path/'analytics')
    summary=import_snapshots(tmp_path/'workspaces',analytics)
    import_snapshots(tmp_path/'workspaces',analytics)
    assert summary['eligible_saved_objects']=={'chat':1}
    assert analytics.report()['events']==[]
    assert analytics.report(days=90,source='historical')['events'][0]['count']==1
    assert path.read_bytes()==before
    with analytics.connect() as db:
        assert 'PRIVATE' not in json.dumps([tuple(row) for row in db.execute('SELECT * FROM events')])

def test_log_summary_never_exports_ips_query_values_or_agents(tmp_path):
    log=tmp_path/'access.log'
    log.write_text('''192.0.2.1 - - [11/Oct/2026:00:01:00 +0000] "GET /?key=SECRET HTTP/1.1" 200 300 "-" "Mozilla/5.0"
192.0.2.2 - - [11/Oct/2026:00:02:00 +0000] "GET / HTTP/1.1" 200 300 "-" "curl/8.0"
192.0.2.1 - - [11/Oct/2026:00:03:00 +0000] "GET /api/private HTTP/1.1" 200 300 "-" "Mozilla/5.0"
''')
    summary=summarize_logs([log])
    assert summary['totals']['browser_like_shell_requests']==1
    assert summary['daily'][0]['known_bot_or_tool_requests']==1
    assert summary['daily'][0]['api_requests']==1
    raw=json.dumps(summary)
    assert '192.0.2' not in raw and 'SECRET' not in raw and 'Mozilla' not in raw
