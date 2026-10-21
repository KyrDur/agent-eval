"""Agent holdout checks: lock candidates before acquiring private, paired results."""
import re
from difflib import SequenceMatcher
from pydantic import Field
from .models import Artifact, now, uid
from .canonical import digest, evaluation_protocol
from .retrieval_models import RetrievalCase
from .retrieval_metrics import aggregate, transition, answer_transition

def same_case_family(a, b):
    def normalized(case):return re.sub(r'[^\w]','',case.query).lower()
    return (bool(a.group_id and a.group_id==b.group_id)
        or bool(a.template_id and a.template_id==b.template_id)
        or bool(a.source_chat_turn_id and a.source_chat_turn_id==b.source_chat_turn_id)
        or SequenceMatcher(None,normalized(a),normalized(b)).ratio()>=.84)

def validate_split(cases, reviewed):
    if not any(c.partition=='HOLDOUT' for c in cases):return
    if any(c.partition=='HOLDOUT' and c.evidence_context.get('used_for_tuning') for c in cases):raise ValueError('HOLDOUT_USED_FOR_TUNING')
    if not reviewed or any(not c.group_id for c in cases):raise ValueError('HOLDOUT_GROUP_REVIEW_REQUIRED')
    if not any(c.partition=='DEBUG' for c in cases):raise ValueError('DEBUG_PARTITION_REQUIRED')
    for a in cases:
        for b in cases:
            if a.partition!=b.partition and same_case_family(a,b):raise ValueError('CROSS_PARTITION_FAMILY')

class RetrievalValidation(Artifact):
    validation_id: str = Field(default_factory=uid)
    comparison_id: str
    baseline_run_id: str
    candidate_run_id: str
    reason: str = Field(min_length=1,max_length=5000)
    request_budget: int = Field(ge=1,le=500)
    expected_requests: int
    baseline_snapshot: dict
    candidate_snapshot: dict
    heldout_cases: list[dict]
    content_hash: str
    status: str = 'LOCKED'
    run_ids: list[str] = Field(default_factory=list)
    released_at: str | None = None
    error: str | None = None
    report: dict | None = None

