"""Scenario evidence contracts shared by live RAG and imported-answer scoring."""
from copy import deepcopy

TEMPLATES = {
    'POLICY_RAG': {'label':'政策知识问答', 'requires_policy':True, 'expected_behavior':'ANSWER'},
    'MISSING_KNOWLEDGE': {'label':'知识缺失与诚实兜底', 'requires_policy':False, 'expected_behavior':'HANDOFF'},
    'CLARIFICATION': {'label':'信息不足时澄清', 'requires_policy':False, 'expected_behavior':'CLARIFY'},
}

def contract(rules=None):
    rules=rules or {}
    key=rules.get('template_id','POLICY_RAG')
    template=TEMPLATES.get(key,TEMPLATES['POLICY_RAG'])
    behavior=rules.get('expected_behavior')
    return {'template_id':key, **deepcopy(template),
        'requires_policy':template['requires_policy'] and behavior not in {'CLARIFY','HANDOFF','REFUSE'},
        'critical_dimensions':['faithfulness','conditions']}

def checks(rules, reference_complete, reference_count, retrieved_count=0):
    policy=contract(rules)
    missing=policy['requires_policy'] and (reference_complete is not True or not reference_count)
    rows=[]
    for key in ('faithfulness','conditions','relevance','actionability'):
        unavailable=missing if key=='conditions' else policy['requires_policy'] and not (reference_count or retrieved_count) if key=='faithfulness' else False
        scope='REFERENCE' if key=='conditions' and policy['requires_policy'] else 'RETRIEVED_OR_REFERENCE' if key=='faithfulness' and policy['requires_policy'] else 'ANSWER'
        rows.append({'name':key,'status':'EVIDENCE_INSUFFICIENT' if unavailable else 'PASS','required_scope':scope,
            'reason':'REFERENCE_COMPLETENESS_UNCONFIRMED' if unavailable else None})
    return rows

def constrain_judgment(judgment,sample,rubric):
    """Missing material can never be manufactured by high model scores."""
    from evaluation.calibration import final_verdict
    items=checks(sample.provenance.get('scenario_rules',{}),sample.reference_complete,len(sample.reference_policy),len(sample.retrieved_evidence))
    dimensions=dict(judgment.dimensions); missing=list(judgment.insufficient_items)
    for item in items:
        dimension=dimensions[item['name']]
        if item['status']=='EVIDENCE_INSUFFICIENT':
            dimensions[item['name']]=dimension.model_copy(update={'score':'INSUFFICIENT',
                'reason':'缺少核验本题政策所需的完整参考。'+dimension.reason})
            missing.append(item['name']+':'+item['reason'])
        elif item['required_scope'] in {'REFERENCE','RETRIEVED_OR_REFERENCE'} and type(dimension.score) is int:
            if not any(c.scope=='REFERENCE' or (item['required_scope']=='RETRIEVED_OR_REFERENCE' and c.scope=='RETRIEVED') for c in dimension.citations):
                dimensions[item['name']]=dimension.model_copy(update={'score':'INSUFFICIENT','reason':'缺少本项政策原文引用。'})
                missing.append(item['name']+':REFERENCE_CITATION_REQUIRED')
    # A model's critical-error label alone is not proof of a policy conflict.
    errors=judgment.critical_errors
    if any(i['status']=='EVIDENCE_INSUFFICIENT' for i in items):
        errors=[]
    value=judgment.model_copy(update={'dimensions':dimensions,'insufficient_items':sorted(set(missing)), 'critical_errors':errors})
    if contract(sample.provenance.get('scenario_rules',{}))['template_id'] in {'MISSING_KNOWLEDGE','CLARIFICATION'}:
        value=value.model_copy(update={'task_resolved':'NO','task_failure_reasons':list(value.task_failure_reasons)+['诚实兜底或澄清不表示原业务任务已完成。']})
    return value.model_copy(update={'verdict':final_verdict(value,rubric)})


def selected_history(case):
    return deepcopy(case.context if case.evidence_context.get('history_mode')=='FULL' else case.context[-4:])
