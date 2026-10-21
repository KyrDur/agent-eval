"""Read-only, versioned CSV views of acquired RAG runs and frozen comparisons."""
from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import json
import math
import re
from zoneinfo import ZoneInfo

from evaluation.models import CaseResult
from .trusted_results import answer_trust

SCHEMA = 'EVAL_CSV_V1'
MAX_BYTES = 32 * 1024 * 1024
TERMINAL = {'COMPLETE', 'PARTIAL', 'FAILED'}
STATES = {'PASS':'通过', 'FAIL':'不通过', 'INVALID':'无效', 'PENDING':'待判断',
          'EVIDENCE_INSUFFICIENT':'证据不足', 'NOT_APPLICABLE':'本题不适用',
          'NOT_CHECKED':'未检查', 'EXECUTION_FAILED':'执行失败', 'NOT_RUN':'未运行'}
TRANSITIONS = {'IMPROVED':'改善', 'REGRESSED':'退化', 'UNCHANGED':'不变',
               'STILL_PASS':'保持通过', 'STILL_FAIL':'仍未通过', 'NOT_COMPARABLE':'无法比较',
               'PASS→PASS':'保持通过', 'FAIL→FAIL':'仍未通过', 'FAIL→PASS':'改善', 'PASS→FAIL':'退化',
               'RETRIEVAL_IMPROVED':'改善', 'RETRIEVAL_REGRESSED':'退化', 'RETRIEVAL_UNCHANGED':'不变'}
DIMENSIONS = {'faithfulness':'事实与依据', 'conditions':'条件覆盖', 'relevance':'相关性',
              'actionability':'下一步可用性', 'accuracy':'准确性', 'completeness':'完整性',
              'helpfulness':'帮助度', 'overall':'综合分'}
METRICS = {'relevant_rank':'正确资料排名', 'hit_at_1':'Hit@1', 'hit_at_3':'Hit@3',
           'mrr':'MRR', 'recall_at_k':'Recall@K', 'precision_at_k':'Precision@K', 'ndcg_at_k':'NDCG@K'}
BASE_COLUMNS = ['题目ID','问题','参考答案','预期行为','必须满足的条件','禁止行为','实际回答',
    '机器原判','机器原始状态','机器理由','人工复核结果','人工复核理由','当前有效判定','判定来源',
    '客户问题状态','客服当前行为','评分量表',
    *[column for name in DIMENSIONS.values() for column in (name+'分数',name+'状态')],
    '评分明细与引用','检索资料原文','相关文档ID','相关片段ID',*METRICS.values(),
    '执行状态','回答执行状态','评分执行状态','缺失或不适用说明','错误原因','记录异常',
    '实际调用次数','已知输入Token','已知输出Token','已知总Token','用量完整性','逐题耗时毫秒',
    '费用','币种','题目来源','用途','问题族','参考资料完整性','人工复核版本','人工复核时间']
META_COLUMNS = ['运行ID','运行类型','运行状态','题集ID','题集版本','知识版本','索引ID','回答模型（配置）','评分模型（配置）',
    '评分方案ID','评分方案版本','评分规则版本','整次运行调用次数（勿按行累加）','导出时间','导出格式版本','整次统计发布状态','整次通过分子（勿累加）','整次通过分母（勿累加）','整次覆盖分子（勿累加）','整次覆盖分母（勿累加）','证据约束版本']
COMPARE_COLUMNS = ['题目ID','问题','参考答案','预期行为','必须满足的条件','题目来源',
    '回答变化','检索变化','无法比较的原因','比较范围说明','修改项','比较ID','比较时的复核快照',
    *[prefix+column for prefix in ('修改前·','修改后·') for column in BASE_COLUMNS[1:]+META_COLUMNS]]
REDACT = re.compile(r'(?i)bearer\s+[a-z0-9._-]{8,}|(?:sk-ant-|sk-|lsv2_)[a-z0-9_-]{8,}')


@dataclass(frozen=True)
class CsvFile:
    content: bytes
    filename: str
    row_count: int


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')) if value is not None else ''


def _group(values, key='case_id'):
    result = defaultdict(list)
    for value in values:
        result[value.get(key)].append(value)
    return result