class RetrievalValidationService:
    def __init__(self, rag):
        self.rag=rag;self.store=rag.store
        with self.store.transaction():
            for item in self.store.list('retrieval_validations'):
                if item.status!='RUNNING':continue
                try:lease=self.store.acquire_run_lease(item.validation_id,'retrieval_validations')
                except BlockingIOError:continue
                try:
                    self.store.put('retrieval_validations',item.model_copy(update={'status':'FAILED',
                        'released_at':now(),'error':'PROCESS_INTERRUPTED',
                        'report':{'status':'FAILED','error':'PROCESS_INTERRUPTED','independent_holdout_reusable':False}}))
                finally:lease.close()

    def lock(self, comparison_id, reason, request_budget):
        from .retrieval_service import implementation_snapshot
        comparison=self.store.get('retrieval_comparisons',comparison_id)
        if not comparison.comparable or not comparison.single_recorded_change:raise ValueError('COMPARABLE_DEBUG_COMPARISON_REQUIRED')
        a=self.store.get('retrieval_runs',comparison.baseline_run_id)
        b=self.store.get('retrieval_runs',comparison.retest_run_id)
        if a.status!='COMPLETE' or b.status!='COMPLETE':raise ValueError('COMPLETE_DEBUG_RUNS_REQUIRED')
        if any(r.controls.get('evaluation_scope',{}).get('partition')!='DEBUG' for r in (a,b)):
            raise ValueError('FRESH_DEBUG_BASELINE_REQUIRED')
        cases=[RetrievalCase.model_validate(c) for c in a.controls['eval_set_snapshot']['cases']]
        validate_split(cases,a.controls['eval_set_snapshot'].get('split_reviewed',False))
        heldout=[c for c in cases if c.partition=='HOLDOUT']
        if not heldout:raise ValueError('HOLDOUT_PARTITION_REQUIRED')
        for r in (a,b):
            if r.controls['retrieval_implementation']!=implementation_snapshot() or r.controls['evaluation_protocol_hash']!=digest(evaluation_protocol()):
                raise ValueError('IMPLEMENTATION_CHANGED_CREATE_BASELINE')
        expected=sum(len(heldout)*(int(r.retrieval_config.query_rewrite)+int(r.retrieval_config.rerank)+(2 if r.verify_answers else 0)) for r in (a,b))
        if expected>request_budget:raise ValueError('HOLDOUT_REQUEST_BUDGET_TOO_SMALL')
        with self.store.transaction():
            for old in self.store.list('retrieval_validations'):
                if any(same_case_family(c,RetrievalCase.model_validate(v)) for c in heldout for v in old.heldout_cases):
                    raise ValueError('HOLDOUT_ALREADY_LOCKED_OR_EXPOSED')
            # Historical runs may have used HOLDOUT as a display label. Such cases
            # cannot be recycled into a fresh independent validation.
            for old in self.store.list('retrieval_runs'):
                if old.run_id in (a.run_id,b.run_id):continue
                seen={r['case_id'] for r in old.case_results if r.get('partition')=='HOLDOUT'}
                prior=[RetrievalCase.model_validate(c) for c in old.controls['eval_set_snapshot']['cases'] if c['case_id'] in seen]
                if any(same_case_family(c,p) for c in heldout for p in prior):raise ValueError('HOLDOUT_ALREADY_EXPOSED')
            snapshots={'baseline':a.model_dump(mode='json'),'candidate':b.model_dump(mode='json'),
                'heldout_cases':[c.model_dump(mode='json') for c in heldout]}
            value=RetrievalValidation(comparison_id=comparison_id,baseline_run_id=a.run_id,candidate_run_id=b.run_id,
                reason=reason,request_budget=request_budget,expected_requests=expected,
                baseline_snapshot=snapshots['baseline'],candidate_snapshot=snapshots['candidate'],
                heldout_cases=snapshots['heldout_cases'],content_hash=digest(snapshots))
            return self.store.put('retrieval_validations',value)

    def view(self, identifier):
        item=self.store.get('retrieval_validations',identifier)
        return {k:getattr(item,k) for k in ('validation_id','comparison_id','baseline_run_id','candidate_run_id',
            'created_at','reason','request_budget','expected_requests','status','released_at','error')} | {
            'heldout_count':len(item.heldout_cases),'isolation':'WORKFLOW_ONLY',
            'report':item.report if item.released_at else None}

    def history(self, comparison_id):
        comparison=self.store.get('retrieval_comparisons',comparison_id)
        return [self.view(v.validation_id) for v in self.store.list('retrieval_validations')
            if v.comparison_id==comparison_id or (v.baseline_run_id==comparison.baseline_run_id
                and v.candidate_run_id==comparison.retest_run_id)]

    async def execute(self, identifier, provider_session_id):
        from .retrieval_service import implementation_snapshot
        item=self.store.get('retrieval_validations',identifier)
        if item.status!='LOCKED':raise ValueError('HOLDOUT_VALIDATION_ALREADY_STARTED')
        session=self.rag.providers.get(provider_session_id)
        for source in (item.baseline_snapshot,item.candidate_snapshot):
            if session.configuration.model_dump()!=source['provider_configuration_snapshot']:raise ValueError('PROVIDER_CONFIG_CHANGED')
            per_run=len(item.heldout_cases)*(int(source['retrieval_config']['query_rewrite'])+int(source['retrieval_config']['rerank'])+(2 if source['verify_answers'] else 0))
            if per_run>session.configuration.max_calls:raise ValueError('CALL_BUDGET_EXCEEDED')
            if source['controls']['retrieval_implementation']!=implementation_snapshot():raise ValueError('IMPLEMENTATION_CHANGED_CREATE_BASELINE')
        # Resolve credentials and readiness before changing the sealed lock state.
        self.rag.providers.credential(provider_session_id)
        if session.text_connection_status!='READY':raise ValueError('CONNECTION_NOT_VERIFIED')
        with self.store.transaction():
            current=self.store.get('retrieval_validations',identifier)
            if current.status!='LOCKED':raise ValueError('HOLDOUT_VALIDATION_ALREADY_STARTED')
            lease=self.store.acquire_run_lease(identifier,'retrieval_validations')
            try:item=self.store.put('retrieval_validations',current.model_copy(update={'status':'RUNNING'}))
            except BaseException:lease.close();raise
        runs=[];error=None
        try:
            for source in (item.baseline_snapshot,item.candidate_snapshot):
                ev=source['controls']['eval_set_snapshot']
                profile=source['controls'].get('scoring_profile')
                remaining=item.request_budget-sum(r.provider_call_count for r in runs)
                if remaining<=0:raise ValueError('CALL_BUDGET_EXCEEDED')
                run=await self.rag.run(provider_session_id,ev['retrieval_eval_set_id'],version=ev['version'],
                    retrieval_config=source['retrieval_config'],verify_answers=source['verify_answers'],
                    scoring_profile_id=profile['profile_id'] if profile else None,
                    _partition='HOLDOUT',_sink_group='retrieval_validation_runs',_request_limit=remaining)
                # Every control except selected execution partition must retain
                # its frozen debug value. Knowledge updates retain their own side.
                controls=dict(run.controls);controls['execution_order']=source['controls']['execution_order']
                controls['evaluation_scope']=source['controls']['evaluation_scope']
                if controls!=source['controls']:raise ValueError('FROZEN_VALIDATION_CONTROLS_CHANGED')
                runs.append(run)
                with self.store.transaction():
                    item=self.store.put('retrieval_validations',item.model_copy(update={'run_ids':[r.run_id for r in runs]}))
        except BaseException as failure:
            # Persist a bounded classification, never provider exception bodies.
            error=str(failure) if isinstance(failure,ValueError) and re.fullmatch('[A-Z_]{3,100}',str(failure)) else 'HOLDOUT_ACQUISITION_FAILED'
        finally:
            from .trusted_results import sample_flow
            complete=len(runs)==2 and all(r.status=='COMPLETE' and sample_flow(r)['complete'] for r in runs)
            report=self.report(item,runs,error)
            with self.store.transaction():
                self.store.put('retrieval_validations',item.model_copy(update={'status':'COMPLETE' if complete and not error else 'FAILED',
                    'run_ids':[r.run_id for r in runs],'released_at':now(),'error':error,'report':report}))
            lease.close()
        return self.view(identifier)

    def report(self, item, runs, error):
        from .trusted_results import sample_flow,answer_trust,comparison_trust
        flows=[sample_flow(r) for r in runs]
        pairs=[]
        for case in item.heldout_cases:
            rows=[next((c for c in r.case_results if c['case_id']==case['case_id']),None) if case['case_id'] in f['retrieval_reconciliation']['valid_ids'] else None for r,f in zip(runs,flows)]
            answers=[next((a for a in r.answer_results if a.case_id==case['case_id']),None) if f['answer_reconciliation'] and case['case_id'] in f['answer_reconciliation']['valid_ids'] else None for r,f in zip(runs,flows)]
            rows=(rows+[None,None])[:2];answers=(answers+[None,None])[:2]
            movement,why=transition(*rows,error)
            pairs.append({'case_id':case['case_id'],'query':case['query'],'partition':'HOLDOUT',
                'transition':movement,'reason':why,'baseline':rows[0],'retest':rows[1],
                'baseline_answer':answers[0].to_dict() if answers[0] else None,
                'retest_answer':answers[1].to_dict() if answers[1] else None,
                'answer_transition':answer_transition(*answers,error or ('ANSWER_EVIDENCE_NOT_COMPARABLE' if any(answer_trust(a,(r or {}).get('input_package'),r)['evaluation_state'] not in {'PASS','FAIL'} for a,r in zip(answers,rows)) else None))})
        return {'status':'ACQUIRED' if not error and len(runs)==2 else 'INCOMPLETE','error':error,
            'case_pairs':pairs,'runs':[r.model_dump(mode='json') for r in runs],
            'provider_call_count':sum(r.provider_call_count for r in runs),
            'metrics_before':aggregate(runs[0].case_results,len(item.heldout_cases)) if runs else None,
            'metrics_after':aggregate(runs[1].case_results,len(item.heldout_cases)) if len(runs)>1 else None,
            'trust_summary':comparison_trust(runs[0],runs[1],runs[0].answer_results,runs[1].answer_results,not error) if len(runs)==2 else None,
            'independent_holdout_reusable':False,
            'limitations':['解封后不再作为新的独立保留集。','单轮差异不证明因果。','构造或演示题不代表真实业务分布。']}
