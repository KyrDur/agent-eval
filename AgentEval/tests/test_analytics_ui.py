import uuid

from experiments.analytics import AnalyticsStore, PAGES
from experiments import analytics_v2 as v2


def row(action='welcome.content', stage='exposure', **extra):
    value = dict(stage=stage, action=action, page='welcome', page_visit='visit', session='session',
        event_id=str(uuid.uuid4()), placement='LandingPage.content_product', path='RETRIEVAL',
        entry='home', material='unknown', role='unknown', context='unknown', reason='none',
        state='none', operation='', retry_of='', duration_ms=0,
        ui_variant='muji_20261012', layout='wide', content='product', example_kind='unknown',
        issue_kind='unknown', reveal='unknown', preparation_flow='')
    return {**value, **extra}


def test_v3_fixed_dimensions_and_legacy_client_compatibility(tmp_path):
    store = AnalyticsStore(tmp_path)
    assert v2.validate(row(), PAGES)
    legacy = {k: v for k, v in row().items() if k not in v2.UI_FIELDS}
    assert v2.validate(legacy, PAGES)
    for key in v2.UI_FIELDS - {'preparation_flow'}:
        assert not v2.validate(row(**{key: 'PRIVATE USER INPUT'}), PAGES)
    assert not v2.validate(row(preparation_flow='business/id'), PAGES)
    assert not v2.validate({**row(), 'input_value': 'secret'}, PAGES)
    v2.client_batch(store, 'browser', [legacy, row()])
    visual = store.report()['expansion']['visual']
    assert visual['version'] == 3
    assert {r['ui_variant'] for r in visual['content']} == {'unknown', 'muji_20261012'}
    assert not store.report(source='historical')['expansion']['visual']['collected']


def test_ctr_and_six_teaching_categories_are_separate(tmp_path):
    store = AnalyticsStore(tmp_path)
    v2.client_batch(store, 'a', [row('welcome.setup', content='unknown'),
        row('welcome.setup', 'interaction', content='unknown')])
    v2.client_batch(store, 'b', [row('welcome.setup', 'interaction', layout='compact', content='unknown')])
    items = [row('guide.issue', page='evaluate', placement='JourneyGuide.issue', content='unknown',
                 issue_kind=k, reveal='manual') for k in v2.CONTRACT['issue_kinds'] if k != 'unknown']
    v2.client_batch(store, 'a', items)
    v2.client_batch(store, 'a', items)
    visual = store.report()['expansion']['visual']
    assert len([r for r in visual['content'] if r['action'] == 'guide.issue']) == 6
    assert all(r['exposures'] == 1 for r in visual['content'] if r['action'] == 'guide.issue')
    buttons = {r['layout']: r for r in visual['buttons']}
    assert buttons['wide']['click_rate'] == 1
    assert buttons['compact']['click_rate'] is None
    store.exclude('a', True)
    assert store.report()['expansion']['visual']['content'] == []


def test_preparation_failure_retry_and_hashed_flow(tmp_path):
    store = AnalyticsStore(tmp_path)
    flow_id=str(uuid.uuid4())
    for action, op, outcome in [('knowledge.save', 'save', 'SUCCESS'),
                               ('knowledge.index', 'index-one', 'FAILED'),
                               ('knowledge.index', 'index-two', 'SUCCESS')]:
        event = row(action, 'submitted', operation=op, preparation_flow=flow_id, content='unknown')
        assert v2.validate(event, PAGES)
        v2.client_batch(store, 'browser', [event])
        metadata = {**event, 'stage': 'received'}
        v2.received(store, 'browser', metadata)
        v2.result(store, 'browser', metadata, outcome, 10, 'none')
    flow = store.report()['expansion']['visual']['preparation'][0]
    assert (flow['started'], flow['saved'], flow['completed'], flow['failed'], flow['index_retries']) == (1, 1, 1, 0, 1)
    with store.connect() as db:
        assert all(r[0] != flow_id and len(r[0]) == 64 for r in db.execute('SELECT preparation_flow FROM stage_ui'))


def test_original_v2_writer_and_new_store_can_share_database(tmp_path):
    store = AnalyticsStore(tmp_path)
    # Reproduce the v2 INSERT used by retained containers, independent of an output artifact.
    legacy = {k: v for k, v in row().items() if k not in v2.UI_FIELDS}
    with store.connect() as db:
        assert len(list(db.execute('PRAGMA table_info(stages)'))) == 21
        db.execute('INSERT OR IGNORE INTO stages VALUES ('+','.join('?'*21)+')', v2.write(store, 'old-browser', legacy))
    old = store.report()['expansion']['visual']['content'][0]
    assert old['ui_variant'] == old['layout'] == 'unknown'
    salt, started = store.salt, store.report()['started_at']
    again = AnalyticsStore(tmp_path)
    assert again.salt == salt and again.report()['started_at'] == started
    assert again.report()['expansion']['visual']['content'] == store.report()['expansion']['visual']['content']


def test_evidence_path_uses_time_order_and_same_anonymous_session(tmp_path):
    store = AnalyticsStore(tmp_path)
    before = row('trace.analyze', 'submitted', page='evaluate', operation='before')
    v2.result(store, 'a', before, 'SUCCESS', 10, 'none')
    opening = row('evidence.details', 'interaction', page='evaluate', state='expand')
    v2.client_batch(store, 'a', [opening])
    v2.result(store, 'b', row('review.save', operation='other'), 'SUCCESS', 10, 'none')
    v2.result(store, 'a', row('conclusion.save', operation='after'), 'SUCCESS', 10, 'none')
    path = store.report()['expansion']['visual']['evidence_path'][0]
    assert path['evidence_sessions'] == path['recorded_sessions'] == 1
    assert path['analyzed_sessions'] == path['reviewed_sessions'] == 0