def _one(values):
    return values[0] if len(values) == 1 else None


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _model(configuration, role):
    if role == 'judge':
        configuration = configuration.get('judge_provider_configuration') or configuration
    return (configuration.get('role_overrides', {}).get(role) or {}).get('model') or configuration.get('model', '')


def _quality(answer, retrieval, frozen=None):
    if frozen is not None:
        return frozen
    try:
        model = CaseResult.model_validate(answer) if answer else None
        return answer_trust(model, (retrieval or {}).get('input_package'), retrieval)
    except (ValueError, TypeError):
        return {'evaluation_state':'NOT_CHECKED', 'task_outcome':'UNKNOWN', 'judged_by':'UNKNOWN'}


def _responses(answer):
    turns = (answer or {}).get('turn_evidence', [])
    if len(turns) == 1:
        return turns[0].get('response', '')
    return '\n\n'.join(f"第 {turn.get('turn','未知')} 轮\n{turn.get('response','')}" for turn in turns)


def _usage(retrieval):
    if not retrieval or 'provider_call_traces' not in retrieval:
        return {'用量完整性':'未知'}
    traces = retrieval['provider_call_traces']
    known = [t['usage'] for t in traces if isinstance(t.get('usage'), dict)
             and all(_number(t['usage'].get(k)) and t['usage'][k] >= 0
                     for k in ('input_tokens','output_tokens','total_tokens'))]
    result = {'实际调用次数':len(traces), '用量完整性':'完整' if len(known)==len(traces) else '部分未知' if known else '未知'}
    if known or not traces:
        result.update({label:sum(u[key] for u in known) for label,key in
            [('已知输入Token','input_tokens'),('已知输出Token','output_tokens'),('已知总Token','total_tokens')]})
    return result


def _index(run):
    return {'cases':_group(run.get('controls', {}).get('eval_set_snapshot', {}).get('cases', [])),
            'retrieval':_group(run.get('case_results', [])), 'answers':_group(run.get('answer_results', []))}


def _in_scope(run):
    # Never enumerate the entire frozen eval set: it may include private HOLDOUT.
    cases = _group(run.get('controls', {}).get('eval_set_snapshot', {}).get('cases', []))
    partition = run.get('controls', {}).get('evaluation_scope', {}).get('partition')
    return list(dict.fromkeys(sid for sid in run.get('execution_order', [])
        if partition != 'DEBUG' or not any(c.get('partition') == 'HOLDOUT' for c in cases[sid])))


def _anomalies(run, sid, index):
    errors = []
    for label,key in [('题目','cases'),('检索','retrieval'),('回答','answers')]:
        count = len(index[key][sid])
        if count > 1:
            errors.append(f'{label}记录重复：{count} 条，未选取其中一条作为有效结果')
        elif not count and (key!='answers' or run.get('verify_answers')):
            errors.append(label+'记录缺失')
    if run.get('execution_order', []).count(sid) > 1:
        errors.append('应评题目ID重复')
    scope = set(_in_scope(run))
    outside = sum(len(values) for key in ('retrieval','answers') for key_id,values in index[key].items() if key_id not in scope)
    if outside:
        errors.append(f'另有 {outside} 条范围外结果，未导出其内容')
    return errors


