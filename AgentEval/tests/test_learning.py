"""Synthetic teaching workflow acceptance; never actual learner or HUMAN results."""
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import pytest
from experiments.store import JsonStore
from experiments.learning_service import LearningService,LearningError
from experiments.learning_analytics import record
from experiments.analytics import AnalyticsStore

@pytest.fixture
def learning(tmp_path):return LearningService(SimpleNamespace(store=JsonStore(tmp_path/'workspace')))

def judgment(case,source='SELF'):
    e=case['evidence'][0]
    return {'judgment':'需要核对本轮证据，不凭分数下结论。','evidence':[{'evidence_id':e['evidence_id'],'quote':e['text']}],
        'candidate_causes':['DATA','UNCERTAIN'],'uncertainty':'其他解释尚未排除。','distinguishing_check':'固定回答，核对对象与原始返回。','source':source}

def progress(s,mode='TRAINING',case='p01',request='start-request'):
    v=s.start(case,mode,request);i=v['attempt_id']
    v=s.mutate(i,'initial',judgment(v['case']),'initial-request')
    v=s.mutate(i,'prediction',{'choice':'APPLY','expected_result':'目标误判消除','potential_cost':'观察其他案例退化','reason':'核对原文后试验'},'predict-request')
    v=s.mutate(i,'replay',{},'replay-request')
    v=s.mutate(i,'decision',{'decision':'DECLINE','reason':'证据仍不足以采用','limitations':'仅限教学回放'},'decide-request')
    return s.mutate(i,'transfer-start',{},'transfer-request')

def test_server_hides_answers_until_progress_and_never_calls_provider(learning):
    v=learning.start('p01','TRAINING','start-request');i=v['attempt_id']
    assert not v['reference'] and not v['hints'] and 'machine_verdict' not in v['case']
    assert not v['proposed_change'] and v['actual_model_requests']==0
    assert v['analytics_event']['family_id'] not in {'DATA','PROMPT','RUBRIC','AGENT'}
    assert 'analysis' not in json.dumps(learning.catalog())
    with pytest.raises(LearningError,match='INITIAL_REQUIRED'):learning.mutate(i,'hint',{'level':1},'hint-request')
    bad=judgment(v['case']);bad['evidence'][0]['quote']='并不存在的引用'
    with pytest.raises(LearningError,match='EVIDENCE_INVALID'):learning.mutate(i,'initial',bad,'bad-initial')
    v=learning.mutate(i,'initial',judgment(v['case']),'initial-request')
    assert v['initial_independent'] and not v['reference']
    with pytest.raises(LearningError,match='HINT_ORDER'):learning.mutate(i,'hint',{'level':3},'skip-hint')
    for level in range(1,4):v=learning.mutate(i,'hint',{'level':level},'hint-level-'+str(level))
    assert v['reference'] and v['highest_hint']==3
    assert not learning.store.list('calibration_annotations')


def test_independent_transfer_denominator_and_exposure_survive_new_attempt(learning):
    v=progress(learning);i=v['attempt_id']
    assert v['transfer_independent_eligible'] and not v['transfer_reference']
    assert v['transfer']['case_id']=='t01'
    assert 'machine_verdict' not in v['transfer']
    with pytest.raises(LearningError,match='TRANSFER_SUBMIT_REQUIRED'):learning.mutate(i,'transfer-feedback',{},'feedback-request')
    body=judgment(v['transfer']);v=learning.mutate(i,'transfer-submit',body,'submit-request')
    assert v['transfer_reference'] and v['review_status']=='PENDING_HUMAN_REVIEW'
    assert v['stage']=='COMPLETE_PENDING_REVIEW' and not v['learning_effect_verified']
    before=len(learning.events(i));learning.mutate(i,'transfer-submit',body,'submit-request');assert len(learning.events(i))==before
    second=progress(learning,request='second-start')
    assert not second['transfer_independent_eligible']
    s=learning.summary();assert s['transfer_entered']==2 and s['transfer_unsubmitted']==1
    assert s['verified_success_rate']==0 and s['independent_completion_rate']==.5
    exported=learning.export(i)['markdown'];assert 'LEARNER_WORK_NOT_HUMAN_GOLD' not in exported or '不是校准' in exported
    assert '待维护者确认' in exported and '本人输入来源声明' in exported


def test_free_mode_and_revealed_transfer_cannot_be_independent(learning):
    v=progress(learning,mode='FREE')
    assert v['reference'] and not v['transfer_independent_eligible']
    v=learning.mutate(v['attempt_id'],'transfer-feedback',{},'expose-request')
    v=learning.mutate(v['attempt_id'],'transfer-submit',judgment(v['transfer']),'submit-request')
    assert not v['events'][-1]['payload']['independent']
    with pytest.raises(LearningError,match='NOT_INDEPENDENT'):
        learning.review(v['attempt_id'],'fixture-reviewer',{},'fixture review',True,'MEETS_CRITERIA')


def test_concurrent_idempotency_workspace_isolation_and_analytics_allowlist(learning,tmp_path):
    with ThreadPoolExecutor(max_workers=4) as pool:values=list(pool.map(lambda _:learning.start('p01','TRAINING','same-request'),range(4)))
    assert len({v['attempt_id'] for v in values})==1 and len(learning.store.list('learning_attempts'))==1
    other=LearningService(SimpleNamespace(store=JsonStore(tmp_path/'other')))
    with pytest.raises(FileNotFoundError):other.view(values[0]['attempt_id'])
    analytics=AnalyticsStore(tmp_path/'analytics');metadata=values[0]['analytics_event']
    assert record(analytics,'fixture-workspace',metadata) and not record(analytics,'fixture-workspace',metadata)
    assert not record(analytics,'fixture-workspace',{**metadata,'answer':'private prose'})
    data=(tmp_path/'analytics/events.sqlite3').read_bytes();assert values[0]['attempt_id'].encode() not in data
    assert analytics.report()['learning']['attempts_started']==1
