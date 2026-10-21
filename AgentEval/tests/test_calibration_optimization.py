"""Software fixtures only, never independent human research results."""
import asyncio
from copy import deepcopy
import hashlib
import json

import pytest
from pydantic import ValidationError

from test_calibration import env, annotate, judgment, protocol, run, sample, ScriptedProvider
from experiments.calibration_models import CalibrationResult, CalibrationSample, JudgeProtocolVersion, Judgment
from evaluation.calibration import score_answer
from evaluation.calibration_evidence import evidence_fragments, fragment_input, resolve_fragment_judgment
from evaluation.calibration_metrics import metrics_with_slices


@pytest.mark.parametrize('validation_output',['invalid-json','PENDING','PASS'])
def test_profile_adoption_requires_full_valid_scope_even_with_human_fixture(env,validation_output):
    # HUMAN records below are synthetic software fixtures, never study evidence.
    for s in env.dataset.samples:
        annotate(env,s,source='HUMAN')
    baseline=protocol(env);candidate=protocol(env,'J2',baseline.protocol_id)
    run(env,baseline,'adoption-baseline');run(env,candidate,'adoption-candidate')
    lock=env.cal.lock(env.dataset.dataset_id,env.rubric.rubric_id,baseline.protocol_id,
        candidate.protocol_id,'Synthetic acceptance boundary',1,2,'synthetic-annotator')
    ScriptedProvider.output='not-json' if validation_output=='invalid-json' else judgment(validation_output)
    final=asyncio.run(env.cal.validate(lock.validation_id,env.sid,env.sid,'synthetic-annotator'))
    assert final.status=='COMPLETE'  # Acquisition finished, not proof of valid evaluation.
    from experiments.scoring_profiles import available_profiles
    if validation_output=='PASS':
        conclusion=env.cal.conclude(final.comparison_id,'ADOPT','Fixture only','synthetic-annotator',final.validation_id)
        assert conclusion.report_snapshot['adoption_gate']['eligible']
        assert conclusion.conclusion_id in {p['profile_id'] for p in available_profiles(env.cal.store)}
    else:
        with pytest.raises(ValueError,match='ADOPTION_REQUIRES_COMPLETE_EVALUATION'):
            env.cal.conclude(final.comparison_id,'ADOPT','Fixture only','synthetic-annotator',final.validation_id)
        conclusion=env.cal.conclude(final.comparison_id,'KEEP_BASELINE','Insufficient valid evidence','synthetic-annotator',final.validation_id)
        assert conclusion.research_status=='PENDING'
        assert conclusion.report_snapshot['adoption_gate']['restrictions']
        assert len(available_profiles(env.cal.store))==1
        assert '不能采用为已验证评分方案' in env.cal.export(conclusion.conclusion_id)['markdown']


def fragment_output(s):
    catalog=evidence_fragments(s)
    answer=next(f['fragment_id'] for f in catalog if f['scope']=='ANSWER')
    retrieved=next(f['fragment_id'] for f in catalog if f['scope']=='RETRIEVED')
    reference=next(f['fragment_id'] for f in catalog if f['scope']=='REFERENCE')
    data=judgment()
    data['dimensions']={k:{'score':2,'answer_fragment_ids':[answer],
        'evidence_fragment_ids':[retrieved if k=='faithfulness' else reference],
        'reason':'Synthetic fragment protocol fixture.'} for k in data['dimensions']}
    return data


def test_fragment_positions_preserve_markdown_negation_numbers_and_source_hash():
    s=CalibrationSample.model_validate(sample(answer='  **注意：**过期 3 天不能退。\n'+('保留原文。'*130)))
    fs=evidence_fragments(s)
    assert len(fs)==len({f['fragment_id'] for f in fs})
    for f in fs:
        source=s.answer if f['scope']=='ANSWER' else next(e.text for e in
            (s.retrieved_evidence if f['scope']=='RETRIEVED' else s.reference_policy) if e.evidence_id==f['evidence_id'])
        assert source[f['start']:f['end']]==f['text']
        assert f['source_sha256']==hashlib.sha256(source.encode()).hexdigest()
        assert len(f['text'])<=500
    assert '**注意：**过期 3 天不能退。' in fs[0]['text']
    assert 'partition' not in fragment_input(s)


def test_fragment_protocol_scores_only_current_ids_and_retains_raw_and_provenance(env):
    s=env.dataset.samples[0]
    p=env.cal.create_protocol(env.dataset.dataset_id,env.rubric.rubric_id,env.sid,'fragment fixture','J1','fixture',citation_mode='FRAGMENT_IDS')
    ScriptedProvider.output=fragment_output(s)
    result=run(env,p)
    record=env.cal.store.get('calibration_runs',result['run_id'])
    r=record.results[0]
    assert r.status=='SUCCESS' and r.judgment.verdict=='PASS'
    assert r.judgment.dimensions['faithfulness'].answer_quotes==[s.answer]
    assert r.citation_provenance and json.loads(r.raw_output)==ScriptedProvider.output
    assert record.protocol_snapshot.parser_version=='2'
    assert record.sample_snapshot[0].answer==s.answer
    loaded=env.cal.store.get('calibration_protocols',p.protocol_id)
    assert loaded.output_schema=='CALIBRATION_FRAGMENT_JUDGMENT_V2'