def _row(run, sid, index, answers, reviews, exported_at, retrieval=None, frozen=None, note=''):
    case = _one(index['cases'][sid]) or {}
    raw = _one(index['answers'][sid])
    answer = _one(answers[sid]) if len(index['answers'][sid]) <= 1 else None
    r = retrieval or {}
    trust = _quality(answer, retrieval, frozen)
    original_judgment = ((raw or {}).get('evidence_evaluation') or {}).get('judgment') or {}
    original_state = (raw or {}).get('original_status')
    if original_state=='INVALID' and original_judgment.get('verdict')=='PENDING' and raw.get('judge_status')=='SUCCESS':
        original_state = 'EVIDENCE_INSUFFICIENT'
    package = r.get('input_package') or {}
    evaluation = (answer or {}).get('evidence_evaluation') or {}
    judgment = evaluation.get('judgment') or {}
    protocol = (answer or raw or {}).get('scoring_protocol') or {}
    profile = run.get('controls', {}).get('scoring_profile') or {}
    if not protocol and profile:
        protocol = {'profile_id':profile.get('profile_id'), 'profile_hash':profile.get('content_hash'),
                    'rubric_hash':(profile.get('rubric') or {}).get('content_hash'), 'scale':'0/1/2; INSUFFICIENT; NA'}
    latest = max((v for v in reviews if v.get('case_id')==sid and v.get('run_id')==run['run_id']),
                 key=lambda v:v.get('revision',0), default={})
    anomalies = _anomalies(run, sid, index)
    if note:
        anomalies.append(note)
    if len(index['retrieval'][sid]) > 1 or len(index['answers'][sid]) > 1:
        trust = {'evaluation_state':'NOT_CHECKED','task_outcome':'UNKNOWN','judged_by':'UNKNOWN'}
        answer = None
        judgment = {}
    state = trust.get('evaluation_state', 'NOT_RUN') if run.get('verify_answers') else 'NOT_CHECKED'
    source = case.get('evidence_context', {}).get('source_type') or {'demo':'CONSTRUCTED','ai_generated':'AI_GENERATED'}.get(case.get('source'),'UNKNOWN')
    errors = [v for v in (r.get('error'), (answer or {}).get('evaluation_error'), (answer or {}).get('judge_error'), evaluation.get('error')) if v]
    errors.extend(turn['execution_error'] for turn in (answer or {}).get('turn_evidence', []) if turn.get('execution_error'))
    checks = package.get('check') or {}
    row = {'题目ID':sid, '问题':case.get('query') or r.get('query',''), '参考答案':case.get('expected_answer'),
        '预期行为':case.get('scenario_rules', {}).get('expected_behavior'),
        '必须满足的条件':'\n'.join(case.get('must_do', [])), '禁止行为':'\n'.join(case.get('must_not_do', [])),
        '实际回答':_responses(answer), '机器原判':STATES.get(original_state,'未记录'),
        '机器原始状态':(raw or {}).get('original_status'), '机器理由':(raw or {}).get('original_reason'),
        '人工复核结果':STATES.get((answer or {}).get('human_evaluation_state') or (answer or {}).get('human_final_status'),''), '人工复核理由':(answer or {}).get('human_reason'),
        '当前有效判定':STATES.get(state,state), '判定来源':{'MACHINE':'评分模型','HUMAN_REVIEW':'人工复核','EXECUTABLE_RULE':'规则检查'}.get(trust.get('judged_by'),'未知'),
        '客户问题状态':{'COMPLETED':'已解决','UNRESOLVED':'未解决','WAITING_CLARIFICATION':'待澄清'}.get(trust.get('task_outcome'),'未知'),
        '客服当前行为':trust.get('current_turn_behavior'),
        '评分量表':protocol.get('scale') or ('0～1' if (answer or {}).get('scores') else ''),
        '评分明细与引用':_json(judgment.get('dimensions') or (answer or {}).get('scores') or None),
        '检索资料原文':'\n\n'.join(f"{v.get('document_id','')} / {v.get('chunk_id','')}\n{v.get('text','')}" for v in r.get('results', [])),
        '相关文档ID':'\n'.join(case.get('relevant_document_ids', [])), '相关片段ID':'\n'.join(case.get('relevant_chunk_ids', [])),
        '执行状态':r.get('status','NOT_RUN'), '回答执行状态':(answer or {}).get('execution_status','NOT_RUN'),
        '评分执行状态':(answer or {}).get('judge_status','NOT_RUN'),
        '缺失或不适用说明':_json({'missing':package.get('missing_items', []),'issues':checks.get('issues', []),
            'truncated':package.get('truncated_items', []),'insufficient':judgment.get('insufficient_items', [])}),
        '错误原因':'\n'.join(v if isinstance(v,str) else _json(v) for v in errors), '记录异常':'\n'.join(anomalies),
        '逐题耗时毫秒':r.get('case_latency_ms'),
        '题目来源':{'ACTUAL':'实际交互','CONSTRUCTED':'模拟题','AI_GENERATED':'AI生成题'}.get(source,'未知'),
        '用途':{'DEBUG':'调试','HOLDOUT':'保留'}.get(case.get('partition') or r.get('partition'),'未知'),
        '问题族':case.get('group_id') or sid,
        '证据约束版本':run.get('controls',{}).get('trust_contract_version','历史版本待重核'),
        '参考资料完整性':{True:'已声明完整',False:'已声明不完整'}.get(case.get('reference_complete'),'未确认'),
        '人工复核版本':latest.get('revision'), '人工复核时间':(answer or {}).get('reviewed_at'),
        '运行ID':run['run_id'], '运行类型':{'BASELINE':'初测','RETEST':'复测'}.get(run.get('run_type')),
        '运行状态':run.get('status'), '题集ID':run.get('controls', {}).get('eval_set_snapshot', {}).get('retrieval_eval_set_id'),
        '题集版本':run.get('controls', {}).get('eval_set_snapshot', {}).get('version'),
        '知识版本':run.get('controls', {}).get('knowledge_snapshot', {}).get('version'),
        '索引ID':run.get('controls', {}).get('index_snapshot', {}).get('index_id'),
        '回答模型（配置）':_model(run.get('provider_configuration_snapshot', {}),'general'),
        '评分模型（配置）':_model(run.get('provider_configuration_snapshot', {}),'judge'),
        '评分方案ID':protocol.get('profile_id'),
        '评分方案版本':protocol.get('profile_hash') or run.get('controls', {}).get('evaluation_protocol_hash'),
        '评分规则版本':protocol.get('rubric_hash'), '导出时间':exported_at, '导出格式版本':SCHEMA,
        '整次运行调用次数（勿按行累加）':run.get('provider_call_count'), **_usage(retrieval)}
    recorded_calls = sum(len(v.get('provider_call_traces', [])) for v in run.get('case_results', []))
    if recorded_calls != run.get('provider_call_count'):
        row['实际调用次数'] = None
        row['用量完整性'] = '调用记录不完整，已知Token仅供参考'
    row.update({label:r.get('metrics', {}).get(key) for key,label in METRICS.items()})
    dimensions = judgment.get('dimensions') or {}
    for key,label in DIMENSIONS.items():
        score = dimensions.get(key, {}).get('score') if key in dimensions else (answer or {}).get('scores', {}).get(key)
        row[label+'分数'] = score if _number(score) else None
        row[label+'状态'] = '已评分' if _number(score) else {'NA':'不适用','INSUFFICIENT':'证据不足'}.get(score,'未评分')
    return row


