"""Business invariants using isolated software fixtures, no quality research claims."""
from types import SimpleNamespace as NS
import pytest
from experiments.retrieval_models import RetrievalCase
from experiments.trusted_results import freeze_input,source_identity,result_state,sample_flow,comparison_trust


def answer(identifier,state='PASS'):
    return NS(case_id=identifier,execution_status='SUCCESS',judge_status='SUCCESS',hard_rule_violations=[],
        evaluation_error=None,final_status=state,evidence_evaluation=None,case=None,human_final_status=None,scoring_protocol=None)

def run(states):
    ids=list(states)
    return NS(execution_order=ids,case_results=[{'case_id':i,'status':'SUCCESS','input_package':{'check':{'status':'PASS'}}} for i in ids],
        answer_results=[answer(i,s) for i,s in states.items()],verify_answers=True,provider_call_count=20,
        controls={'eval_set_snapshot':{'cases':[{'case_id':i} for i in ids]},'eval_set_hash':'v1'})


def test_four_failures_becoming_unevaluable_never_prove_overall_gain():
    baseline=run({str(i):'PASS' if i<6 else 'FAIL' for i in range(10)})
    retest=run({str(i):'PASS' for i in range(10)})
    for row in retest.case_results[6:]:row['input_package']['check']['status']='EVIDENCE_INSUFFICIENT'
    result=comparison_trust(baseline,retest,baseline.answer_results,retest.answer_results,True)
    assert result['baseline']['machine_pass_rate']['value']==.6
    assert result['retest']['machine_pass_rate']['value']==1
    assert result['retest']['coverage']['value']==.6
    assert result['common_subset']['count']==6 and not result['common_subset']['improved_ids']
    assert result['coverage_declined'] and len(result['lost_valid_decision_ids'])==4
    assert not result['adoption_allowed'] and not result['overall_improvement_allowed']
    assert len(result['full_scope']['state_transitions'])==10


def test_equal_result_counts_with_wrong_ids_and_duplicates_cannot_balance():
    r=run({'a':'PASS','b':'FAIL'})
    r.answer_results=[answer('a'),answer('a')]
    f=sample_flow(r)
    assert f['answer_reconciliation']['duplicate_ids']==['a']
    assert f['answer_reconciliation']['missing_ids']==['b'] and f['coverage']['numerator']==0
    r.answer_results=[answer('a'),answer('wrong')]
    f=sample_flow(r)
    assert f['answer_reconciliation']['unexpected_ids']==['wrong'] and not f['complete']
    assert f['cost']['known_total_tokens'] is None and f['cost']['currency_cost'] is None
    assert f['cost']['unknown_usage_requests']==20


@pytest.mark.parametrize('metadata,context,reason',[
    ({'object_ids':{'order_id':'A'}},{'object_ids':{'order_id':'B'}},'OBJECT_MISMATCH:order_id'),
    ({'turn_id':'1'},{'turn_id':'2'},'TURN_ID_MISMATCH'),
    ({'policy_version':'v1','effective_until':'2025-01-01T00:00:00Z'},{'question_time':'2026-01-01T00:00:00Z'},'POLICY_NOT_EFFECTIVE'),
    ({'effective_from':'2025-01-01'},{'question_time':'2026-01-01'},'POLICY_TIME_PREMISES_MISSING')])
def test_evidence_that_exists_but_does_not_apply_is_preserved_and_not_passed(metadata,context,reason):
    c=RetrievalCase(case_id='a',query='现在适用吗？',evidence_context=context)
    package=freeze_input(c,{'results':[]},'可以。',[{'document_id':'policy','text':'原文保留。','metadata':metadata}])
    assert package['check']['status']=='EVIDENCE_INSUFFICIENT'
    assert package['evidence'][0]['text']=='原文保留。'
    assert reason in package['evidence'][0]['applicability_reasons']
    assert result_state(answer('a'),package)=='EVIDENCE_INSUFFICIENT'


def test_missing_card_and_oversize_inputs_are_explicit_not_silently_cleaned():
    c=RetrievalCase(case_id='a',query='检查',evidence_context={'required_evidence_ids':['card-missing'],'max_input_characters':2})
    package=freeze_input(c,{'results':[]},'错误输出仍保留。',[])
    assert 'EVIDENCE:card-missing' in package['missing_items'] and package['truncated_items']
    assert package['current_answer']=='错误输出仍保留。'
    assert package['question_time'] is None and package['source_type']=='UNKNOWN'
    assert not c.model_dump().get('reference_complete')


def test_sources_reference_completeness_and_legacy_serialization_are_independent():
    old={'case_id':'a','query':'知识有没有？'}
    c=RetrievalCase(**old)
    assert source_identity(c)=='UNKNOWN'
    assert 'evidence_context' not in c.model_dump() and 'reference_complete' not in c.model_dump()
    p=freeze_input(c,{'results':[]},'不知道。',[{'document_id':'p','text':'一份文档'}])
    assert p['reference_complete'] is None and p['check']['reference_completeness_status']=='UNKNOWN'
    declared=c.model_copy(update={'source':'user_created','evidence_context':{'source_type':'CONSTRUCTED'}})
    assert source_identity(declared)=='CONSTRUCTED'


def test_execution_failure_cannot_be_disguised_as_abstention_or_not_applicable():
    a=answer('a');a.judge_status='FAILED'
    p={'check':{'status':'EVIDENCE_INSUFFICIENT'}}
    assert result_state(a,p)=='EXECUTION_FAILED'
    a.judge_status='SUCCESS';a.final_status='FAIL'
    p={'check':{'status':'PASS'},'scenario_rules':{'evaluation_applicability':{'applicable':False,'rule_id':'scope-v1','reason':'不属于该业务','confirmed_by':'fixture-maintainer'}}}
    assert result_state(a,p)=='FAIL'
    a.final_status='PASS';assert result_state(a,p)=='NOT_APPLICABLE'
