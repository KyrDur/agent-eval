"""Four-layer repair evidence acceptance, only synthetic fixtures."""
import asyncio
import pytest
from test_agent_eval_practice import env as rag_env,knowledge_pair
from test_calibration import env,annotate,protocol,run
from experiments.calibration_service import CalibrationService


def plan(sid):return {'success_criteria':'目标错误消除，观察新增退化','target_error':'具体遗漏或误判','potential_regressions':'其他条件仍有效','validation_scope':'仅原题，不声称新题泛化','verification_sample_ids':[sid]}
def report():return {'target_eliminated':True,'regression_checked':True,'regression_found':False,'regression_result':'已检查声明范围；无新增目标错误','validation_scope':'仅原题，未做未见新题'}

def test_main_rag_issue_requires_new_post_change_run_and_separates_closure(rag_env):
    a,b,c,_=knowledge_pair(rag_env);cal=CalibrationService(rag_env.exp)
    source=cal.issue_source(a.run_id,'opened','fixture')
    issue=cal.create_issue(source['dataset_id'],'opened',a.run_id,'fixture','真实运行链路软件样例','AGENT','fixture-owner','知识缺少条件的模拟证据',source_type='RETRIEVAL_RUN',repair_plan=plan('opened'),related_evidence=['source original policy'])
    e=cal.update_issue(issue.issue_id,'fixture','REPRODUCED','原题复现')
    e=cal.update_issue(issue.issue_id,'fixture','CHANGED','修改已记录',previous_event_id=e.event_id,change_summary='只补知识')
    with pytest.raises(ValueError,match='ISSUE_VERIFICATION_INVALID'):
        cal.update_issue(issue.issue_id,'fixture','RETESTED','旧运行不能作为新验证',previous_event_id=e.event_id,verification_run_id=b.run_id,outcome='FIXED',verification_report=report())
    new=asyncio.run(rag_env.rag.run(rag_env.sid,c.target_eval_set_id,run_type='RETEST',parent_run_id=a.run_id,change_id=c.change_id,verify_answers=True))
    with pytest.raises(ValueError,match='ISSUE_ACCEPTANCE_REQUIRED'):
        cal.update_issue(issue.issue_id,'fixture','RETESTED','技术完成不代表修复',previous_event_id=e.event_id,verification_run_id=new.run_id,outcome='FIXED')
    tested=cal.update_issue(issue.issue_id,'fixture','RETESTED','原题评分有效及明确验收',previous_event_id=e.event_id,verification_run_id=new.run_id,outcome='FIXED',verification_report=report())
    closed=cal.update_issue(issue.issue_id,'fixture','CLOSED','明确限定原题范围',previous_event_id=tested.event_id,closure_type='FIXED')
    assert closed.closure_type=='FIXED' and closed.evidence_level=='SAME_CASE'
    other=cal.create_issue(source['dataset_id'],'opened',a.run_id,'fixture','暂不修复','DATA','fixture-owner','证据不足待调查',source_type='RETRIEVAL_RUN')
    cal.update_issue(other.issue_id,'fixture','CLOSED','先保留材料以后调查',closure_type='DEFERRED')
    views=cal.issues_view(source['dataset_id'],'fixture');assert {v['closure_type'] for v in views}=={'FIXED','DEFERRED'}
    with pytest.raises(ValueError,match='ISSUE_SCOPE_INVALID'):cal.issue_source(a.run_id,'custom-exception','fixture')


def test_prompt_unchanged_successful_rescore_is_not_a_repair(env):
    s=env.dataset.samples[0];annotate(env,s);p=protocol(env);base=run(env,p)
    issue=env.cal.create_issue(env.dataset.dataset_id,s.sample_id,base['run_id'],'synthetic-annotator','提示修复样例','PROMPT','owner','固定回答上的误判',repair_plan=plan(s.sample_id))
    e=env.cal.update_issue(issue.issue_id,'synthetic-annotator','REPRODUCED','原题复现')
    e=env.cal.update_issue(issue.issue_id,'synthetic-annotator','CHANGED','声称修改',previous_event_id=e.event_id,change_summary='声称提示有改变')
    new=run(env,p,'unchanged-rescore')
    with pytest.raises(ValueError,match='ISSUE_CHANGE_NOT_OBSERVED'):
        env.cal.update_issue(issue.issue_id,'synthetic-annotator','RETESTED','请求成功不能证明修改生效',previous_event_id=e.event_id,verification_run_id=new['run_id'],outcome='FIXED',verification_report=report())