def _encode(columns, rows, kind, identifier, instant, secrets):
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\r\n')
    def cell(value):
        if value is None or type(value) is float and not math.isfinite(value):
            return ''
        if type(value) in (int,float):
            return value
        value = str(value)
        for secret in secrets:
            if secret:
                value = value.replace(secret,'[已隐藏凭据]')
        value = REDACT.sub('[已隐藏凭据]',value)
        # Excel treats leading whitespace followed by these characters as a formula.
        return "'"+value if value.lstrip('\ufeff'+''.join(chr(i) for i in range(33))).startswith(('=','+','-','@')) else value
    writer.writerow(columns)
    for row in rows:
        writer.writerow([cell(row.get(column)) for column in columns])
        if output.tell() > MAX_BYTES:
            raise ValueError('CSV_EXPORT_TOO_LARGE')
    content = output.getvalue().encode('utf-8-sig')
    if len(content) > MAX_BYTES:
        raise ValueError('CSV_EXPORT_TOO_LARGE')
    day = instant.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d')
    safe_id = re.sub(r'[^a-zA-Z0-9_-]','',identifier)[:12]
    return CsvFile(content,f'{kind}_{day}_{safe_id}.csv',len(rows))


def summary_columns(flow):
    rate=flow.get('machine_pass_rate',{});coverage=flow.get('coverage',{})
    return {'整次统计发布状态':flow.get('publication_status','历史快照待重核'),
        '整次通过分子（勿累加）':rate.get('numerator'),'整次通过分母（勿累加）':rate.get('denominator'),
        '整次覆盖分子（勿累加）':coverage.get('numerator'),'整次覆盖分母（勿累加）':coverage.get('denominator')}


