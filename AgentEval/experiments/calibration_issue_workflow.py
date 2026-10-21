"""Issue evidence shared by calibration and the main RAG workflow.

All references resolve through the current workspace's store. No generic lookup of
private validation runs is permitted here; calibration reads retain blind access.
"""
from .canonical import digest
from .calibration_models import CalibrationIssue, CalibrationIssueEvent, IssueRepairPlan, IssueVerificationReport


ISSUE_ROUTES = {
    'DATA': {'action':'检查原始记录、解析与关联；保留原输入，建立带父引用的派生输入', 'verification_kind':'DATA_REPLAY', 'destination':'calibration'},
    'PROMPT': {'action':'固定回答、业务标准与人工参照，进入 Judge 提示词校准', 'verification_kind':'CALIBRATION', 'destination':'calibration'},
    'RUBRIC': {'action':'修订业务规则并按新标准重新标注；保留旧口径', 'verification_kind':'RUBRIC_STUDY', 'destination':'calibration'},
    'AGENT': {'action':'进入主实验的单项修改，固定评分条件并记录收益与风险', 'verification_kind':'RETRIEVAL', 'destination':'retrieval'},
}


class IssueWorkflow:
    def __init__(self, calibration):
        self.cal = calibration
        self.store = calibration.store

    def source(self, run_id, sample_id, actor, source_type='CALIBRATION', source_id=None):
        if source_type == 'CALIBRATION':
            view = self.cal.issue_access(run_id, sample_id, actor)
            run = self.store.get('calibration_runs', run_id)
            sample = next(s for s in run.sample_snapshot if s.sample_id == sample_id)
            return {'dataset_id':run.dataset_id, 'rubric_id':run.rubric_id, 'run_id':run_id,
                'sample_id':sample_id, 'source_type':source_type, 'source_id':source_id,
                'snapshot':{'question':sample.question, 'answer':sample.answer,
                    'sample_hash':digest(sample.model_dump(mode='json')), 'dataset_hash':run.dataset_hash,
                    'rubric_hash':run.rubric_snapshot.content_hash, 'protocol_id':run.protocol_id,
                    'protocol_hash':run.protocol_snapshot.content_hash,
                    'source_run_id':sample.source_run_id, 'source_case_id':sample.source_case_id,
                    'results':[r.model_dump(mode='json') for r in view['results'] if r.sample_id == sample_id]}}
        # Only ordinary RAG runs can be selected. Private validation runs live in
        # a separate group and are deliberately never searched as a fallback.
        run = self.store.get('retrieval_runs', run_id)
        if run.status == 'RUNNING' or sample_id not in run.execution_order:
            raise ValueError('ISSUE_SCOPE_INVALID')
        cases = run.controls.get('eval_set_snapshot', {}).get('cases', [])
        case = next((c for c in cases if c['case_id'] == sample_id), None)
        if not case or case.get('partition', 'DEBUG') == 'HOLDOUT':
            raise ValueError('HOLDOUT_LOCKED')
        linked = None
        if source_type == 'RETRIEVAL_COMPARISON':
            linked = self.store.get('retrieval_comparisons', source_id)
            if run_id not in {linked.baseline_run_id, linked.retest_run_id}:
                raise ValueError('ISSUE_SCOPE_INVALID')
        elif source_type == 'RETRIEVAL_REVIEW':
            linked = self.store.get('retrieval_reviews', source_id)
            if linked.run_id != run_id or linked.case_id != sample_id:
                raise ValueError('ISSUE_SCOPE_INVALID')
        elif source_type != 'RETRIEVAL_RUN':
            raise ValueError('ISSUE_SCOPE_INVALID')
        answers = [r for r in run.answer_results if r.case_id == sample_id]
        profile = run.controls.get('scoring_profile') or {}
        rubric = profile.get('rubric') or {}
        answer = answers[0] if len(answers) == 1 else None
        return {'dataset_id':run.controls['eval_set_snapshot']['retrieval_eval_set_id'],
            'rubric_id':rubric.get('rubric_id') or run.controls.get('evaluation_protocol_hash', 'UNKNOWN'),
            'run_id':run_id, 'sample_id':sample_id, 'source_type':source_type, 'source_id':source_id,
            'snapshot':{'question':case['query'], 'answer':answer.turn_evidence[-1].response if answer and answer.turn_evidence else '',
                'case_hash':digest(case), 'controls_hash':digest(run.controls), 'run_type':run.run_type,
                'rubric_hash':rubric.get('content_hash'), 'scoring_profile_hash':profile.get('content_hash'),
                'judge_protocol':profile.get('protocol'), 'judge_configuration':profile.get('judge_configuration'),
                'evaluation_protocol_hash':run.controls.get('evaluation_protocol_hash'),
                'answer_result':answer.model_dump(mode='json') if answer else None,
                'source_record':linked.model_dump(mode='json') if linked else None}}

    def create(self, dataset_id, sample_id, run_id, actor, title, layer, owner, description, **details):
        if not all(v.strip() for v in (actor,title,owner,description)):
            raise ValueError('ISSUE_INPUT_INVALID')
        source = self.source(run_id,sample_id,actor,details.get('source_type','CALIBRATION'),details.get('source_id'))
        if source['dataset_id'] != dataset_id:
            raise ValueError('ISSUE_SCOPE_INVALID')
        if details.get('agent_component')=='TOOL':
            # This workspace currently stores policy RAG evidence, with no
            # business-action tool execution to attribute a defect to.
            raise ValueError('ISSUE_COMPONENT_NOT_EXECUTED')
        if details.get('observed_count') is not None:
            if not details.get('observed_denominator') or details['observed_count'] > details['observed_denominator'] or not details.get('sampling_source','').strip():
                raise ValueError('ISSUE_PRIORITY_SCOPE_REQUIRED')
        if details.get('repair_plan'):
            plan=IssueRepairPlan.model_validate(details['repair_plan'])
            if sample_id not in plan.verification_sample_ids:
                raise ValueError('ISSUE_PLAN_REQUIRED')
        issue = CalibrationIssue(schema_version='ISSUE_REPAIR_V2',dataset_id=dataset_id,sample_id=sample_id,run_id=run_id,
            rubric_id=source['rubric_id'],actor=actor,title=title,layer=layer,owner=owner,
            description=description,baseline_snapshot=source['snapshot'],**details)
        with self.store.transaction():
            return self.store.put('calibration_issues',issue)

    def events(self, issue_id):
        return sorted([e for e in self.store.list('calibration_issue_events') if e.issue_id == issue_id],
                      key=lambda e:(e.created_at,e.event_id))

    def view(self, dataset_id, actor, source_type=None, run_id=None):
        items=[]
        for issue in self.store.list('calibration_issues'):
            if dataset_id is not None and issue.dataset_id != dataset_id: continue
            if source_type is not None and issue.source_type != source_type: continue
            if run_id is not None and issue.run_id != run_id: continue
            try: self.source(issue.run_id,issue.sample_id,actor,issue.source_type,issue.source_id)
            except (ValueError,FileNotFoundError): continue
            events=self.events(issue.issue_id); latest=events[-1] if events else None
            items.append({'issue':issue,'events':events,'status':latest.to_status if latest else 'OPEN',
                'closure_type':latest.closure_type if latest and latest.to_status=='CLOSED' else None,
                'evidence_level':latest.evidence_level if latest else 'UNVERIFIED',
                'next_action':ISSUE_ROUTES[issue.layer]})
        return items

    def verification(self,issue,run_id,sample_id,actor,kind,changed,plan,outcome,report,evidence_level):
        if run_id == issue.run_id:raise ValueError('ISSUE_VERIFICATION_INVALID')
        if kind != ISSUE_ROUTES[issue.layer]['verification_kind']:
            raise ValueError('ISSUE_VERIFICATION_KIND_INVALID')
        sample_id = sample_id or issue.sample_id
        wanted = set(plan.verification_sample_ids) if plan else {sample_id}
        if kind == 'RETRIEVAL':
            if issue.source_type == 'CALIBRATION':
                base_id=issue.baseline_snapshot.get('source_run_id')
                if issue.baseline_snapshot.get('source_case_id') != sample_id:
                    raise ValueError('ISSUE_SCOPE_INVALID')
            else: base_id=issue.run_id
            if not base_id: raise ValueError('ISSUE_VERIFICATION_KIND_INVALID')
            base=self.store.get('retrieval_runs',base_id)
            validation=None; extra_results=[]
            try:run=self.store.get('retrieval_runs',run_id)
            except FileNotFoundError:
                validation=self.store.get('retrieval_validations',run_id)
                if (evidence_level!='UNSEEN' or validation.status!='COMPLETE' or not validation.released_at
                    or validation.baseline_run_id!=base_id or len(validation.run_ids)!=2):raise ValueError('HOLDOUT_LOCKED')
                run=self.store.get('retrieval_runs',validation.candidate_run_id)
                held=self.store.get('retrieval_validation_runs',validation.run_ids[1])
                from .trusted_results import sample_flow
                if not sample_flow(held)['complete']:raise ValueError('ISSUE_VERIFICATION_INVALID')
                extra_results=list(held.answer_results)
                if validation.created_at < changed.created_at:raise ValueError('ISSUE_VERIFICATION_INVALID')
            self.source(run.run_id,sample_id,actor,'RETRIEVAL_RUN')
            if run.run_type!='RETEST' or run.parent_run_id!=base_id or not run.change_id:
                raise ValueError('ISSUE_VERIFICATION_KIND_INVALID')
            change=self.store.get('retrieval_changes',run.change_id)
            if change.implemented_status!='APPLIED' or not change.observed_diff:
                raise ValueError('ISSUE_CHANGE_NOT_OBSERVED')
            keys=('evaluation_config','evaluation_protocol_hash','scoring_profile','verify_answers')
            if any(base.controls.get(k)!=run.controls.get(k) for k in keys):
                raise ValueError('ISSUE_VERIFICATION_VERSION_INVALID')
            before_cases={c['case_id']:c for c in base.controls['eval_set_snapshot']['cases']}
            after_cases={c['case_id']:c for c in run.controls['eval_set_snapshot']['cases']}
            if any(before_cases.get(s)!=after_cases.get(s) for s in wanted):
                raise ValueError('ISSUE_VERIFICATION_VERSION_INVALID')
            all_results=[*run.answer_results,*extra_results]
            results={r.case_id:r for r in all_results}
            usable={sid:r.original_status for sid,r in results.items() if r.execution_status=='SUCCESS'
                and r.judge_status=='SUCCESS' and not r.evaluation_error and r.original_status in {'PASS','FAIL'}}
            from .trusted_results import sample_flow
            flows=[sample_flow(run)] + ([sample_flow(held)] if validation else [])
            binary={sid for flow in flows for state in ('PASS','FAIL') for sid in flow['states'][state]['sample_ids']}
            usable={sid:state for sid,state in usable.items() if sid in binary}
            if len(results)!=len(all_results): usable={}
            snapshot={'run_id':run_id,'run_type':'AGENT_RERUN','change_id':run.change_id,
                'actual_diff':change.observed_diff,'controls_hash':digest(run.controls),
                'released_validation_id':validation.validation_id if validation else None}
            baseline_ids=set(base.execution_order)
        else:
            view=self.cal.issue_access(run_id,sample_id,actor)
            run=self.store.get('calibration_runs',run_id)
            sample=next(s for s in run.sample_snapshot if s.sample_id==sample_id)
            if issue.source_type == 'CALIBRATION':
                base=self.store.get('calibration_runs',issue.run_id)
                before=next(s for s in base.sample_snapshot if s.sample_id==issue.sample_id)
                if sample_id!=issue.sample_id and (sample.provenance.get('parent_dataset_id')!=issue.dataset_id
                    or sample.provenance.get('parent_sample_id')!=issue.sample_id):
                    raise ValueError('ISSUE_VERIFICATION_VERSION_INVALID')
                if sample.question!=before.question or sample.answer!=before.answer:
                    raise ValueError('ISSUE_VERIFICATION_VERSION_INVALID')
                if kind=='DATA_REPLAY' and run.dataset_id!=base.dataset_id and (
                    sample.provenance.get('parent_dataset_id')!=issue.dataset_id or sample.provenance.get('parent_sample_id')!=issue.sample_id):
                    raise ValueError('ISSUE_VERIFICATION_VERSION_INVALID')
                if kind!='RUBRIC_STUDY' and run.rubric_snapshot.content_hash!=base.rubric_snapshot.content_hash:
                    raise ValueError('ISSUE_VERIFICATION_VERSION_INVALID')
                if run.protocol_snapshot.provider_configuration!=base.protocol_snapshot.provider_configuration:
                    raise ValueError('ISSUE_VERIFICATION_VERSION_INVALID')
                if kind=='CALIBRATION':
                    stable=('evidence_input','output_schema','parser_version')
                    if (run.dataset_hash!=base.dataset_hash or any(getattr(run.protocol_snapshot,k)!=getattr(base.protocol_snapshot,k) for k in stable)):
                        raise ValueError('ISSUE_VERIFICATION_VERSION_INVALID')
                    if run.protocol_snapshot.prompt==base.protocol_snapshot.prompt and run.protocol_snapshot.examples==base.protocol_snapshot.examples:
                        raise ValueError('ISSUE_CHANGE_NOT_OBSERVED')
                if kind=='DATA_REPLAY' and digest(sample.model_dump(mode='json'))==digest(before.model_dump(mode='json')) and all(
                    getattr(run.protocol_snapshot,k)==getattr(base.protocol_snapshot,k) for k in ('evidence_input','output_schema','parser_version')):
                    raise ValueError('ISSUE_CHANGE_NOT_OBSERVED')
                baseline_ids={s.sample_id for s in base.sample_snapshot}
            else:
                if sample.source_run_id!=issue.run_id or sample.source_case_id!=issue.sample_id or sample.answer!=issue.baseline_snapshot.get('answer'):
                    raise ValueError('ISSUE_VERIFICATION_VERSION_INVALID')
                if kind!='RUBRIC_STUDY' and run.rubric_snapshot.content_hash!=issue.baseline_snapshot.get('rubric_hash'):
                    raise ValueError('ISSUE_VERIFICATION_VERSION_INVALID')
                mapping={s.source_case_id:s.sample_id for s in run.sample_snapshot if s.source_run_id==issue.run_id}
                wanted={mapping.get(s,s) for s in wanted}
                old_protocol=issue.baseline_snapshot.get('judge_protocol') or {}
                if kind=='CALIBRATION' and run.protocol_snapshot.prompt==old_protocol.get('prompt') and run.protocol_snapshot.examples==old_protocol.get('examples',[]):
                    raise ValueError('ISSUE_CHANGE_NOT_OBSERVED')
                old_judge=issue.baseline_snapshot.get('judge_configuration')
                if old_judge and run.protocol_snapshot.provider_configuration.resolved()['judge']!=old_judge:
                    raise ValueError('ISSUE_VERIFICATION_VERSION_INVALID')
                baseline_ids={s.sample_id for s in run.sample_snapshot}
            if kind=='RUBRIC_STUDY':
                if run.rubric_snapshot.content_hash==issue.baseline_snapshot.get('rubric_hash'):
                    raise ValueError('ISSUE_CHANGE_NOT_OBSERVED')
                reference=run.reference_snapshot.get(sample_id,{})
                if (reference.get('judgment') or {}).get('verdict') not in {'PASS','FAIL'}:
                    raise ValueError('INDEPENDENT_HUMAN_REFERENCE_REQUIRED')
            pairs={(r.sample_id,r.repetition):[] for r in view['results']}
            for r in view['results']: pairs[(r.sample_id,r.repetition)].append(r)
            usable={}
            for sid in {r.sample_id for r in view['results']}:
                rows=[pairs.get((sid,n),[]) for n in range(1,run.repetitions+1)]
                if all(len(rs)==1 and rs[0].status=='SUCCESS' and rs[0].judgment and rs[0].judgment.verdict in {'PASS','FAIL'} for rs in rows):
                    usable[sid]=[rs[0].judgment.verdict for rs in rows]
            snapshot={'run_id':run_id,'run_type':'FIXED_ANSWER_RESCORING','dataset_id':run.dataset_id,
                'rubric_id':run.rubric_id,'rubric_hash':run.rubric_snapshot.content_hash,
                'protocol_id':run.protocol_id,'protocol_hash':run.protocol_snapshot.content_hash}
        if run.status=='RUNNING' or run.created_at < changed.created_at:
            raise ValueError('ISSUE_VERIFICATION_INVALID')
        # A new successful request alone has no bearing on target-error removal.
        if outcome=='FIXED':
            if run.status not in {'COMPLETE','PARTIAL'}:raise ValueError('ISSUE_VERIFICATION_INVALID')
            if not plan: raise ValueError('ISSUE_PLAN_REQUIRED')
            required={sample_id,*wanted}
            if not required <= set(usable): raise ValueError('ISSUE_VERIFICATION_INVALID')
            if not report or not report.target_eliminated or not report.regression_checked or report.regression_found:
                raise ValueError('ISSUE_ACCEPTANCE_REQUIRED')
            verdicts=usable[sample_id] if isinstance(usable[sample_id],list) else [usable[sample_id]]
            if plan.expected_verdict and any(v!=plan.expected_verdict for v in verdicts):
                raise ValueError('ISSUE_ACCEPTANCE_REQUIRED')
        if report:
            claimed=set(report.regression_sample_ids+report.unseen_sample_ids)
            if not claimed <= set(usable): raise ValueError('ISSUE_VERIFICATION_INVALID')
            if set(report.unseen_sample_ids) & baseline_ids: raise ValueError('ISSUE_UNSEEN_SCOPE_INVALID')
        if evidence_level=='UNSEEN' and (not report or not report.unseen_sample_ids): raise ValueError('ISSUE_UNSEEN_SCOPE_INVALID')
        if evidence_level=='REGRESSION' and (not report or not report.regression_sample_ids): raise ValueError('ISSUE_VERIFICATION_INVALID')
        return {**snapshot,'sample_id':sample_id,'valid_scoring_sample_ids':sorted(usable),
            'target_verdicts':usable.get(sample_id),'verification_kind':kind}

    def update(self,issue_id,actor,to_status,note,previous_event_id=None,change_summary='',verification_run_id=None,outcome=None,
               candidate_causes=None,confirmed_cause='',repair_plan=None,verification_kind=None,verification_sample_id=None,
               verification_report=None,closure_type=None,evidence_level='UNVERIFIED'):
        if not actor.strip() or not note.strip(): raise ValueError('ISSUE_INPUT_INVALID')
        issue=self.store.get('calibration_issues',issue_id)
        self.source(issue.run_id,issue.sample_id,actor,issue.source_type,issue.source_id)
        events=self.events(issue_id);latest=events[-1] if events else None
        current=latest.to_status if latest else 'OPEN'
        if previous_event_id!=(latest.event_id if latest else None): raise ValueError('ISSUE_EVENT_CONFLICT')
        allowed={'OPEN':{'REPRODUCED','UNRESOLVED'},'REPRODUCED':{'CHANGED','UNRESOLVED'},
                 'CHANGED':{'RETESTED','UNRESOLVED'},'RETESTED':{'CLOSED','UNRESOLVED'},
                 'UNRESOLVED':{'REPRODUCED'},'CLOSED':set()}
        resolved_without_repair=to_status=='CLOSED' and closure_type in {'FALSE_ALARM','DEFERRED'} and current!='CLOSED'
        if to_status not in allowed[current] and not resolved_without_repair: raise ValueError('ISSUE_TRANSITION_INVALID')
        plan=next((e.repair_plan for e in reversed(events) if e.repair_plan),issue.repair_plan)
        if repair_plan is not None:
            if to_status!='CHANGED': raise ValueError('ISSUE_PLAN_ALREADY_FROZEN')
            plan=IssueRepairPlan.model_validate(repair_plan)
        if to_status=='CHANGED':
            if not change_summary.strip(): raise ValueError('ISSUE_CHANGE_REQUIRED')
            if not plan or issue.sample_id not in plan.verification_sample_ids: raise ValueError('ISSUE_PLAN_REQUIRED')
        report=IssueVerificationReport.model_validate(verification_report) if verification_report else None
        snapshot={}
        if to_status=='RETESTED':
            if not verification_run_id or outcome is None: raise ValueError('ISSUE_VERIFICATION_REQUIRED')
            changed=next(e for e in reversed(events) if e.to_status=='CHANGED')
            kind=verification_kind or ISSUE_ROUTES[issue.layer]['verification_kind']
            snapshot=self.verification(issue,verification_run_id,verification_sample_id,actor,kind,changed,plan,outcome,report,evidence_level)
            verification_kind=kind
            if outcome=='FIXED' and evidence_level=='UNVERIFIED': evidence_level='SAME_CASE'
        elif verification_run_id or report: raise ValueError('ISSUE_VERIFICATION_KIND_INVALID')
        if to_status=='CLOSED':
            closure_type=closure_type or 'FIXED'
            if closure_type=='FIXED':
                if not latest or latest.outcome!='FIXED' or not latest.verification_snapshot or not latest.verification_report:
                    raise ValueError('ISSUE_VERIFICATION_REQUIRED')
                evidence_level=latest.evidence_level
            elif closure_type=='FALSE_ALARM' and not issue.related_evidence and not candidate_causes:
                raise ValueError('ISSUE_ACCEPTANCE_REQUIRED')
            else: evidence_level='UNVERIFIED'
        elif closure_type: raise ValueError('ISSUE_TRANSITION_INVALID')
        with self.store.transaction():
            # Check again while locked so two clients cannot append competing heads.
            head=self.events(issue_id)
            if previous_event_id!=(head[-1].event_id if head else None): raise ValueError('ISSUE_EVENT_CONFLICT')
            return self.store.put('calibration_issue_events',CalibrationIssueEvent(schema_version='ISSUE_REPAIR_V2',issue_id=issue_id,actor=actor,
                previous_event_id=previous_event_id,from_status=current,to_status=to_status,note=note,
                change_summary=change_summary,verification_run_id=verification_run_id,outcome=outcome,
                candidate_causes=candidate_causes or [],confirmed_cause=confirmed_cause,
                repair_plan=plan if to_status=='CHANGED' else None,verification_kind=verification_kind,
                verification_sample_id=verification_sample_id,verification_report=report,
                verification_snapshot=snapshot,closure_type=closure_type,evidence_level=evidence_level))