@pytest.mark.parametrize('failure',['unknown','wrong_scope','duplicate','other_sample'])
def test_fragment_ids_cannot_be_forged_or_cross_scope_or_sample(failure,env):
    s=env.dataset.samples[0];data=fragment_output(s);d=data['dimensions']['faithfulness']
    if failure=='unknown':d['answer_fragment_ids']=['A-not-in-frozen-input']
    elif failure=='wrong_scope':d['answer_fragment_ids']=d['evidence_fragment_ids']
    elif failure=='duplicate':d['answer_fragment_ids']*=2
    else:
        other=CalibrationSample.model_validate(sample(answer='另一份回答，不能借用。'))
        d['answer_fragment_ids']=[evidence_fragments(other)[0]['fragment_id']]
    p=env.cal.create_protocol(env.dataset.dataset_id,env.rubric.rubric_id,env.sid,'bad fragments','J1','fixture',citation_mode='FRAGMENT_IDS')
    provider=ScriptedProvider(p.provider_configuration,'fixture-key');ScriptedProvider.output=data
    r=asyncio.run(score_answer(provider,p,env.rubric,s,1))
    assert r.status=='CONTENT_INVALID' and r.judgment is None
    assert r.raw_output and r.error.startswith('FRAGMENT_')


def test_fragment_schema_cannot_bypass_with_legacy_quote_fields(env):
    data=fragment_output(env.dataset.samples[0]);data['dimensions']['faithfulness']['answer_quotes']=['made-up quote']
    with pytest.raises(ValueError,match='FRAGMENT_SCHEMA_INVALID'):
        resolve_fragment_judgment(data,env.dataset.samples[0])
    p=protocol(env)
    incompatible=p.model_dump();incompatible['parser_version']='2'
    with pytest.raises(ValidationError):JudgeProtocolVersion.model_validate(incompatible)


def test_version_change_is_explicit_and_legacy_still_scores(env):
    old=protocol(env);old_run=run(env,old,'old')
    new=env.cal.create_protocol(env.dataset.dataset_id,env.rubric.rubric_id,env.sid,'new','J1','citation change',
        parent_protocol_id=old.protocol_id,citation_mode='FRAGMENT_IDS')
    assert set(new.declared_changes)=={'prompt','evidence_input','output_schema','parser_version'}
    assert env.cal.store.get('calibration_protocols',old.protocol_id).parser_version=='1'
    assert env.cal.store.get('calibration_runs',old_run['run_id']).results[0].status=='SUCCESS'


def test_annotation_view_hides_others_until_actor_submits_and_keeps_progress(env):
    s=env.dataset.samples[0]
    a=annotate(env,s,actor='fixture-a',source='HUMAN')
    hidden=env.cal.annotation_view(env.dataset.dataset_id,env.rubric.rubric_id,'fixture-b')
    assert hidden['annotations']==[] and hidden['references']=={}
    assert hidden['own_submitted_count']==0 and hidden['hidden_sample_count']==2
    assert hidden['progress'][0]['submitted_count']==1
    assert 'Synthetic fixture reason' not in json.dumps(hidden)
    annotate(env,s,actor='fixture-b',source='HUMAN',value='FAIL')
    visible=env.cal.annotation_view(env.dataset.dataset_id,env.rubric.rubric_id,'fixture-b')
    assert a.annotation_id in [row.annotation_id for row in visible['annotations']]
    assert visible['references'][s.sample_id]['state']=='DISAGREEMENT'
    reopened=env.cal.open_blind(env.dataset.dataset_id,s.sample_id,env.rubric.rubric_id,'fixture-b')
    assert reopened['prior_peer_exposure']
    review=annotate(env,s,actor='fixture-b',source='HUMAN')
    assert review.seen_peer and not review.independent
    assert env.cal.reference(env.dataset.dataset_id,env.rubric.rubric_id)[s.sample_id]['state']=='DISAGREEMENT'


def make_issue(env):
    s=env.dataset.samples[0];annotate(env,s)
    p=protocol(env);r=run(env,p,'initial-issue-run')
    issue=env.cal.create_issue(env.dataset.dataset_id,s.sample_id,r['run_id'],'synthetic-annotator',
        'Fixture issue','PROMPT','fixture-owner','Observed fixture discrepancy, not a real defect claim.',repair_plan={'success_criteria':'Correct the fixture discrepancy','target_error':'Fixture Judge reading error','potential_regressions':'Check opposite fixture','validation_scope':'Same fixture only','verification_sample_ids':[s.sample_id]})
    return issue,p


