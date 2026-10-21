"""Adapter boundaries: reference leakage, credential parsing, and abstention."""
import json
from types import SimpleNamespace
import pytest
from experiments.langsmith_eval import (
    examples_for, judge_feedback, load_data, read_config,
    alias_sample_input, normalize_alias_judgment,
    feedback_matches,
)
from experiments.calibration_models import CalibrationSample, RubricVersion
from evaluation.calibration import RUBRIC_TEMPLATE
from experiments.canonical import digest


def case_data():
    return {'name': 'test', 'documents': [], 'cases': [{
        'case_id': 'r1', 'query': '退款多久到账？', 'context': [],
        'expected_answer': '审核通过后五至七个工作日。', 'relevant_document_ids': ['refund'],
        'relevant_chunk_ids': [], 'must_do': ['先核验订单'], 'must_not_do': ['声称退款已完成'],
        'scenario': None, 'partition': 'DEBUG', 'source': 'demo',
    }]}


def test_reference_answer_and_labels_stay_out_of_generation_inputs():
    example = examples_for(case_data(), 'abc')[0]
    assert set(example['inputs']) == {'case_id', 'query', 'context'}
    assert '五至七' not in json.dumps(example['inputs'], ensure_ascii=False)
    assert example['outputs']['relevant_document_ids'] == ['refund']
    assert example['outputs']['must_not_do'] == ['声称退款已完成']


def test_failed_judge_never_becomes_answer_pass():
    feedback = judge_feedback(SimpleNamespace(status='CONTENT_INVALID', error='EVIDENCE_QUOTE_INVALID', judgment=None))
    assert all(item['key'] != 'answer_pass' for item in feedback)
    assert next(item['value'] for item in feedback if item['key'] == 'verdict') == 'UNAVAILABLE'


def test_pending_and_not_applicable_have_no_fabricated_numeric_score():
    judgment = SimpleNamespace(
        dimensions={'faithfulness': SimpleNamespace(score='INSUFFICIENT', reason='缺少证据'),
                    'actionability': SimpleNamespace(score='NA', reason='纯事实题')},
        verdict='PENDING', reason='证据不足', task_resolved='INSUFFICIENT',
        faithful_to_available='INSUFFICIENT', critical_errors=[],
    )
    feedback = judge_feedback(SimpleNamespace(status='SUCCESS', error=None, judgment=judgment))
    assert all(item['key'] != 'answer_pass' for item in feedback)
    for item in feedback:
        if item['key'] in ('faithfulness', 'actionability'):
            assert 'score' not in item


def test_credential_file_is_literal_and_environment_takes_precedence(tmp_path, monkeypatch):
    config = tmp_path / 'config.env'
    config.write_text('AGENTEVAL_TEST_LITERAL=$(touch should-not-exist)\nAGENTEVAL_TEST_EXISTING=file-value\n')
    config.chmod(0o600)
    monkeypatch.setenv('AGENTEVAL_TEST_EXISTING', 'env-value')
    values = read_config(config)
    assert values['AGENTEVAL_TEST_LITERAL'] == '$(touch should-not-exist)'
    assert values['AGENTEVAL_TEST_EXISTING'] == 'env-value'
    assert not (tmp_path / 'should-not-exist').exists()


def test_readable_by_other_users_credential_file_is_rejected(tmp_path):
    config = tmp_path / 'config.env'
    config.write_text('LANGSMITH_API_KEY=fake-secret\n')
    config.chmod(0o644)
    with pytest.raises(ValueError, match='CONFIG_PERMISSIONS_REQUIRE_600'):
        read_config(config)


def test_duplicate_case_ids_do_not_overwrite_results(tmp_path):
    data = case_data()
    data['cases'] *= 2
    path = tmp_path / 'cases.json'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='DATASET_CASE_IDS_INVALID'):
        load_data(path, 8)


def aliased_judge_fixture():
    sample = CalibrationSample(sample_id='r1', group_id='r1', partition='CALIBRATION',
        question='退款多久？', answer='审核后五至七个工作日。', origin='CONSTRUCTED',
        retrieved_evidence=[{'evidence_id': 'chunk1', 'document_id': 'refund', 'text': '审核后五至七个工作日。'}],
        reference_policy=[{'evidence_id': 'policy1', 'document_id': 'refund', 'text': '审核后五至七个工作日。'}],
        reference_complete=True)
    rubric = RubricVersion(**RUBRIC_TEMPLATE, content_hash=digest(RUBRIC_TEMPLATE))
    data, aliases = alias_sample_input(sample)
    raw = {'dimensions': {
        name: {'score': score, 'answer_fragment_ids': ['A1'],
               'evidence_fragment_ids': ['R1' if name == 'faithfulness' else 'P1'], 'reason': '原文支持'}
        for name, score in [('faithfulness', 2), ('conditions', 2), ('relevance', 1), ('actionability', 1)]
    }, 'critical_errors': [], 'error_tags': [], 'task_resolved': 'YES',
        'faithful_to_available': 'YES', 'task_failure_reasons': [], 'insufficient_items': [], 'reason': '按原文评分',
        'verdict': 'FAIL'}
    return sample, rubric, data, aliases, raw


def test_code_verdict_uses_frozen_thresholds_and_preserves_original_model_verdict():
    sample, rubric, _, aliases, raw = aliased_judge_fixture()
    judgment, provenance = normalize_alias_judgment(raw, aliases, sample, rubric)
    assert judgment.verdict == 'PASS'  # relevance=1 and actionability=1 meet this Rubric.
    assert raw['verdict'] == 'FAIL'    # Preserve the original response for audit.
    assert judgment.dimensions['faithfulness'].citations[0].quote == sample.retrieved_evidence[0].text
    assert all(p['source_sha256'] and p['fragment_id'].startswith(('A-', 'R-', 'P-')) for p in provenance)


def test_unknown_alias_is_rejected_without_guessing_a_nearby_fragment():
    sample, rubric, _, aliases, raw = aliased_judge_fixture()
    raw['dimensions']['faithfulness']['evidence_fragment_ids'] = ['R11']
    with pytest.raises(ValueError, match='FRAGMENT_ID_INVALID'):
        normalize_alias_judgment(raw, aliases, sample, rubric)


def test_wrong_scope_is_rejected_even_when_alias_exists():
    sample, rubric, _, aliases, raw = aliased_judge_fixture()
    raw['dimensions']['faithfulness']['evidence_fragment_ids'] = ['A1']
    with pytest.raises(ValueError, match='FRAGMENT_SCOPE_INVALID'):
        normalize_alias_judgment(raw, aliases, sample, rubric)


def test_code_verdict_below_threshold_is_fail_and_abstention_stays_pending():
    sample, rubric, _, aliases, raw = aliased_judge_fixture()
    raw['dimensions']['conditions']['score'] = 1
    judgment, _ = normalize_alias_judgment(raw, aliases, sample, rubric)
    assert judgment.verdict == 'FAIL'
    raw['dimensions']['conditions']['score'] = 'INSUFFICIENT'
    raw['insufficient_items'] = ['缺少条件信息']
    judgment, _ = normalize_alias_judgment(raw, aliases, sample, rubric)
    assert judgment.verdict == 'PENDING'


def test_cloud_rounding_is_allowed_but_materially_different_scores_are_rejected():
    assert feedback_matches(SimpleNamespace(score=0.3333, value=None), {'score': 1/3})
    assert not feedback_matches(SimpleNamespace(score=0.34, value=None), {'score': 1/3})
    assert not feedback_matches(SimpleNamespace(score=None, value='PASS'), {'value': 'PENDING'})