def test_derived_data_keeps_answer_parent_and_exposure_and_never_inherits_reference(env):
    s=env.dataset.samples[0];annotate(env,s);p=protocol(env);r=run(env,p)
    env.cal.run_view(r['run_id'],'synthetic-annotator')
    old_bytes=env.exp.store.path('calibration_datasets',env.dataset.dataset_id).read_bytes()
    child=env.cal.derive_input(env.dataset.dataset_id,s.sample_id,{'reference_complete':False},'核查发现参考政策不完整','clean-v2','mapping-v2','synthetic-annotator')
    value=next(v for v in child.samples if v.sample_id==s.sample_id)
    assert value.question==s.question and value.answer==s.answer
    assert value.provenance['parent_dataset_id']==env.dataset.dataset_id
    assert value.provenance['parent_input_id'] and not value.reference_complete
    assert env.exp.store.path('calibration_datasets',env.dataset.dataset_id).read_bytes()==old_bytes
    assert env.cal.reference(child.dataset_id,env.rubric.rubric_id)[s.sample_id]['state']=='MISSING'
    assert env.cal.open_blind(child.dataset_id,s.sample_id,env.rubric.rubric_id,'synthetic-annotator')['prior_machine_exposure']
    assert not env.cal.open_blind(child.dataset_id,s.sample_id,env.rubric.rubric_id,'unexposed-other-person')['prior_machine_exposure']
    with pytest.raises(ValueError,match='DATA_REPAIR_FIELDS_INVALID'):
        env.cal.derive_input(env.dataset.dataset_id,s.sample_id,{'answer':'删除实际错误来涨分'},'禁止修改回答','v2','v2','fixture')
    with pytest.raises(ValueError,match='HOLDOUT_LOCKED'):
        env.cal.derive_input(env.dataset.dataset_id,env.dataset.samples[1].sample_id,{'reference_complete':False},'保留题不得修成新未见题','v2','v2','fixture')


def test_correcting_false_pass_to_fail_can_be_a_successful_prompt_repair(env):
    from test_calibration import ScriptedProvider,judgment
    s=env.dataset.samples[0];annotate(env,s);p=protocol(env);base=run(env,p,'false-pass-baseline')
    planned={**plan(s.sample_id),'expected_verdict':'FAIL'}
    issue=env.cal.create_issue(env.dataset.dataset_id,s.sample_id,base['run_id'],'synthetic-annotator','纠正错误放行','PROMPT','fixture','固定回答不应通过',repair_plan=planned)
    e=env.cal.update_issue(issue.issue_id,'synthetic-annotator','REPRODUCED','确认原判为 PASS 的软件样例')
    e=env.cal.update_issue(issue.issue_id,'synthetic-annotator','CHANGED','固定回答，仅改变提示',previous_event_id=e.event_id,change_summary='逐项证据核对提示')
    p2=protocol(env,'J2',p.protocol_id);ScriptedProvider.output=judgment('FAIL');new=run(env,p2,'false-pass-corrected')
    result=env.cal.update_issue(issue.issue_id,'synthetic-annotator','RETESTED','PASS→FAIL 修正误放行，不是质量退化',previous_event_id=e.event_id,verification_run_id=new['run_id'],outcome='FIXED',verification_report=report())
    assert result.outcome=='FIXED' and result.verification_snapshot['target_verdicts']==['FAIL']


def test_rubric_revision_requires_new_reference_and_keeps_old_scoring_scope(env):
    from copy import deepcopy
    s=env.dataset.samples[0];annotate(env,s);p=protocol(env);base=run(env,p,'rubric-baseline')
    issue=env.cal.create_issue(env.dataset.dataset_id,s.sample_id,base['run_id'],'synthetic-annotator','修订业务标准','RUBRIC','fixture','旧标准不适用业务边界',repair_plan=plan(s.sample_id))
    e=env.cal.update_issue(issue.issue_id,'synthetic-annotator','REPRODUCED','软件样例确认标准冲突')
    e=env.cal.update_issue(issue.issue_id,'synthetic-annotator','CHANGED','新标准单独研究',previous_event_id=e.event_id,change_summary='发布新的条件覆盖阈值与业务说明')
    old=env.rubric
    definition={k:deepcopy(getattr(old,k)) for k in ['name','dimensions','critical_errors','applicable_scope','rules']}
    definition['rules']['minimum_scores']['conditions']=1
    env.rubric=env.cal.create_rubric(definition,old.rubric_id)
    annotate(env,s)
    revised=protocol(env);new=run(env,revised,'rubric-new-reference-missing')
    with pytest.raises(ValueError,match='INDEPENDENT_HUMAN_REFERENCE_REQUIRED'):
        env.cal.update_issue(issue.issue_id,'synthetic-annotator','RETESTED','不能继承旧标准参照',previous_event_id=e.event_id,verification_run_id=new['run_id'],outcome='FIXED',verification_report=report())
    # HUMAN below is a synthetic contract fixture inside pytest's temporary store.
    # It must never be exported as real independent annotation evidence.
    annotate(env,s,actor='human-contract-fixture-only',source='HUMAN')
    new=run(env,revised,'rubric-reannotated-contract')
    result=env.cal.update_issue(issue.issue_id,'synthetic-annotator','RETESTED','新标准具有新参照；不宣称 Agent 改善',previous_event_id=e.event_id,verification_run_id=new['run_id'],outcome='FIXED',verification_report=report())
    assert result.verification_kind=='RUBRIC_STUDY'
    assert result.verification_snapshot['rubric_id']!=old.rubric_id
