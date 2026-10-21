"""Read-only readiness checks. Never opens a blind session or fabricates a label."""
from collections import Counter
from .canonical import digest
from .calibration_service import CalibrationService, same_family


def calibration_readiness(store, dataset_id, rubric_id):
    dataset=store.get('calibration_datasets',dataset_id)
    rubric=store.get('calibration_rubrics',rubric_id)
    # The normal constructor recovers interrupted runs. An audit must not do that.
    reader=object.__new__(CalibrationService)
    reader.store=store
    references=reader.reference(dataset_id,rubric_id)
    annotations=[a for a in store.list('calibration_annotations')
                 if a.dataset_id==dataset_id and a.rubric_id==rubric_id]
    access=[a for a in store.list('calibration_access') if a.dataset_id==dataset_id]
    runs=[r for r in store.list('calibration_runs') if r.dataset_id==dataset_id]
    groups=Counter(s.partition for s in dataset.samples)
    valid={s.sample_id for s in dataset.samples
           if (references.get(s.sample_id,{}).get('judgment') or {}).get('verdict') in {'PASS','FAIL'}}
    independent=[a for a in annotations if a.source=='HUMAN' and a.independent
                 and not a.seen_machine and not a.seen_peer]
    cross=[(a.sample_id,b.sample_id) for i,a in enumerate(dataset.samples)
           for b in dataset.samples[i+1:] if a.partition!=b.partition and same_family(a,b)]
    released=any(a.kind in {'HOLDOUT_RELEASE','HOLDOUT_INVALIDATED'} for a in access)
    incomplete=[s.sample_id for s in dataset.samples if not s.answer.strip()
                or not s.reference_policy or not s.retrieved_evidence]
    missing_refs=sorted({s.sample_id for s in dataset.samples}-valid)
    blockers=[]
    if missing_refs: blockers.append('INDEPENDENT_VALID_REFERENCE_INCOMPLETE')
    if cross: blockers.append('CROSS_PARTITION_FAMILY')
    if released: blockers.append('HOLDOUT_ALREADY_RELEASED')
    if incomplete: blockers.append('MATERIAL_REVIEW_REQUIRED')
    if not groups['CALIBRATION'] or not groups['HOLDOUT']: blockers.append('PARTITION_MISSING')
    return {
        'schema_version':'RESEARCH_READINESS_V1','dataset_id':dataset_id,'rubric_id':rubric_id,
        'dataset_content_hash':dataset.content_hash,'rubric_content_hash':rubric.content_hash,
        'sample_count':len(dataset.samples),'question_family_count':len({s.group_id for s in dataset.samples}),
        'partitions':dict(groups),'origins':dict(Counter(s.origin for s in dataset.samples)),
        'independent_human_annotation_events':len(independent),
        'independent_human_annotators':len({a.annotator_id for a in independent}),
        'valid_reference_count':len(valid),'missing_reference_ids':missing_refs,
        'reference_states':dict(Counter(r['state'] for r in references.values())),
        'prior_machine_exposure_count':sum(s.prior_machine_exposure for s in dataset.samples),
        'access_events':dict(Counter(a.kind for a in access)),
        'holdout_released':released,'cross_partition_pairs':cross,
        'material_review_ids':incomplete,'machine_run_count':len(runs),
        'machine_scoring_events':sum(len(r.results) for r in runs),
        'ready_for_initial_judge_study':not blockers,'blockers':blockers,
        'reference_completeness_is_declaration':True,
        'policy_scope':'构造或演示政策；真实 API 回答不等于生产问题分布。',
        'standard_confirmation':'现有评分细则为初始未校准版本，需业务维护者确认适用范围。',
        'audit_scope':'只读核对封存内容与曝光元数据；未打开盲标会话、未向标注者展示分析、未生成标注或调用模型。',
        'source_snapshot_hash':digest({'dataset':dataset.model_dump(mode='json'),
                                      'rubric':rubric.model_dump(mode='json')})}
