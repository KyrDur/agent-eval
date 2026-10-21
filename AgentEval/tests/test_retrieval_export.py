"""CSV contracts on synthetic records; no model calls or human study claims."""
from copy import deepcopy
import csv
import hashlib
import io
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from evaluation.models import CaseResult
from experiments import api
from experiments.canonical import digest
from experiments.retrieval_api import router
from experiments.retrieval_export import export_run, export_comparison, _quality
from experiments.retrieval_models import RetrievalRun, RetrievalComparison
from experiments.retrieval_service import RetrievalService
from experiments.store import JsonStore
from test_anonymous_workspaces import environment, boot


def answer(sid, text='第一行，包含逗号与“引号”。\n第二行 "quoted"', score=1):
    return CaseResult(case_id=sid,execution_status='SUCCESS',judge_status='SUCCESS',
        original_status='PASS' if score else 'FAIL',original_reason='保存的完整理由，不能改写。',
        scores={**{k:score for k in ('relevance','accuracy','completeness','helpfulness')},'overall':score},
        turn_evidence=[{'turn':1,'question':'模拟问题','response':text,'execution_status':'SUCCESS'}])


def make_run(rag, ids=('a','b'), *, mode='BASELINE', results=None, answers=None, status='COMPLETE', extra_cases=(), **kwargs):
    cases=[{'case_id':sid,'query':'问题 '+sid,'expected_answer':'参考，保持完整条件。',
            'must_do':['核对订单'],'source':'demo','partition':'DEBUG','reference_complete':True} for sid in ids]
    controls={'eval_set_snapshot':{'retrieval_eval_set_id':'fixture-set','version':1,'cases':cases+list(extra_cases)},
        'knowledge_snapshot':{'version':1},'index_snapshot':{'index_id':'fixture-index'},
        'evaluation_scope':{'partition':'DEBUG'},'evaluation_protocol_hash':'legacy-v1'}
    if results is None:
        results=[{'case_id':sid,'query':'问题 '+sid,'status':'SUCCESS','partition':'DEBUG','case_latency_ms':12.5,
            'results':[{'document_id':'policy','chunk_id':'chunk','text':'完整政策，含 "引号"。\n下一行。'}],
            'input_package':{'check':{'status':'PASS'},'source':'SYNTHETIC_EXPORT_FIXTURE_ONLY'},'provider_call_traces':[],'metrics':{'relevant_rank':1,'hit_at_1':1,'mrr':1}} for sid in ids]
    value=RetrievalRun(run_type=mode,status=status,provider_session_id='unused',
        provider_configuration_snapshot={'model':'answer-model','role_overrides':{'judge':{'model':'judge-model'}}},
        provider_readiness_snapshot={},controls=controls,retrieval_config={'top_k':1},execution_order=list(ids),
        verify_answers=True,case_results=results,answer_results=answers if answers is not None else [answer(sid) for sid in ids],**kwargs)
    rag.store.put('retrieval_runs',value)
    return value


def comparison(rag, before, after, *, pairs=None, comparable=True, reviews=()):
    if pairs is None:
        pairs=[]
        for sid in dict.fromkeys(before.execution_order+after.execution_order):
            pair={'case_id':sid,'transition':'RETRIEVAL_UNCHANGED','answer_transition':'PASS→PASS','reason':None}
            for side,run in [('baseline',before),('retest',after)]:
                r=next((r for r in run.case_results if r['case_id']==sid),None)
                a=next((a.model_dump(mode='json') for a in run.answer_results if a.case_id==sid),None)
                pair.update({side:r,side+'_answer':a,side+'_trust':_quality(a,r)})
            pairs.append(pair)
    value=RetrievalComparison(baseline_run_id=before.run_id,retest_run_id=after.run_id,
        comparable=comparable,comparability_reasons=[] if comparable else ['RUBRIC_CHANGED'],
        comparison_completeness='FULL',expected_case_count=len(pairs),matched_case_count=len(pairs),
        single_recorded_change=True,warnings=[],case_pairs=pairs,metrics_before={},metrics_after={},paired_metrics={},
        answer_review_snapshot={'records':list(reviews),'hash':digest(list(reviews))})
    rag.store.put('retrieval_comparisons',value)
    return value


@pytest.fixture
def rag(tmp_path):
    # Export uses only the real store and effective_answers; it must not need a provider or index.
    value=object.__new__(RetrievalService)
    value.store=JsonStore(tmp_path/'artifacts')
    return value


def read(file):
    assert file.content.startswith(b'\xef\xbb\xbf')
    rows=list(csv.DictReader(io.StringIO(file.content.decode('utf-8-sig'),newline='')))
    assert all(None not in row for row in rows), 'Quoting must not shift cells to extra columns'
    assert len(rows)==file.row_count
    return rows