def export_run(rag, identifier):
    with rag.store.transaction():
        run = rag.store.get('retrieval_runs',identifier)
        if run.status not in TERMINAL:
            raise ValueError('CSV_EXPORT_RUN_NOT_FINISHED')
        saved = run.model_dump(mode='json')
        answers = [a.model_dump(mode='json') for a in rag.effective_answers(run)]
        reviews = [r.model_dump(mode='json') for r in rag.store.list('retrieval_reviews') if r.run_id==identifier]
        secrets = tuple(rag.store.forbidden_values)
    instant = datetime.now(timezone.utc)
    index = _index(saved)
    grouped = _group(answers)
    rows = [_row(saved,sid,index,grouped,reviews,instant.isoformat(),retrieval=_one(index['retrieval'][sid])) for sid in _in_scope(saved)]
    from .trusted_results import sample_flow
    flow=sample_flow(run,[CaseResult.model_validate(a) for a in answers])
    for row in rows:row.update(summary_columns(flow))
    return _encode(BASE_COLUMNS+META_COLUMNS,rows,'评测明细',identifier,instant,secrets)

def export_score_report(rag, identifier):
    """Only the immutable adoption manifest supplies scores and denominators."""
    report=rag.store.get('score_reports',identifier)
    job=rag.store.get('score_jobs',report.job_id)
    run=rag.store.get('retrieval_runs',report.source_run_id).model_dump(mode='json')
    instant=datetime.now(timezone.utc);index=_index(run);rows=[]
    extra=['评分报告ID','评分修订','新评分协议','新评分理由','采用尝试ID','最近尝试ID','失败类型','恢复状态','评分字段问题','评分累计实际请求（勿累加）',
           '累计请求预留（勿累加）','累计Token预留（勿累加）','累计已知Token（勿累加）','累计未知用量请求（勿累加）']
    for adopted in report.adoption_manifest:
        sid=adopted['case_id'];result=adopted['result'];judgment=result.get('judgment') or {}
        # Preserve old observation columns; replace every current scoring column together.
        row=_row(run,sid,index,index['answers'],[],instant.isoformat(),retrieval=_one(index['retrieval'][sid]))
        row.update({'当前有效判定':STATES.get(adopted['evaluation_state']), '判定来源':'新协议固定答案重评',
            '新评分理由':judgment.get('reason'),'评分明细与引用':_json(judgment.get('dimensions')),
            '评分执行状态':result.get('status','NOT_RUN'),'错误原因':result.get('error'),
            '评分方案版本':report.protocol_hash,'评分模型（配置）':_model(job.provider_configuration,'judge'),
            '评分量表':'0/1/2; NA; INSUFFICIENT','人工复核结果':'','人工复核理由':'',
            '客户问题状态':judgment.get('task_resolved','UNKNOWN'),'客服当前行为':'UNKNOWN',
            '评分报告ID':report.report_id,'评分修订':report.score_revision,'新评分协议':report.protocol_hash,
            '采用尝试ID':adopted['adopted_attempt_id'],'最近尝试ID':adopted['latest_attempt_id'],
            '失败类型':result.get('error'),'恢复状态':report.summary['recovery_status'],'评分字段问题':_json(result.get('validation_issues',[])),
            '累计请求预留（勿累加）':report.summary['request_reservations'],'累计Token预留（勿累加）':report.summary['token_reservations'],
            '评分累计实际请求（勿累加）':report.summary['actual_requests'],
            '累计已知Token（勿累加）':report.summary['known_total_tokens'],'累计未知用量请求（勿累加）':report.summary['unknown_usage_requests'],
            '整次统计发布状态':'仅限本协议所选封存答案','整次通过分子（勿累加）':report.summary['pass_rate']['numerator'],
            '整次通过分母（勿累加）':report.summary['pass_rate']['denominator'],
            '整次覆盖分子（勿累加）':report.summary['coverage']['numerator'],'整次覆盖分母（勿累加）':len(report.case_ids)})
        for key,label in DIMENSIONS.items():
            score=judgment.get('dimensions',{}).get(key,{}).get('score')
            row[label+'分数']=score if _number(score) else None
            row[label+'状态']='已评分' if _number(score) else {'NA':'不适用','INSUFFICIENT':'证据不足'}.get(score,'未评分')
        rows.append(row)
    return _encode(BASE_COLUMNS+META_COLUMNS+extra,rows,'固定答案重评',identifier,instant,rag.store.forbidden_values)


