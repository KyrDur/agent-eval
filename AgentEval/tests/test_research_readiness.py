"""Readiness fixtures are software data, never actual human research."""
from pathlib import Path
from test_calibration import env, annotate
from experiments.research_readiness import calibration_readiness


def snapshot(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in Path(root).rglob('*.json')}


def test_read_only_audit_neither_creates_exposure_nor_labels(env):
    before=snapshot(env.exp.store.root)
    result=calibration_readiness(env.exp.store,env.dataset.dataset_id,env.rubric.rubric_id)
    assert result['valid_reference_count']==0
    assert not result['ready_for_initial_judge_study']
    assert result['blockers']==['INDEPENDENT_VALID_REFERENCE_INCOMPLETE']
    assert snapshot(env.exp.store.root)==before


def test_codex_labels_and_disagreement_do_not_qualify_as_human_reference(env):
    for sample in env.dataset.samples:annotate(env,sample)
    result=calibration_readiness(env.exp.store,env.dataset.dataset_id,env.rubric.rubric_id)
    assert result['independent_human_annotators']==result['valid_reference_count']==0
    for sample in env.dataset.samples:annotate(env,sample,actor='test-human-A',source='HUMAN')
    result=calibration_readiness(env.exp.store,env.dataset.dataset_id,env.rubric.rubric_id)
    assert result['ready_for_initial_judge_study']
    assert result['independent_human_annotators']==1
    annotate(env,env.dataset.samples[0],actor='test-human-B',source='HUMAN',value='FAIL')
    result=calibration_readiness(env.exp.store,env.dataset.dataset_id,env.rubric.rubric_id)
    assert result['valid_reference_count']==1 and not result['ready_for_initial_judge_study']
    assert result['reference_states']['DISAGREEMENT']==1