def manifest(store):
    return {p.relative_to(store.root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in store.root.rglob('*.json')}


def test_full_text_quoting_multiturn_zero_missing_and_read_only(rag):
    text='原文含逗号, "引号"\n'+('完整回答；'*6000)
    a=answer('a',text,score=0)
    # Missing b and its missing answer remain an expected row, not a zero score.
    run=make_run(rag,answers=[a],results=[{'case_id':'a','status':'SUCCESS','results':[],
        'input_package':{'check':{'status':'PASS'},'source':'SYNTHETIC_EXPORT_FIXTURE_ONLY'},'provider_call_traces':[],'metrics':{'hit_at_1':0},'case_latency_ms':0}])
    before=manifest(rag.store)
    rows=read(export_run(rag,run.run_id))
    assert len(rows)==2 and rows[0]['实际回答']==text
    assert float(rows[0]['准确性分数'])==0 and rows[0]['Hit@1']=='0' and rows[0]['逐题耗时毫秒']=='0'
    assert rows[0]['评分量表']=='0～1' and rows[0]['当前有效判定']=='不通过'
    assert rows[1]['实际回答']==rows[1]['准确性分数']==rows[1]['实际调用次数']==''
    assert rows[1]['当前有效判定']=='未运行' and '记录缺失' in rows[1]['记录异常']
    assert rows[0]['费用']==rows[0]['币种']==''
    assert manifest(rag.store)==before


def test_two_scale_scores_keep_original_dimension_states_and_protocol(rag):
    from test_calibration import judgment
    from experiments.calibration_models import CalibrationResult
    j=judgment('FAIL');j['dimensions']['conditions']['score']='NA'
    evidence=CalibrationResult(sample_id='a',repetition=1,status='SUCCESS',judgment=j)
    a=CaseResult(case_id='a',execution_status='SUCCESS',judge_status='SUCCESS',original_status='FAIL',
        original_reason='构造测试，非研究结果',scoring_protocol={'kind':'EVIDENCE_RUBRIC_V1','scale':'0/1/2; INSUFFICIENT; NA','profile_hash':'new-v1'},
        evidence_evaluation=evidence.model_dump(mode='json'))
    run=make_run(rag,ids=('a',),answers=[a]);row=read(export_run(rag,run.run_id))[0]
    assert row['事实与依据分数']=='0' and row['条件覆盖分数']=='' and row['条件覆盖状态']=='不适用'
    assert row['评分方案版本']=='new-v1' and row['准确性分数']=='' and row['评分量表'].startswith('0/1/2')


def test_current_review_and_frozen_comparison_never_mix(rag):
    a=make_run(rag,ids=('a',));b=make_run(rag,ids=('a',),mode='RETEST')
    comp=comparison(rag,a,b)
    rag.review(b.run_id,'a','FAIL','后补复核：回答漏了条件。')
    single=read(export_run(rag,b.run_id))[0]
    assert single['机器原判']=='通过' and single['人工复核结果']==single['当前有效判定']=='不通过'
    assert single['人工复核版本']=='1' and single['人工复核时间']
    frozen=read(export_comparison(rag,comp.comparison_id))[0]
    assert frozen['修改后·当前有效判定']=='通过' and frozen['修改后·人工复核结果']==''
    assert frozen['回答变化']=='保持通过' and frozen['比较时的复核快照']==digest([])
    assert frozen['检索变化']=='不变'
    assert '后补复核' not in str(frozen)


@pytest.mark.parametrize('scores,ranks,expected_answer,expected_retrieval',[
    ((0,1),(0.5,1),'改善','改善'),((1,0),(1,0.5),'退化','退化'),
    ((1,1),(1,1),'保持通过','不变'),((0,0),(1,1),'仍未通过','不变')])
def test_real_transition_codes_export_the_saved_meaning(rag,scores,ranks,expected_answer,expected_retrieval):
    from experiments.retrieval_metrics import transition, answer_transition
    before=make_run(rag,ids=('a',),answers=[answer('a',score=scores[0])])
    after=make_run(rag,ids=('a',),mode='RETEST',answers=[answer('a',score=scores[1])])
    pair={'case_id':'a'}
    for side,run,rank in zip(('baseline','retest'),(before,after),ranks):
        retrieval=deepcopy(run.case_results[0]);retrieval['metrics'].update(mrr=rank,recall_at_k=1)
        value=run.answer_results[0].model_dump(mode='json')
        pair.update({side:retrieval,side+'_answer':value,side+'_trust':_quality(value,retrieval)})
    pair['transition'],pair['reason']=transition(pair['baseline'],pair['retest'])
    pair['answer_transition']=answer_transition(before.answer_results[0],after.answer_results[0])
    comp=comparison(rag,before,after,pairs=[pair]);row=read(export_comparison(rag,comp.comparison_id))[0]
    assert row['回答变化']==expected_answer and row['检索变化']==expected_retrieval


def test_machine_original_is_preserved_when_the_input_is_unevaluable(rag):
    run=make_run(rag,ids=('a',),results=[{'case_id':'a','status':'SUCCESS','results':[],
        'input_package':{'check':{'status':'EVIDENCE_INSUFFICIENT'},'missing_items':['订单对应记录']}}])
    row=read(export_run(rag,run.run_id))[0]
    assert row['机器原判']=='通过' and row['当前有效判定']=='证据不足'
    assert '订单对应记录' in row['缺失或不适用说明']


def test_pair_union_missing_duplicates_and_changed_scoring_cannot_improve(rag):
    before=make_run(rag,ids=('a','removed'))
    after=make_run(rag,ids=('a','added'),mode='RETEST')
    comp=comparison(rag,before,after)
    rows=read(export_comparison(rag,comp.comparison_id))
    assert {r['题目ID'] for r in rows}=={'a','removed','added'}
    assert all(r['回答变化']=='无法比较' and r['无法比较的原因'] for r in rows if r['题目ID']!='a')
    assert next(r for r in rows if r['题目ID']=='added')['修改前·实际回答']==''
    changed=deepcopy(comp.case_pairs);changed[0]['retest_answer']['scoring_protocol']={'scale':'0/1/2','profile_hash':'other'}
    invalid=comparison(rag,before,after,pairs=changed,comparable=False)
    assert read(export_comparison(rag,invalid.comparison_id))[0]['回答变化']=='无法比较'
    dup=make_run(rag,ids=('a',),results=[before.case_results[0],before.case_results[0]],answers=[answer('a'),answer('a')])
    row=read(export_run(rag,dup.run_id))[0]
    assert row['当前有效判定']=='未检查' and row['实际回答']==row['检索资料原文']==row['准确性分数']==''
    assert '记录重复：2' in row['记录异常']


def test_usage_is_not_allocated_and_failed_calls_with_unknown_tokens_are_retained(rag):
    run=make_run(rag,ids=('a',),provider_call_count=2,results=[{'case_id':'a','status':'SUCCESS','results':[],
        'provider_call_traces':[{'usage':{'input_tokens':10,'output_tokens':5,'total_tokens':15}}, {'status':'FAILED','usage':None}]}])
    row=read(export_run(rag,run.run_id))[0]
    assert row['实际调用次数']=='2' and row['已知总Token']=='15' and row['用量完整性']=='部分未知'
    assert row['费用']==''
    old=make_run(rag,ids=('a',),provider_call_count=7,results=[{'case_id':'a','status':'SUCCESS','results':[]}])
    row=read(export_run(rag,old.run_id))[0]
    assert row['实际调用次数']==row['已知总Token']==''
    assert row['整次运行调用次数（勿按行累加）']=='7' and '不完整' in row['用量完整性']


def test_scope_filters_private_holdout_even_if_an_outside_record_exists(rag):
    hidden={'case_id':'holdout','query':'DO_NOT_EXPORT_SECRET_HOLDOUT','expected_answer':'HIDDEN_REFERENCE','partition':'HOLDOUT'}
    run=make_run(rag,ids=('a','holdout'),extra_cases=())
    data=run.model_dump(mode='json');data['controls']['eval_set_snapshot']['cases'][1]=hidden
    # Pure function fixture, not a rewrite of an existing immutable record.
    data['run_id']='scoped-copy';data['case_results'][1]['query']=hidden['query']
    value=RetrievalRun.model_validate(data);rag.store.put('retrieval_runs',value)
    file=export_run(rag,value.run_id)
    assert [r['题目ID'] for r in read(file)]==['a']
    assert b'DO_NOT_EXPORT' not in file.content and b'HIDDEN_REFERENCE' not in file.content


def test_formula_neutralization_does_not_corrupt_numeric_zero_or_modify_source(rag):
    run=make_run(rag,ids=('a',),answers=[answer('a',' \t=HYPERLINK("https://example.invalid")',score=0)])
    before=manifest(rag.store);row=read(export_run(rag,run.run_id))[0]
    assert row['实际回答'].startswith("' \t=") and float(row['准确性分数'])==0
    assert manifest(rag.store)==before


def test_multiple_turns_stay_in_one_row_and_execution_errors_are_explicit(rag):
    a=answer('a')
    from evaluation.models import TurnEvidence
    a=a.model_copy(update={'turn_evidence':[TurnEvidence(turn=i,question='测试',response=text,execution_status='SUCCESS')
        for i,text in [(1,'第一轮回答'),(2,'第二轮回答')]]})
    failed=CaseResult(case_id='b',execution_status='FAILED',judge_status='NOT_RUN',original_status='INVALID',
        original_reason='没有完成回答',turn_evidence=[TurnEvidence(turn=1,question='测试',execution_status='FAILED',execution_error='TIMEOUT')])
    run=make_run(rag,answers=[a,failed],status='PARTIAL')
    rows=read(export_run(rag,run.run_id))
    assert len(rows)==2 and '第 1 轮\n第一轮回答' in rows[0]['实际回答'] and '第 2 轮\n第二轮回答' in rows[0]['实际回答']
    assert rows[1]['当前有效判定']=='执行失败' and rows[1]['评分执行状态']=='NOT_RUN'
    assert rows[1]['准确性分数']=='' and 'TIMEOUT' in rows[1]['错误原因']


def test_credentials_in_old_prose_are_redacted_without_exporting_configuration(rag):
    run=make_run(rag,ids=('a',),answers=[answer('a','旧错误含 opaque-test-secret')])
    rag.store.forbidden_values=('opaque-test-secret',)
    data=export_run(rag,run.run_id).content.decode('utf-8-sig')
    assert 'opaque-test-secret' not in data and '已隐藏凭据' in data


def test_duplicate_frozen_pairs_and_old_missing_snapshots_are_not_reconstructed(rag):
    before=make_run(rag,ids=('a',));after=make_run(rag,ids=('a',),mode='RETEST')
    comp=comparison(rag,before,after)
    duplicate=comparison(rag,before,after,pairs=comp.case_pairs*2)
    row=read(export_comparison(rag,duplicate.comparison_id))[0]
    assert row['回答变化']==row['检索变化']=='无法比较'
    assert '唯一对应' in row['修改后·记录异常']
    old=comparison(rag,before,after,pairs=[{'case_id':'a','transition':'UNCHANGED'}])
    rag.review(after.run_id,'a','FAIL','后补复核不可带入旧比较')
    row=read(export_comparison(rag,old.comparison_id))[0]
    assert row['修改后·人工复核结果']==row['修改后·实际回答']==''
    assert row['修改后·当前有效判定']=='未知' and '未保存该侧回答快照' in row['修改后·记录异常']


def test_http_download_headers_error_states_and_secret_allowlist(rag,monkeypatch):
    previous=api._service_provider;api.configure(lambda:SimpleNamespace(retrieval=rag))
    app=FastAPI();app.include_router(router)
    try:
        run=make_run(rag,ids=('a',),status='FAILED')
        with TestClient(app) as client:
            response=client.get(f'/experiments/retrieval-runs/{run.run_id}/export?format=csv')
            assert response.status_code==200 and response.headers['content-type'].startswith('text/csv')
            assert 'filename*=UTF-8' in response.headers['content-disposition'] and response.headers['x-csv-row-count']=='1'
            assert response.headers['cache-control']=='private, no-store' and response.headers['x-export-schema']=='EVAL_CSV_V1'
            assert 'provider_session_id' not in response.text and 'base_url' not in response.text
            assert client.get(f'/experiments/retrieval-runs/{run.run_id}/export?format=xlsx').status_code==422
            assert client.get('/experiments/retrieval-runs/missing/export').status_code==404
            running=make_run(rag,ids=('a',),status='RUNNING')
            assert client.get(f'/experiments/retrieval-runs/{running.run_id}/export').json()['detail']=='CSV_EXPORT_RUN_NOT_FINISHED'
            monkeypatch.setattr('experiments.retrieval_export.MAX_BYTES',10)
            oversized=client.get(f'/experiments/retrieval-runs/{run.run_id}/export')
            assert oversized.status_code==413 and oversized.json()['detail']=='CSV_EXPORT_TOO_LARGE'
    finally:
        api._service_provider=previous


def test_export_cannot_read_other_workspaces_or_private_validation_runs(environment):
    app,registry,a,b=environment;ra=boot(a);boot(b)
    owned=registry.get(ra.json()['workspace_ref']).retrieval
    run=make_run(owned,ids=('a',))
    assert a.get(f'/experiments/retrieval-runs/{run.run_id}/export').status_code==200
    assert b.get(f'/experiments/retrieval-runs/{run.run_id}/export').status_code==404
    private=run.model_copy(update={'run_id':'private-holdout'})
    owned.store.put('retrieval_validation_runs',private)
    assert a.get('/experiments/retrieval-runs/private-holdout/export').status_code==404
    comp=comparison(owned,run,run)
    assert b.get(f'/experiments/retrieval-comparisons/{comp.comparison_id}/export').status_code==404
