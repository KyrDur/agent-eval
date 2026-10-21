"""Aggregate fixed UI dimensions only; never return visitor or operation tokens."""
from collections import defaultdict
from datetime import datetime, timezone


def summarize_ui(rows, started, collected):
    result = dict(version=3, started_at=started, collected=collected,
                  segments=[], buttons=[], content=[], preparation=[], evidence_path=[])
    if not collected:
        return result
    segments = defaultdict(list)
    buttons = defaultdict(list)
    content = defaultdict(list)
    flows = defaultdict(list)
    sessions = defaultdict(list)
    for row in rows:
        segment = (row['ui_variant'], row['layout'])
        segments[segment].append(row)
        if row['stage'] in {'exposure', 'interaction'}:
            buttons[(*segment, row['page'], row['action'], row['placement'])].append(row)
        if row['action'] in {'welcome.content', 'welcome.evidence', 'guide.issue'}:
            content[(*segment, row['action'], row['content'], row['example_kind'],
                     row['issue_kind'], row['reveal'])].append(row)
        if row['preparation_flow'] and row['action'] in {'knowledge.save', 'knowledge.index'}:
            flows[(row['visitor'], row['preparation_flow'])].append(row)
        if row['session']:
            sessions[(*segment, row['visitor'], row['session'])].append(row)

    for (variant, layout), group in sorted(segments.items()):
        entered = [r for r in group if r['stage'] == 'page_enter']
        submitted = {(r['visitor'], r['operation']) for r in group if r['stage'] == 'submitted'}
        completed = {(r['visitor'], r['operation']) for r in group
                     if r['stage'] == 'result' and r['outcome'] == 'SUCCESS'}
        result['segments'].append(dict(ui_variant=variant, layout=layout,
            page_entries=len(entered), browsers=len({r['visitor'] for r in entered}),
            submitted=len(submitted), completed=len(completed)))
    for (variant, layout, page, action, placement), group in sorted(buttons.items()):
        if action in {'welcome.content', 'guide.issue'}:
            continue
        exposed = {r['visitor'] for r in group if r['stage'] == 'exposure'}
        clicked = {r['visitor'] for r in group if r['stage'] == 'interaction'}
        result['buttons'].append(dict(ui_variant=variant, layout=layout, page=page,
            action=action, placement=placement, clicks=sum(r['stage'] == 'interaction' for r in group),
            exposed_browsers=len(exposed), clicked_browsers=len(clicked),
            exposed_clicked_browsers=len(exposed & clicked),
            click_rate=len(exposed & clicked)/len(exposed) if exposed else None))
    for (variant, layout, action, section, example, issue, reveal), group in sorted(content.items()):
        exposed = [r for r in group if r['stage'] == 'exposure']
        clicked = [r for r in group if r['stage'] == 'interaction']
        result['content'].append(dict(ui_variant=variant, layout=layout, action=action,
            content=section, example_kind=example, issue_kind=issue, reveal=reveal,
            exposures=len(exposed), exposed_browsers=len({r['visitor'] for r in exposed}),
            clicks=len(clicked), clicked_browsers=len({r['visitor'] for r in clicked})))

    preparation = defaultdict(lambda: defaultdict(int))
    for group in flows.values():
        group.sort(key=lambda r: r['timestamp'])
        submitted = [r for r in group if r['stage'] == 'submitted']
        if not submitted:
            continue
        first = submitted[0]
        stats = preparation[(first['ui_variant'], first['layout'])]
        stats['started'] += 1
        stats['reused_saved'] += not any(r['action'] == 'knowledge.save' for r in submitted)
        stats['saved'] += any(r['action'] == 'knowledge.save' and r['stage'] == 'result'
                              and r['outcome'] == 'SUCCESS' for r in group)
        outcomes = [r for r in group if r['stage'] == 'result']
        indexed = [r for r in outcomes if r['action'] == 'knowledge.index']
        last = indexed[-1] if indexed else outcomes[-1] if outcomes else None
        # An earlier failed index followed by a successful retry is one completed flow.
        if indexed and last['outcome'] == 'SUCCESS':
            status = 'completed'
        elif last and last['outcome'] in {'FAILED', 'PARTIAL'}:
            status = 'failed'
        elif last and last['outcome'] in {'UNKNOWN', 'DUPLICATE'}:
            status = 'unknown'
        elif any(r['stage'] == 'transport_error' for r in group) or (
                datetime.now(timezone.utc)-datetime.fromisoformat(submitted[-1]['timestamp'])).total_seconds() > 300:
            status = 'unobserved'
        else:
            status = 'waiting'
        stats[status] += 1
        stats['index_retries'] += max(0, sum(r['action'] == 'knowledge.index' for r in submitted)-1)
    for (variant, layout), stats in sorted(preparation.items()):
        result['preparation'].append(dict(ui_variant=variant, layout=layout,
            **{k: stats[k] for k in ('started', 'saved', 'reused_saved', 'completed', 'failed',
                                   'waiting', 'unobserved', 'unknown', 'index_retries')}))

    pathways = defaultdict(lambda: defaultdict(int))
    evidence_actions = {'evidence.details', 'case.details', 'run.answer', 'trace.evidence'}
    record_actions = {'change.propose', 'change.record', 'change.diagnose',
                      'change.confirm', 'conclusion.save'}
    for (variant, layout, _, _), group in sessions.items():
        openings = [r for r in group if r['stage'] == 'interaction'
                    and r['action'] in evidence_actions and r['state'] != 'collapse']
        if not openings:
            continue
        after = min(r['timestamp'] for r in openings)
        succeeding = {r['action'] for r in group if r['stage'] == 'result'
                      and r['outcome'] == 'SUCCESS' and r['timestamp'] >= after}
        stats = pathways[(variant, layout)]
        stats['evidence_sessions'] += 1
        stats['analyzed_sessions'] += 'trace.analyze' in succeeding
        stats['reviewed_sessions'] += 'review.save' in succeeding
        stats['recorded_sessions'] += bool(record_actions & succeeding)
    for (variant, layout), stats in sorted(pathways.items()):
        result['evidence_path'].append(dict(ui_variant=variant, layout=layout, **dict(stats)))
    return result
