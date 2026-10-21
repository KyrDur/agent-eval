"""Frozen evidence scoring profiles. Adoption requires the existing human validation."""
from copy import deepcopy
from types import SimpleNamespace
from evaluation.calibration import RUBRIC_TEMPLATE, score_answer
from evaluation.calibration_metrics import adoption_restrictions
from .canonical import digest
from .calibration_models import RubricVersion, CalibrationSample
from .evidence_judge import ALIAS_PROMPT, score_alias_answer
from .trusted_results import freeze_input, source_identity

INITIAL_ID = 'initial-evidence-v1'

def validation_scope(conclusion):
    report=conclusion.report_snapshot;dataset=report.get('dataset',{});samples=dataset.get('samples',[])
    refs=report.get('comparison',{}).get('reference_snapshot',{})
    candidate=report.get('runs',[{},{}])[-1].get('protocol_snapshot',{})
    return {'dataset_id':dataset.get('dataset_id'),'sample_count':len(samples),
        'question_family_count':len({s['group_id'] for s in samples}),
        'calibration_count':sum(s['partition']=='CALIBRATION' for s in samples),
        'holdout_count':sum(s['partition']=='HOLDOUT' for s in samples),
        'valid_human_reference_count':sum((r.get('judgment') or {}).get('verdict') in {'PASS','FAIL'} for r in refs.values()),
        'research_status':conclusion.research_status,'changed_fields':candidate.get('declared_changes',[]),
        'adoption_reason':conclusion.reason,'decision_source':'USER_CONFIRMED_RESEARCH_DECISION',
        'limitation':'只支持该样本、来源与场景范围；不能宣称通用准确或生产级可靠。'}

def resolve_profile(store, identifier, configuration):
    if not identifier:
        return None
    if identifier == INITIAL_ID:
        definition = deepcopy(RUBRIC_TEMPLATE)
        rubric = RubricVersion(**definition, rubric_id=INITIAL_ID,
            created_at='2026-10-15T00:00:00+00:00', content_hash=digest(definition))
        value = {'profile_id':identifier,'name':'政策证据评分 · 初始未校准',
            'calibration_status':'INITIAL_UNVALIDATED','rubric':rubric.model_dump(mode='json'),
            'validation_scope':{'sample_count':0,'valid_human_reference_count':0,'research_status':'PENDING'},
            'protocol':{'prompt':ALIAS_PROMPT,'examples':[],'output_schema':'EXACT_FRAGMENT_ALIASES_V1','wire_contract_version':'JUDGE_WIRE_V2'},
            'judge_configuration':configuration.resolved()['judge']}
    else:
        conclusion = store.get('calibration_conclusions', identifier)
        if conclusion.decision != 'ADOPT' or conclusion.research_status == 'PENDING' or adoption_restrictions(conclusion.report_snapshot.get('comparison',{})):
            raise ValueError('SCORING_PROFILE_NOT_VALIDATED')
        comparison = store.get('calibration_comparisons', conclusion.comparison_id)
        run = store.get('calibration_runs', comparison.candidate_run_id)
        if run.protocol_snapshot.evidence_contract_version!='EVIDENCE_CONTRACT_V2':raise ValueError('SCORING_ENGINE_CHANGED_NEW_PROTOCOL_REQUIRED')
        if run.protocol_snapshot.provider_configuration.resolved()['judge'] != configuration.resolved()['judge']:
            raise ValueError('SCORING_PROFILE_MODEL_MISMATCH')
        value = {'profile_id':identifier,'name':run.protocol_snapshot.name,
            'calibration_status':conclusion.research_status,'conclusion_id':identifier,
            'validation_scope':validation_scope(conclusion),
            'rubric':run.rubric_snapshot.model_dump(mode='json'),
            'protocol':run.protocol_snapshot.model_dump(mode='json'),
            'judge_configuration':configuration.resolved()['judge']}
    value['evidence_contract_version']='EVIDENCE_CONTRACT_V2'
    from .judge_jobs import component_identity
    value['scoring_components']=component_identity()
    value['content_hash'] = digest(value)
    return value

def available_profiles(store):
    values = [{'profile_id':INITIAL_ID,'name':'政策证据评分 · 初始未校准','status':'INITIAL_UNVALIDATED','validation_scope':{'sample_count':0,'valid_human_reference_count':0,'research_status':'PENDING'}}]
    for item in store.list('calibration_conclusions'):
        if item.decision == 'ADOPT' and (item.report_snapshot.get('runs',[{},{}])[-1].get('protocol_snapshot') or {}).get('evidence_contract_version')=='EVIDENCE_CONTRACT_V2' and item.research_status != 'PENDING' and not adoption_restrictions(item.report_snapshot.get('comparison',{})):
            values.append({'profile_id':item.conclusion_id,'name':item.report_snapshot['runs'][1]['protocol_snapshot']['name'],
                'status':item.research_status,'validation_scope':validation_scope(item)})
    return values

def scoring_identity(profile):
    return {'kind':'EVIDENCE_RUBRIC_V1','profile_id':profile['profile_id'],
        'profile_hash':profile['content_hash'],'rubric_hash':profile['rubric']['content_hash'],
        'calibration_status':profile['calibration_status'],'scale':'0/1/2; INSUFFICIENT; NA',
        'result_schema_version':'TRUSTED_RESULT_V1','validation_scope':profile.get('validation_scope')}

async def score_grounded(provider, profile, case, answer, retrieval, documents):
    from .calibration_models import CalibrationResult
    package = freeze_input(case,retrieval,answer,documents,retrieval.get('run_id'))
    retrieval['input_package'] = package
    blocking=[v for v in package['missing_items'] if v!='REFERENCE_COMPLETENESS_UNCONFIRMED']
    if blocking or package['truncated_items'] or package['check']['issues']:
        return CalibrationResult(sample_id=case.case_id,repetition=1,status='NOT_RUN',
            error='EVIDENCE_INSUFFICIENT',request_count=0)
    from .evidence_policy import selected_history
    sample = CalibrationSample(sample_id=case.case_id, group_id=case.group_id or case.case_id,
        partition='CALIBRATION', question=case.query, context=selected_history(case), answer=answer,
        retrieved_evidence=[{'evidence_id':r['chunk_id'],'document_id':r['document_id'],'text':r['text']}
            for r in retrieval['results']],
        reference_policy=[{'evidence_id':d['document_id'],'document_id':d['document_id'],'text':d['text']}
            for d in documents], reference_complete=case.reference_complete is True,
        expected_facts=[*case.must_do,*([case.expected_answer] if case.expected_answer else [])],
        origin=source_identity(case), scenario=case.scenario or '政策知识问答',
        provenance={'schema_version':'TRUSTED_RESULT_V1','input_id':package['input_id'],
            'reference_completeness':case.reference_completeness,
            'reference_completeness_known':case.reference_complete is not None,
            'evidence_context':case.evidence_context,'scenario_rules':case.scenario_rules,'tool_evidence':retrieval.get('tool_evidence',[])})
    rubric = RubricVersion.model_validate(profile['rubric'])
    if profile['protocol']['output_schema'] == 'EXACT_FRAGMENT_ALIASES_V1':
        return await score_alias_answer(provider,rubric,sample,SimpleNamespace(**profile['protocol']))
    return await score_answer(provider, SimpleNamespace(**profile['protocol']), rubric, sample, 1)
