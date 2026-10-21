"""Read-only historical snapshots; never import bodies into the analytics DB.

Run: python -m experiments.analytics_history --workspaces /state/workspaces
     --analytics /state/analytics --log /www/wwwlogs/www.test.softcue.xyz.log
Snapshots are not attempts, visits or real people. Only known saved objects with
explicit timestamps are eligible. Raw server logs stay on the server.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from .analytics import AnalyticsStore, SHANGHAI

GROUPS = {'knowledge_datasets':'knowledge_save', 'knowledge_indices':'knowledge_index',
          'retrieval_evalsets':'tests_save', 'evalsets':'tests_save',
          'chat_turns':'chat', 'retrieval_runs':'run', 'runs':'run',
          'retrieval_comparisons':'compare', 'comparisons':'compare'}


def import_snapshots(workspaces, analytics):
    counts, skipped = Counter(), Counter()
    browsers = set()
    for directory in sorted(Path(workspaces).iterdir()):
        if not re.fullmatch(r'[a-f0-9]{64}', directory.name) or not (directory/'workspace.json').is_file():
            continue
        browsers.add(directory.name)
        for path in sorted((directory/'artifacts').rglob('*.json')):
            group = path.parent.name
            name = GROUPS.get(group)
            if group == 'materials':
                name = 'materials_generate'
            if group == 'ai_drafts':
                name = 'draft'
            if group == 'provider_sessions':
                name = 'provider_snapshot'
            if not name:
                continue
            if path.stat().st_size > 16*1024*1024:
                skipped['large_file'] += 1
                continue
            try:
                envelope = json.loads(path.read_text())
                data = envelope['artifact']
                # Reject corrupt evidence instead of trusting filenames.
                from .canonical import digest
                if envelope.get('sha256') != digest(data):
                    skipped['integrity'] += 1
                    continue
                stamp = data.get('created_at')
                outcome = 'SUCCESS'
                if name == 'draft':
                    name = {'KNOWLEDGE':'knowledge_generate','TESTS':'tests_generate','TRACE':'trace_analyze'}.get(data.get('kind'))
                    if not name:
                        skipped['unknown_draft_kind'] += 1
                        continue
                elif name == 'provider_snapshot':
                    # Only a last successful stored connection is known; no test count.
                    stamp = data.get('last_tested_at')
                    if data.get('text_connection_status') != 'READY' or not stamp:
                        skipped['provider_without_successful_timestamp'] += 1
                        continue
                    name = 'api_connect'
                elif name == 'run':
                    stamp = data.get('finished_at') or stamp
                    name = {'BASELINE':'baseline','RETEST':'retest'}.get(data.get('run_type'),'run')
                    outcome = {'COMPLETE':'SUCCESS','PARTIAL':'PARTIAL','FAILED':'FAILED'}.get(data.get('status'),'UNKNOWN')
                elif name == 'chat':
                    outcome = 'SUCCESS' if data.get('status') == 'SUCCESS' else 'FAILED'
                if not isinstance(stamp, str) or datetime.fromisoformat(stamp.replace('Z','+00:00')).tzinfo is None:
                    skipped['missing_explicit_timezone'] += 1
                    continue
                key = hashlib.sha256(('historical:'+directory.name+str(path.relative_to(directory))).encode()).hexdigest()
                analytics.record(directory.name, name, outcome, source='historical', event_id=key, timestamp=stamp)
                counts[name] += 1
            except (ValueError, KeyError, TypeError, OSError):
                skipped['invalid_record'] += 1
    return {'workspace_directories':len(browsers),'eligible_saved_objects':dict(counts),'skipped':dict(skipped),
            'scope':'Saved snapshots only. Includes owner/testing; not visits, attempts or verified real users.'}


LOG_LINE = re.compile(r'^\S+ \S+ \S+ \[([^\]]+)\] "(\S+) ([^ ]+) [^"]+" (\d+) \S+ "([^"]*)" "([^"]*)"')
BOTS = re.compile(r'bot|spider|crawl|curl|python|wget|headless|monitor|health|Go-http-client',re.I)


def summarize_logs(paths):
    daily = defaultdict(Counter)
    counts = Counter()
    first = last = None
    for path in paths:
        path = Path(path)
        if not path.is_file():
            continue
        opener = gzip.open if path.suffix=='.gz' else open
        with opener(path,'rt',errors='replace') as stream:
            for line in stream:
                counts['requests'] += 1
                match = LOG_LINE.match(line)
                if not match:
                    counts['unparsed'] += 1
                    continue
                stamp, method, target, status, _, user_agent = match.groups()
                try:
                    date = datetime.strptime(stamp,'%d/%b/%Y:%H:%M:%S %z').astimezone(SHANGHAI)
                    url = urlsplit(target)
                except ValueError:
                    counts['unparsed'] += 1
                    continue
                first = min(first,date) if first else date
                last = max(last,date) if last else date
                row = daily[date.date().isoformat()]
                row['requests'] += 1
                if BOTS.search(user_agent):
                    row['known_bot_or_tool_requests'] += 1
                    continue
                # SPA shell requests are only a lower-detail signal. Client page
                # transitions never reach Nginx as a new shell request.
                if method=='GET' and status in {'200','304'} and url.path in {'/','/index.html'}:
                    row['browser_like_shell_requests'] += 1
                    counts['browser_like_shell_requests'] += 1
                if url.path.startswith('/api/'):
                    row['api_requests'] += 1
    return {'range_start':first.isoformat() if first else None,'range_end':last.isoformat() if last else None,
            'totals':dict(counts),'daily':[{'day':day,**dict(row)} for day,row in sorted(daily.items())],
            'scope':'HTTP requests, not historical PV/UV. No IPs or user agents are exported; bot filtering is heuristic.'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspaces',required=True)
    parser.add_argument('--analytics',required=True)
    parser.add_argument('--log',action='append',default=[])
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    store=AnalyticsStore(args.analytics)
    result={'generated_at':datetime.now(timezone.utc).isoformat(),
            'snapshots':import_snapshots(args.workspaces,store),'logs':summarize_logs(args.log)}
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    main()