def export_comparison(rag, identifier):
    with rag.store.transaction():
        comparison = rag.store.get('retrieval_comparisons',identifier).model_dump(mode='json')
        runs = [rag.store.get('retrieval_runs',comparison[key]).model_dump(mode='json') for key in ('baseline_run_id','retest_run_id')]
        if any(run['status'] not in TERMINAL for run in runs):
            raise ValueError('CSV_EXPORT_RUN_NOT_FINISHED')
        secrets = tuple(rag.store.forbidden_values)
    instant = datetime.now(timezone.utc)
    indices = [_index(run) for run in runs]
    scopes = [set(_in_scope(run)) for run in runs]
    ids = list(dict.fromkeys([*_in_scope(runs[0]), *_in_scope(runs[1])]))
    pairs = _group(comparison.get('case_pairs', []))
    reviews = comparison.get('answer_review_snapshot', {}).get('records', [])
    rows = []
    for sid in ids:
        pair = _one(pairs[sid]) or {}
        sides = []
        for i,side in enumerate(('baseline','retest')):
            if sid not in scopes[i]:
                sides.append({column:None for column in BASE_COLUMNS+META_COLUMNS})
                continue
            frozen = pair.get(side+'_trust')
            answer = pair.get(side+'_answer')
            note = '' if pair else (f'比较记录重复：{len(pairs[sid])} 条，未保存唯一对应的逐题快照'
                                    if len(pairs[sid])>1 else '比较未保存唯一对应的逐题快照')
            missing_snapshot = bool(runs[i].get('verify_answers') and not answer and indices[i]['answers'][sid])
            if missing_snapshot:
                note = (note+'；' if note else '')+'比较未保存该侧回答快照，当前判定未知'
            output = _row(runs[i],sid,indices[i],_group([answer] if answer else []),reviews,
                instant.isoformat(),retrieval=pair.get(side),frozen=frozen,note=note)
            if missing_snapshot:
                output.update({'当前有效判定':'未知','回答执行状态':'UNKNOWN','评分执行状态':'UNKNOWN'})
            output.update(summary_columns(comparison.get('trust_summary',{}).get(side,{})))
            sides.append(output)
        left,right = sides
        reasons = list(comparison.get('comparability_reasons', []))
        if pair.get('reason'):
            reasons.append(pair['reason'])
        if not pair or sid not in scopes[0] or sid not in scopes[1]:
            reasons.append('该题缺少一侧结果或比较快照')
        anomalous = any(side.get('记录异常') for side in sides)
        answer_change = pair.get('answer_transition')
        retrieval_change = pair.get('transition')
        if anomalous or not comparison.get('comparable') or not pair or sid not in scopes[0]&scopes[1]:
            answer_change = retrieval_change = 'NOT_COMPARABLE'
        if anomalous:
            reasons.append('逐题记录不完整或ID异常，不能按有效配对解释')
        for side in sides:
            if side.get('当前有效判定') not in {'通过','不通过'} and answer_change not in {None,'NOT_COMPARABLE'}:
                answer_change = 'NOT_COMPARABLE'
                reasons.append('缺少有效回答判定')
        if (left.get('评分量表') and right.get('评分量表') and left['评分量表']!=right['评分量表']
                or left.get('评分方案版本') and right.get('评分方案版本') and left['评分方案版本']!=right['评分方案版本']):
            answer_change = 'NOT_COMPARABLE'
            reasons.append('两侧评分量表或方案版本不同')
        if answer_change=='NOT_COMPARABLE' and not reasons:
            reasons.append('回答未检查、证据不足或评分条件不同，沿用已保存的不可比较判定')
        row = {'题目ID':sid, **{key:left.get(key) or right.get(key) for key in ('问题','参考答案','预期行为','必须满足的条件','题目来源')},
            '回答变化':TRANSITIONS.get(answer_change,'未记录' if runs[0].get('verify_answers') or runs[1].get('verify_answers') else '未检查'),
            '检索变化':TRANSITIONS.get(retrieval_change,'未记录'),
            '无法比较的原因':'\n'.join(dict.fromkeys(reasons)),
            '比较范围说明':'全部应评题目；不受页面筛选影响；不自动推断整体提升',
            '修改项':_json(runs[1].get('experiment_identity', {}).get('declared_diff') or None),
            '比较ID':identifier, '比较时的复核快照':comparison.get('answer_review_snapshot', {}).get('hash'),
            **{prefix+key:value for prefix,side in zip(('修改前·','修改后·'),sides) for key,value in side.items()}}
        rows.append(row)
    return _encode(COMPARE_COLUMNS,rows,'评测对比',identifier,instant,secrets)