def test_issue_requires_visible_sample_and_cannot_skip_to_fixed(env):
    issue,p=make_issue(env)
    assert env.cal.issues_view(env.dataset.dataset_id,'unsubmitted-actor')==[]
    with pytest.raises(ValueError,match='ISSUE_TRANSITION_INVALID'):
        env.cal.update_issue(issue.issue_id,'synthetic-annotator','CLOSED','Cannot close without evidence')
    reproduced=env.cal.update_issue(issue.issue_id,'synthetic-annotator','REPRODUCED','Fixture reproduced')
    with pytest.raises(ValueError,match='ISSUE_CHANGE_REQUIRED'):
        env.cal.update_issue(issue.issue_id,'synthetic-annotator','CHANGED','Missing change',previous_event_id=reproduced.event_id)
    changed=env.cal.update_issue(issue.issue_id,'synthetic-annotator','CHANGED','Changed fixture',previous_event_id=reproduced.event_id,change_summary='One declared adjustment')
    with pytest.raises(ValueError,match='ISSUE_VERIFICATION_REQUIRED'):
        env.cal.update_issue(issue.issue_id,'synthetic-annotator','RETESTED','Missing run',previous_event_id=changed.event_id)
    with pytest.raises(ValueError,match='ISSUE_VERIFICATION_INVALID'):
        env.cal.update_issue(issue.issue_id,'synthetic-annotator','RETESTED','Same run',previous_event_id=changed.event_id,verification_run_id=issue.run_id,outcome='FIXED')
    candidate=protocol(env,'J2',p.protocol_id)
    retest=run(env,candidate,'new-issue-run')
    tested=env.cal.update_issue(issue.issue_id,'synthetic-annotator','RETESTED','New acquired evidence',previous_event_id=changed.event_id,verification_run_id=retest['run_id'],outcome='FIXED',verification_report={'target_eliminated':True,'regression_checked':True,'regression_found':False,'regression_result':'Checked software fixture only','validation_scope':'Same fixture; no independent new-case evidence'})
    closed=env.cal.update_issue(issue.issue_id,'synthetic-annotator','CLOSED','Explicit research decision',previous_event_id=tested.event_id)
    assert closed.from_status=='RETESTED'
    assert env.cal.issues_view(env.dataset.dataset_id,'synthetic-annotator')[0]['status']=='CLOSED'
    with pytest.raises(ValueError):env.cal.store.put('calibration_issues',issue)
    with pytest.raises(ValueError):env.cal.store.put('calibration_issue_events',tested)


def test_issue_conflict_and_failed_retest_cannot_be_claimed_fixed(env):
    issue,p=make_issue(env)
    reproduced=env.cal.update_issue(issue.issue_id,'synthetic-annotator','REPRODUCED','Reproduced')
    with pytest.raises(ValueError,match='ISSUE_EVENT_CONFLICT'):
        env.cal.update_issue(issue.issue_id,'synthetic-annotator','UNRESOLVED','Stale client')
    changed=env.cal.update_issue(issue.issue_id,'synthetic-annotator','CHANGED','Changed',previous_event_id=reproduced.event_id,change_summary='Fixture adjustment')
    candidate=protocol(env,'J2',p.protocol_id)
    ScriptedProvider.error='RATE_LIMITED';failed=run(env,candidate,'failed-retest')
    with pytest.raises(ValueError,match='ISSUE_VERIFICATION_INVALID'):
        env.cal.update_issue(issue.issue_id,'synthetic-annotator','RETESTED','No usable score',previous_event_id=changed.event_id,verification_run_id=failed['run_id'],outcome='FIXED')
    tested=env.cal.update_issue(issue.issue_id,'synthetic-annotator','RETESTED','Failure retained',previous_event_id=changed.event_id,verification_run_id=failed['run_id'],outcome='INCONCLUSIVE')
    with pytest.raises(ValueError,match='ISSUE_VERIFICATION_REQUIRED'):
        env.cal.update_issue(issue.issue_id,'synthetic-annotator','CLOSED','Cannot assert fixed',previous_event_id=tested.event_id)


def test_reconciliation_detects_equal_counts_with_wrong_ids_and_duplicate_scores():
    s=CalibrationSample.model_validate(sample())
    one=CalibrationResult(sample_id=s.sample_id,repetition=1,status='SUCCESS',judgment=Judgment.model_validate(judgment()))
    refs={s.sample_id:{'state':'SINGLE','judgment':judgment('FAIL')}}
    m=metrics_with_slices([s],[one,one],refs,2)
    assert m['reconciliation']=={'expected':2,'received':2,'missing':1,'duplicates':1,'unexpected':0,'balanced':False}
    assert m['coverage']['numerator']==0 and m['health']['DUPLICATE_RESULT']==1
    assert m['unavailable_on_human_fail']['numerator']==2
    assert m['repeat_stability']['denominator']==1 and m['repeat_stability']['numerator']==0
    other=one.model_copy(update={'sample_id':'unexpected'})
    unexpected=metrics_with_slices([s],[other],refs,1)
    assert unexpected['reconciliation']['unexpected']==1 and not unexpected['reconciliation']['balanced']
