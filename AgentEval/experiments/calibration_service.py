"""Calibration lifecycle, blind annotation, protocol experiments and final validation."""
import asyncio
from copy import deepcopy
from difflib import SequenceMatcher
import json
import re
import time
from .canonical import digest
from .models import now, uid
from .calibration_models import (CalibrationSample, CalibrationDataset, RubricVersion, Annotation,
    Adjudication, CalibrationAccess, JudgeProtocolVersion, CalibrationRun, CalibrationComparison,
    CalibrationValidation, CalibrationConclusion, CalibrationIssue, CalibrationIssueEvent, Judgment, CAUSES)
from .provider_transport import ObservedProvider
from .providers import ProviderFailure
from evaluation.calibration import (RUBRIC_TEMPLATE, BASE_PROMPT, VERIFY_PROMPT, EXAMPLES_PROMPT,
    FRAGMENT_PROMPT, FRAGMENT_VERIFY_PROMPT, validate_rubric, check_judgment, sample_input, score_answer)
from evaluation.calibration_evidence import evidence_fragments
from evaluation.calibration_metrics import metrics_with_slices, fraction, adoption_restrictions

def normalized_question(sample):
    return re.sub(r'[^\w]', '', sample.question).lower()

def same_family(a,b):
    return (a.group_id==b.group_id or (a.template_id and a.template_id==b.template_id)
        or (a.source_run_id and a.source_run_id==b.source_run_id and a.source_case_id==b.source_case_id)
        or SequenceMatcher(None,normalized_question(a),normalized_question(b)).ratio()>=.84)

def judgment_identity(value):
    # Different wording in reasons is not an annotation disagreement.
    return {'scores':{k:v['score'] for k,v in value['dimensions'].items()},
            **{k:sorted(value[k]) if isinstance(value[k],list) else value[k]
               for k in ('verdict','critical_errors','task_resolved','faithful_to_available')}}

def judge_budget_limit(configuration):
    bound=configuration.judge_provider_configuration
    return min(configuration.max_calls,bound['max_calls']) if bound else configuration.max_calls

class CalibrationService:
    def __init__(self, experiments):
        self.experiments=experiments;self.store=experiments.store;self.providers=experiments.providers
        self.provider_factory=ObservedProvider
        # Leases distinguish a live coroutine from a process interrupted before sealing.
        with self.store.transaction():
            for run in self.store.list('calibration_runs'):
                if run.status!='RUNNING': continue
                try: lease=self.store.acquire_run_lease(run.run_id,'calibration_runs')
                except BlockingIOError: continue
                try:
                    self.store.put('calibration_runs',run.model_copy(update={'status':'FAILED','finished_at':now(),
                        'warnings':[*run.warnings,'PROCESS_INTERRUPTED'],
                        'metrics':metrics_with_slices(run.sample_snapshot,run.results,run.reference_snapshot,run.repetitions)}))
                finally: lease.close()
            for validation in self.store.list('calibration_validations'):
                if validation.status!='RUNNING': continue
                try: lease=self.store.acquire_run_lease(validation.validation_id,'calibration_validations')
                except BlockingIOError: continue
                try:
                    self.store.put('calibration_validations',validation.model_copy(update={'status':'FAILED'}))
                finally: lease.close()

    def get_dataset(self,identifier): return self.store.get('calibration_datasets',identifier)

    def sample(self,dataset_id,sample_id):
        return next(s for s in self.get_dataset(dataset_id).samples if s.sample_id==sample_id)

    def from_run(self,selection):
        run=self.store.get('retrieval_runs',selection['run_id'])
        if run.status not in {'COMPLETE','PARTIAL'}: raise ValueError('SOURCE_RUN_UNAVAILABLE')
        case=next(c for c in run.controls['eval_set_snapshot']['cases'] if c['case_id']==selection['case_id'])
        answer=next(a for a in run.answer_results if a.case_id==selection['case_id'])
        actual=answer.turn_evidence[-1].response if answer.turn_evidence else ''
        if not actual.strip(): raise ValueError('SOURCE_ANSWER_MISSING')
        retrieval=next(r for r in run.case_results if r['case_id']==selection['case_id'])
        snapshot=run.controls.get('knowledge_snapshot')
        docs=snapshot.get('documents',[]) if snapshot else []
        return CalibrationSample(group_id=selection['group_id'],partition=selection['partition'],
            question=case['query'],context=case.get('context',[]),answer=actual,
            retrieved_evidence=[{'evidence_id':r.get('chunk_id') or r['document_id'],
                'document_id':r['document_id'],'text':r['text'],'title':r.get('title','')} for r in retrieval['results']],
            reference_policy=[{'evidence_id':d['document_id'],'document_id':d['document_id'],
                'text':d['text'],'title':d.get('title','')} for d in docs],reference_complete=case.get('reference_complete') is True,
            expected_facts=[*case.get('must_do',[]),*([case['expected_answer']] if case.get('expected_answer') else [])],
            scenario=selection.get('scenario') or case.get('scenario') or '单事实',
            origin=selection['origin'],diagnostic=selection.get('diagnostic',False),
            source_run_id=run.run_id,source_case_id=case['case_id'],summary=selection.get('summary',''),
            prior_machine_exposure=True,creator_seen_content=True,
            machine_exposed_actors=[selection.get('source_viewer','workspace-user')],
            provenance={'type':'FROZEN_RETRIEVAL_RUN','source_controls_hash':digest(run.controls),
                'reference_policy_source':'ORIGINAL_SNAPSHOT' if docs else 'MISSING_HISTORICAL_SNAPSHOT',
                'reference_completeness_known':case.get('reference_complete') is not None,
                'reference_completeness':case.get('reference_completeness',{}),
                'evidence_context':case.get('evidence_context',{}),'scenario_rules':case.get('scenario_rules',{}),
                'input_package_hash':retrieval.get('input_package',{}).get('content_hash'),
                'historical_review_is_not_independent_annotation':True})

    def create_dataset(self,name,samples,selections,group_review_confirmed,priority_metric,acceptable_cost):
        values=[CalibrationSample.model_validate(s) for s in samples]+[self.from_run(s) for s in selections]
        if not values or len(values)>100 or len({s.sample_id for s in values})!=len(values): raise ValueError('DATASET_INVALID')
        for i,a in enumerate(values):
            for b in values[i+1:]:
                if a.partition!=b.partition and same_family(a,b): raise ValueError('CROSS_PARTITION_FAMILY')
        with self.store.transaction():
            released={a.dataset_id for a in self.store.list('calibration_access') if a.kind=='HOLDOUT_RELEASE'}
            for old in self.store.list('calibration_datasets'):
                if old.dataset_id not in released: continue
                if any(same_family(a,b) for a in values if a.partition=='HOLDOUT' for b in old.samples):
                    raise ValueError('HOLDOUT_ALREADY_EXPOSED')
            dataset=CalibrationDataset(name=name,samples=values,content_hash=digest([s.model_dump() for s in values]),
                group_review_confirmed=group_review_confirmed,priority_metric=priority_metric,acceptable_cost=acceptable_cost)
            return self.store.put('calibration_datasets',dataset)

    def create_rubric(self,definition=None,parent_rubric_id=None):
        data=deepcopy(definition or RUBRIC_TEMPLATE);validate_rubric(data)
        with self.store.transaction():
            if parent_rubric_id: self.store.get('calibration_rubrics',parent_rubric_id)
            return self.store.put('calibration_rubrics',RubricVersion(**data,parent_rubric_id=parent_rubric_id,content_hash=digest(data)))

    def derive_input(self,dataset_id,sample_id,corrections,reason,cleaning_version,semantic_mapping_version,actor):
        """Create a child input; preserve the original question and actual answer."""
        if not all(v.strip() for v in (reason,cleaning_version,semantic_mapping_version,actor)):
            raise ValueError('DATA_REPAIR_REASON_REQUIRED')
        allowed={'retrieved_evidence','reference_policy','reference_complete','context'}
        if not corrections or set(corrections)-allowed:raise ValueError('DATA_REPAIR_FIELDS_INVALID')
        parent=self.get_dataset(dataset_id);original=next(s for s in parent.samples if s.sample_id==sample_id)
        if any(a.dataset_id==dataset_id and a.kind in {'HOLDOUT_RELEASE','HOLDOUT_INVALIDATED'} for a in self.store.list('calibration_access')):
            raise ValueError('HOLDOUT_ALREADY_EXPOSED')
        if original.partition=='HOLDOUT':raise ValueError('HOLDOUT_LOCKED')
        data=original.model_dump(mode='json');data.update(corrections)
        data['provenance']={**original.provenance,'schema_version':'DATA_DERIVATION_V1','operation':'DATA_REPAIR_FIXED_ANSWER',
            'parent_dataset_id':dataset_id,'parent_sample_id':sample_id,'parent_input_id':digest(original.model_dump(mode='json')),
            'repair_reason':reason,'repair_actor':actor,'cleaning_version':cleaning_version,'semantic_mapping_version':semantic_mapping_version}
        data['prior_machine_exposure']=True
        data['machine_exposed_actors']=[] if original.prior_machine_exposure and not original.machine_exposed_actors else sorted(set([*original.machine_exposed_actors,actor]))
        child=CalibrationSample.model_validate(data)
        samples=[child.model_dump(mode='json') if s.sample_id==sample_id else s.model_dump(mode='json') for s in parent.samples]
        return self.create_dataset(parent.name+' · 派生取证修复',samples,[],True,parent.priority_metric,parent.acceptable_cost)

    def exposed(self,dataset,sample,actor):
        access=self.store.list('calibration_access')
        # Family lineage remains exposed across copies within this workspace.
        for candidate in self.store.list('calibration_datasets'):
            for previous in candidate.samples:
                if not same_family(sample,previous):continue
                if previous.prior_machine_exposure and (not previous.machine_exposed_actors or actor in previous.machine_exposed_actors):return True
                if any(a.dataset_id==candidate.dataset_id and a.actor==actor and a.kind in {'MACHINE_VIEW','HOLDOUT_RELEASE'} and previous.sample_id in a.sample_ids for a in access):return True
        return False

    def peer_exposed(self,dataset_id,sample_id,actor):
        sample=self.sample(dataset_id,sample_id);access=self.store.list('calibration_access')
        return any(a.dataset_id==candidate.dataset_id and a.actor==actor and a.kind=='ANNOTATION_VIEW'
                   and previous.sample_id in a.sample_ids for candidate in self.store.list('calibration_datasets')
                   for previous in candidate.samples if same_family(sample,previous) for a in access)

    def open_blind(self,dataset_id,sample_id,rubric_id,annotator_id):
        dataset=self.get_dataset(dataset_id);sample=self.sample(dataset_id,sample_id)
        rubric=self.store.get('calibration_rubrics',rubric_id)
        with self.store.transaction():
            access=self.store.put('calibration_access',CalibrationAccess(dataset_id=dataset_id,sample_ids=[sample_id],
                actor=annotator_id,kind='BLIND_OPEN',details={'rubric_id':rubric_id,
                    'prior_machine_exposure':self.exposed(dataset,sample,annotator_id),
                    'prior_peer_exposure':self.peer_exposed(dataset_id,sample_id,annotator_id)}))
        return {'blind_access_id':access.access_id,'sample':sample_input(sample),'sample_id':sample_id,
                'rubric':rubric,'prior_machine_exposure':access.details['prior_machine_exposure'],
                'prior_peer_exposure':access.details['prior_peer_exposure'],
                'fragments':evidence_fragments(sample),
                'notice':'原始回答复核、AI 建议和 Codex 验收都不计为独立人工参照。'}

    def annotate(self,dataset_id,sample_id,rubric_id,annotator_id,source,mode,judgment,seen_machine,
                 blind_access_id=None,labeled_at=None,seen_peer=False):
        dataset=self.get_dataset(dataset_id);sample=self.sample(dataset_id,sample_id)
        rubric=self.store.get('calibration_rubrics',rubric_id);value=Judgment.model_validate(judgment)
        check_judgment(value,sample,rubric)
        with self.store.transaction():
            if any(v.dataset_id==dataset_id for v in self.store.list('calibration_validations')):
                raise ValueError('REFERENCE_LOCKED')
            if mode=='BLIND':
                access=self.store.get('calibration_access',blind_access_id or '')
                if (access.kind!='BLIND_OPEN' or access.dataset_id!=dataset_id or access.sample_ids!=[sample_id]
                    or access.actor!=annotator_id or access.details['rubric_id']!=rubric_id): raise ValueError('BLIND_SESSION_INVALID')
                seen_machine=seen_machine or access.details['prior_machine_exposure']
            elif blind_access_id: raise ValueError('IMPORT_BLIND_SESSION_INVALID')
            seen_machine=seen_machine or self.exposed(dataset,sample,annotator_id)
            seen_peer=seen_peer or self.peer_exposed(dataset_id,sample_id,annotator_id)
            return self.store.put('calibration_annotations',Annotation(dataset_id=dataset_id,sample_id=sample_id,
                rubric_id=rubric_id,annotator_id=annotator_id,source=source,mode=mode,blind_access_id=blind_access_id,
                seen_machine=seen_machine,seen_peer=seen_peer,independent=source=='HUMAN' and not seen_machine and not seen_peer,
                labeled_at=labeled_at or now(),judgment=value))

    def reference(self,dataset_id,rubric_id):
        dataset=self.get_dataset(dataset_id);result={}
        annotations=[a for a in self.store.list('calibration_annotations') if a.dataset_id==dataset_id and a.rubric_id==rubric_id]
        adjudications=[a for a in self.store.list('calibration_adjudications') if a.dataset_id==dataset_id and a.rubric_id==rubric_id]
        for sample in dataset.samples:
            latest={}
            for a in sorted(annotations,key=lambda a:a.created_at):
                if a.sample_id==sample.sample_id and a.independent: latest[a.annotator_id]=a
            labels=list(latest.values());ids=sorted(a.annotation_id for a in labels)
            adjud=next((a for a in sorted(adjudications,key=lambda a:a.created_at,reverse=True)
                if a.sample_id==sample.sample_id and a.source=='HUMAN' and sorted(a.annotation_ids)==ids),None)
            state='MISSING';judgment=None
            if adjud: state='ADJUDICATED';judgment=adjud.judgment.model_dump()
            elif labels:
                identities=[judgment_identity(a.judgment.model_dump()) for a in labels]
                if all(v==identities[0] for v in identities):
                    state='SINGLE' if len(labels)==1 else 'AGREED';judgment=labels[0].judgment.model_dump()
                else: state='DISAGREEMENT'
            result[sample.sample_id]={'state':state,'annotation_ids':ids,'judgment':judgment,
                'adjudication_id':adjud.adjudication_id if adjud else None,'annotator_count':len(labels)}
        return result

    def human_agreement(self,dataset_id,rubric_id,sample_ids=None):
        refs=self.reference(dataset_id,rubric_id);pairs=[];agreed=[];pending=[]
        for sid,ref in refs.items():
            if sample_ids is not None and sid not in sample_ids: continue
            labels=[self.store.get('calibration_annotations',i) for i in ref['annotation_ids']]
            for i,a in enumerate(labels):
                for b in labels[i+1:]:
                    key=f'{sid}:{a.annotator_id}:{b.annotator_id}'
                    if a.judgment.verdict not in {'PASS','FAIL'} or b.judgment.verdict not in {'PASS','FAIL'}: pending.append(key);continue
                    pairs.append(key)
                    if a.judgment.verdict==b.judgment.verdict: agreed.append(key)
        return {'binary_agreement_before_adjudication':fraction(agreed,pairs),'unresolved_pair_ids':pending,
                'disagreement_sample_ids':[sid for sid,r in refs.items() if r['state']=='DISAGREEMENT']}

    def annotation_view(self,dataset_id,rubric_id,actor):
        dataset=self.get_dataset(dataset_id)
        self.store.get('calibration_rubrics',rubric_id)
        records=[a for a in self.store.list('calibration_annotations')
                 if a.dataset_id==dataset_id and a.rubric_id==rubric_id]
        submitted={a.sample_id for a in records if a.annotator_id==actor}
        refs=self.reference(dataset_id,rubric_id)
        actors=sorted({a.annotator_id for a in records})
        progress=[{'annotator_id':name,
                   'submitted_count':len({a.sample_id for a in records if a.annotator_id==name}),
                   'independent_human_count':len({a.sample_id for a in records if a.annotator_id==name and a.independent})}
                  for name in actors]
        agreement=self.human_agreement(dataset_id,rubric_id,submitted)
        agreement['disagreement_sample_ids']=[s for s in agreement['disagreement_sample_ids'] if s in submitted]
        peer_ids={a.sample_id for a in records if a.annotator_id!=actor and a.sample_id in submitted}
        if peer_ids:
            with self.store.transaction():
                self.store.put('calibration_access',CalibrationAccess(dataset_id=dataset_id,actor=actor,
                    kind='ANNOTATION_VIEW',sample_ids=sorted(peer_ids),details={'rubric_id':rubric_id}))
        return {'annotations':[a for a in records if a.sample_id in submitted],
                'references':{sid:ref for sid,ref in refs.items() if sid in submitted},
                'human_agreement':agreement,'progress':progress,'sample_count':len(dataset.samples),
                'own_submitted_count':len(submitted),'hidden_sample_count':len(dataset.samples)-len(submitted)}

    def adjudicate(self,dataset_id,sample_id,rubric_id,annotation_ids,adjudicator_id,source,judgment,reason):
        value=Judgment.model_validate(judgment);rubric=self.store.get('calibration_rubrics',rubric_id)
        check_judgment(value,self.sample(dataset_id,sample_id),rubric)
        with self.store.transaction():
            if any(v.dataset_id==dataset_id for v in self.store.list('calibration_validations')): raise ValueError('REFERENCE_LOCKED')
            ref=self.reference(dataset_id,rubric_id)[sample_id]
            if len(set(annotation_ids))<2 or sorted(annotation_ids)!=sorted(ref['annotation_ids']): raise ValueError('ADJUDICATION_REFERENCE_INVALID')
            return self.store.put('calibration_adjudications',Adjudication(dataset_id=dataset_id,sample_id=sample_id,
                rubric_id=rubric_id,annotation_ids=annotation_ids,adjudicator_id=adjudicator_id,source=source,judgment=value,reason=reason))

    def create_protocol(self,dataset_id,rubric_id,provider_session_id,name,variant,change_hypothesis,
                        parent_protocol_id=None,example_sample_ids=None,prompt_addendum='',citation_mode='VERBATIM'):
        if citation_mode not in {'VERBATIM','FRAGMENT_IDS','SHORT_IDS'}: raise ValueError('CITATION_MODE_INVALID')
        dataset=self.get_dataset(dataset_id);rubric=self.store.get('calibration_rubrics',rubric_id)
        session=self.providers.get(provider_session_id);examples=[];example_sample_ids=example_sample_ids or []
        if variant!='J3' and example_sample_ids or variant=='J3' and not example_sample_ids: raise ValueError('PROTOCOL_EXAMPLES_INVALID')
        refs=self.reference(dataset_id,rubric_id)
        for sid in example_sample_ids:
            sample=next(s for s in dataset.samples if s.sample_id==sid)
            if sample.partition!='CALIBRATION': raise ValueError('HOLDOUT_EXAMPLE_PROHIBITED')
            if not refs[sid]['judgment']: raise ValueError('EXAMPLE_REQUIRES_HUMAN_REFERENCE')
            examples.append({'sample_id':sid,'sample':sample_input(sample),'judgment':refs[sid]['judgment'],
                             'annotation_ids':refs[sid]['annotation_ids']})
        from .evidence_judge import ALIAS_PROMPT
        prompt=ALIAS_PROMPT if citation_mode=='SHORT_IDS' else FRAGMENT_PROMPT if citation_mode=='FRAGMENT_IDS' else BASE_PROMPT
        if variant in {'J2','J3'}: prompt+=FRAGMENT_VERIFY_PROMPT if citation_mode=='FRAGMENT_IDS' else VERIFY_PROMPT
        if variant=='J3': prompt+=EXAMPLES_PROMPT
        if prompt_addendum.strip(): prompt+='\n'+prompt_addendum.strip()
        data={'dataset_id':dataset_id,'rubric_id':rubric_id,'name':name,'variant':variant,
            'change_hypothesis':change_hypothesis,'parent_protocol_id':parent_protocol_id,
            'provider_configuration':session.configuration.model_dump(),'prompt':prompt,'examples':examples,
            'evidence_input':'FROZEN_FRAGMENT_ALIASES_V1' if citation_mode=='SHORT_IDS' else 'FROZEN_FRAGMENT_CATALOG_V2' if citation_mode=='FRAGMENT_IDS' else 'FROZEN_DUAL_SCOPE_V1',
            'output_schema':'EXACT_FRAGMENT_ALIASES_V1' if citation_mode=='SHORT_IDS' else 'CALIBRATION_FRAGMENT_JUDGMENT_V2' if citation_mode=='FRAGMENT_IDS' else 'CALIBRATION_JUDGMENT_V1',
            'parser_version':'3' if citation_mode=='SHORT_IDS' else '2' if citation_mode=='FRAGMENT_IDS' else '1',
            'evidence_contract_version':'EVIDENCE_CONTRACT_V2'}
        if citation_mode=='SHORT_IDS':
            from .judge_jobs import component_identity
            from .judge_contract import VERSION
            data.update(wire_contract_version=VERSION,scoring_components=component_identity())
        changes=[]
        with self.store.transaction():
            if any(v.dataset_id==dataset_id for v in self.store.list('calibration_validations')): raise ValueError('CANDIDATE_LOCKED')
            if parent_protocol_id:
                parent=self.store.get('calibration_protocols',parent_protocol_id)
                if parent.dataset_id!=dataset_id or parent.rubric_id!=rubric_id: raise ValueError('RUBRIC_CHANGED_NEW_STUDY_REQUIRED')
                changes=[k for k in ('prompt','examples','provider_configuration','evidence_input','output_schema','parser_version','evidence_contract_version','wire_contract_version','scoring_components') if parent.model_dump().get(k)!=data.get(k)]
            return self.store.put('calibration_protocols',JudgeProtocolVersion(**data,declared_changes=changes,content_hash=digest(data)))

    def released(self,validation_id):
        return bool(self.store.get('calibration_validations',validation_id).released_at)

    def run_view(self,run_id,actor):
        run=self.store.get('calibration_runs',run_id)
        if run.partition=='HOLDOUT' and not self.released(run.validation_id): raise ValueError('HOLDOUT_LOCKED')
        # Do not reveal the machine results for an unsubmitted sample in this workspace.
        submitted={a.sample_id for a in self.store.list('calibration_annotations') if a.dataset_id==run.dataset_id and a.rubric_id==run.rubric_id and a.annotator_id==actor}
        visible=[s for s in run.sample_snapshot if s.sample_id in submitted]
        sample_ids={s.sample_id for s in visible}
        with self.store.transaction():
            self.store.put('calibration_access',CalibrationAccess(dataset_id=run.dataset_id,actor=actor,
                kind='MACHINE_VIEW',sample_ids=sorted(sample_ids),details={'run_id':run_id}))
        refs=self.reference(run.dataset_id,run.rubric_id) if run.partition=='CALIBRATION' else run.reference_snapshot
        return {'run':{k:getattr(run,k) for k in ('run_id','dataset_id','rubric_id','protocol_id','partition','status',
                    'repetitions','request_count','elapsed_ms','warnings')},
            'results':[r for r in run.results if r.sample_id in sample_ids],
            'metrics':metrics_with_slices(visible,[r for r in run.results if r.sample_id in sample_ids],refs,run.repetitions),
            'hidden_sample_count':len(run.sample_snapshot)-len(visible),'references':{k:v for k,v in refs.items() if k in sample_ids},
            'human_agreement':self.human_agreement(run.dataset_id,run.rubric_id)}

    async def run(self,dataset_id,rubric_id,protocol_id,provider_session_id,request_id,repetitions,budget,
                  partition='CALIBRATION',validation_id=None):
        request={'dataset_id':dataset_id,'rubric_id':rubric_id,'protocol_id':protocol_id,
            'provider_session_id':provider_session_id,'repetitions':repetitions,'budget':budget,
            'partition':partition,'validation_id':validation_id};request_hash=digest(request)
        with self.store.transaction():
            prior=next((r for r in self.store.list('calibration_runs') if r.request_id==request_id),None)
            if prior:
                if prior.request_hash!=request_hash: raise ValueError('IDEMPOTENCY_CONFLICT')
                return self.summary(prior)
            dataset=self.get_dataset(dataset_id);rubric=self.store.get('calibration_rubrics',rubric_id)
            protocol=self.store.get('calibration_protocols',protocol_id)
            if protocol.evidence_contract_version!='EVIDENCE_CONTRACT_V2':raise ValueError('SCORING_ENGINE_CHANGED_NEW_PROTOCOL_REQUIRED')
            if protocol.dataset_id!=dataset_id or protocol.rubric_id!=rubric_id: raise ValueError('PROTOCOL_SCOPE_MISMATCH')
            samples=[s for s in dataset.samples if s.partition==partition]
            if not samples: raise ValueError('PARTITION_EMPTY')
            if partition=='HOLDOUT':
                validation=self.store.get('calibration_validations',validation_id or '')
                if (validation.dataset_id!=dataset_id or validation.rubric_id!=rubric_id or validation.status!='RUNNING'
                    or protocol_id not in {validation.baseline_protocol_id,validation.candidate_protocol_id}): raise ValueError('HOLDOUT_LOCKED')
                refs=validation.reference_snapshot
            else:
                if validation_id: raise ValueError('INVALID_VALIDATION_PARTITION')
                if any(v.dataset_id==dataset_id for v in self.store.list('calibration_validations')): raise ValueError('CANDIDATE_LOCKED')
                refs=self.reference(dataset_id,rubric_id)
            session=self.providers.get(provider_session_id)
            if session.configuration!=protocol.provider_configuration: raise ValueError('PROVIDER_CONFIG_CHANGED')
            if session.text_connection_status!='READY': raise ProviderFailure('CONNECTION_NOT_VERIFIED')
            key=self.providers.credential(provider_session_id);judge_key=self.providers.judge_credential(provider_session_id)
            if len(samples)*repetitions>budget or budget>judge_budget_limit(session.configuration): raise ValueError('REQUEST_BUDGET_INVALID')
            run=CalibrationRun(request_id=request_id,request_hash=request_hash,dataset_id=dataset_id,
                rubric_id=rubric_id,protocol_id=protocol_id,partition=partition,validation_id=validation_id,
                repetitions=repetitions,budget=budget,dataset_hash=dataset.content_hash,sample_snapshot=samples,
                rubric_snapshot=rubric,protocol_snapshot=protocol,reference_snapshot=refs,
                warnings=['INITIAL_RUBRIC_UNVALIDATED','WORKFLOW_ISOLATION_ONLY','MODEL_BACKEND_REVISION_UNKNOWN',
                          'NO_AUTOMATIC_RETRIES','SOFTWARE_TESTS_ARE_NOT_RESEARCH'])
            lease=self.store.acquire_run_lease(run.run_id,'calibration_runs')
            try: self.store.put('calibration_runs',run)
            except BaseException: lease.close();raise
        provider=None;results=[];started=time.monotonic();status='COMPLETE';warnings=run.warnings
        try:
            provider=self.provider_factory(session.configuration,key,judge_key)
            for repetition in range(1,repetitions+1):
                for sample in samples:
                    results.append(await score_answer(provider,protocol,rubric,sample,repetition))
            if any(r.status!='SUCCESS' for r in results): status='PARTIAL'
        except asyncio.CancelledError: status='PARTIAL';warnings=[*warnings,'ACQUISITION_INTERRUPTED']
        except Exception: status='FAILED';warnings=[*warnings,'CALIBRATION_EXECUTION_FAILED']
        finally:
            if provider:
                try: await provider.close()
                except Exception: warnings=[*warnings,'PROVIDER_CLOSE_FAILED']
            finished=run.model_copy(update={'status':status,'finished_at':now(),'results':results,
                'metrics':metrics_with_slices(samples,results,refs,repetitions),'warnings':warnings,
                'request_count':provider.call_count if provider else 0,
                'provider_observations':provider.observations if provider else [],
                'elapsed_ms':round((time.monotonic()-started)*1000,2)})
            try:
                with self.store.transaction(): self.store.put('calibration_runs',finished)
            finally: lease.close()
        return self.summary(finished)

    @staticmethod
    def summary(run):
        return {k:getattr(run,k) for k in ('run_id','dataset_id','rubric_id','protocol_id','partition','status',
            'created_at','finished_at','repetitions','request_count','elapsed_ms','validation_id')}

    def compare(self,baseline_run_id,candidate_run_id,actor,internal=False):
        a=self.store.get('calibration_runs',baseline_run_id);b=self.store.get('calibration_runs',candidate_run_id)
        if a.status=='RUNNING' or b.status=='RUNNING': raise ValueError('RUN_NOT_SEALED')
        if not internal:
            views=[self.run_view(a.run_id,actor),self.run_view(b.run_id,actor)]
            if any(v['hidden_sample_count'] for v in views): raise ValueError('ANNOTATION_REQUIRED_BEFORE_RESULTS')
        reasons=[]
        if a.run_id==b.run_id: reasons.append('SAME_RUN')
        for field in ('dataset_id','dataset_hash','rubric_id','partition','repetitions'):
            if getattr(a,field)!=getattr(b,field): reasons.append(field.upper()+'_CHANGED')
        if a.rubric_snapshot.content_hash!=b.rubric_snapshot.content_hash: reasons.append('RUBRIC_CHANGED_NEW_ANNOTATION_REQUIRED')
        if [s.model_dump() for s in a.sample_snapshot]!=[s.model_dump() for s in b.sample_snapshot]: reasons.append('FROZEN_SAMPLES_CHANGED')
        if a.partition=='HOLDOUT' and a.validation_id!=b.validation_id: reasons.append('VALIDATION_CHANGED')
        if a.protocol_snapshot.evidence_contract_version!=b.protocol_snapshot.evidence_contract_version:reasons.append('EVIDENCE_CONTRACT_CHANGED')
        refs=a.reference_snapshot if a.partition=='HOLDOUT' else self.reference(a.dataset_id,a.rubric_id)
        refs_b=b.reference_snapshot if b.partition=='HOLDOUT' else self.reference(b.dataset_id,b.rubric_id)
        diffs=[{'field':k,'before':a.protocol_snapshot.model_dump().get(k),'after':b.protocol_snapshot.model_dump().get(k)}
               for k in ('prompt','examples','provider_configuration','evidence_input','output_schema','parser_version','evidence_contract_version')
               if a.protocol_snapshot.model_dump().get(k)!=b.protocol_snapshot.model_dump().get(k)]
        ma=metrics_with_slices(a.sample_snapshot,a.results,refs,a.repetitions)
        mb=metrics_with_slices(b.sample_snapshot,b.results,refs_b,b.repetitions)
        right={r['key']:r for r in mb['rows']}
        pairs=[{'key':r['key'],'sample_id':r['sample_id'],'before':r,'after':right.get(r['key'])} for r in ma['rows']]
        comparison=CalibrationComparison(dataset_id=a.dataset_id,baseline_run_id=a.run_id,candidate_run_id=b.run_id,
            comparable=not reasons,reasons=reasons,protocol_differences=diffs,single_component_change=len(diffs)==1,
            reference_snapshot=refs,metrics_before=ma,metrics_after=mb,pairs=pairs)
        with self.store.transaction(): return self.store.put('calibration_comparisons',comparison)

    def lock(self,dataset_id,rubric_id,baseline_protocol_id,candidate_protocol_id,reason,repetitions,request_budget,actor):
        dataset=self.get_dataset(dataset_id);protocols=[self.store.get('calibration_protocols',p) for p in (baseline_protocol_id,candidate_protocol_id)]
        if any(p.evidence_contract_version!='EVIDENCE_CONTRACT_V2' for p in protocols):raise ValueError('SCORING_ENGINE_CHANGED_NEW_PROTOCOL_REQUIRED')
        if baseline_protocol_id==candidate_protocol_id: raise ValueError('DISTINCT_PROTOCOLS_REQUIRED')
        if any(p.dataset_id!=dataset_id or p.rubric_id!=rubric_id for p in protocols): raise ValueError('RUBRIC_CHANGED_NEW_STUDY_REQUIRED')
        if not any(s.partition=='HOLDOUT' for s in dataset.samples): raise ValueError('HOLDOUT_EMPTY')
        minimum=2*repetitions*sum(s.partition=='HOLDOUT' for s in dataset.samples)
        if minimum>request_budget: raise ValueError('REQUEST_BUDGET_INVALID')
        if any(minimum//2>judge_budget_limit(p.provider_configuration) for p in protocols): raise ValueError('REQUEST_BUDGET_INVALID')
        with self.store.transaction():
            if any(v.dataset_id==dataset_id for v in self.store.list('calibration_validations')): raise ValueError('CANDIDATE_ALREADY_LOCKED')
            if any(a.dataset_id==dataset_id and a.kind in {'HOLDOUT_RELEASE','HOLDOUT_INVALIDATED'} for a in self.store.list('calibration_access')):
                raise ValueError('HOLDOUT_ALREADY_EXPOSED')
            # Both versions must have been run on calibration answers before locking.
            runs=self.store.list('calibration_runs')
            if any(not any(r.protocol_id==p.protocol_id and r.partition=='CALIBRATION' and r.status in {'COMPLETE','PARTIAL'} for r in runs) for p in protocols):
                raise ValueError('CALIBRATION_RUN_REQUIRED')
            return self.store.put('calibration_validations',CalibrationValidation(dataset_id=dataset_id,rubric_id=rubric_id,
                baseline_protocol_id=baseline_protocol_id,candidate_protocol_id=candidate_protocol_id,reason=reason,
                repetitions=repetitions,request_budget=request_budget,reference_snapshot=self.reference(dataset_id,rubric_id)))

    async def validate(self,validation_id,baseline_session_id,candidate_session_id,actor):
        with self.store.transaction():
            validation=self.store.get('calibration_validations',validation_id)
            if validation.status!='LOCKED': return validation
            count=sum(s.partition=='HOLDOUT' for s in self.get_dataset(validation.dataset_id).samples)*validation.repetitions
            for pid,sid in ((validation.baseline_protocol_id,baseline_session_id),(validation.candidate_protocol_id,candidate_session_id)):
                protocol=self.store.get('calibration_protocols',pid);session=self.providers.get(sid)
                self.providers.credential(sid);self.providers.judge_credential(sid)
                if session.configuration!=protocol.provider_configuration: raise ValueError('PROVIDER_CONFIG_CHANGED')
                if session.text_connection_status!='READY': raise ProviderFailure('CONNECTION_NOT_VERIFIED')
                if count>judge_budget_limit(session.configuration): raise ValueError('REQUEST_BUDGET_INVALID')
            lease=self.store.acquire_run_lease(validation_id,'calibration_validations')
            validation=validation.model_copy(update={'status':'RUNNING'})
            try: self.store.put('calibration_validations',validation)
            except BaseException: lease.close();raise
        runs=[];comparison=None;status='COMPLETE'
        try:
            count=sum(s.partition=='HOLDOUT' for s in self.get_dataset(validation.dataset_id).samples)*validation.repetitions
            for pid,sid in ((validation.baseline_protocol_id,baseline_session_id),(validation.candidate_protocol_id,candidate_session_id)):
                run=await self.run(validation.dataset_id,validation.rubric_id,pid,sid,
                    f'validation-{validation_id}-{pid}',validation.repetitions,count,partition='HOLDOUT',validation_id=validation_id)
                runs.append(run['run_id'])
                if run['status']=='FAILED': status='FAILED'
            comparison=self.compare(*runs,actor,internal=True)
        except (Exception,asyncio.CancelledError): status='FAILED'
        finally:
            released=now()
            final=validation.model_copy(update={'status':status,'run_ids':runs,
                'comparison_id':comparison.comparison_id if comparison else None,'released_at':released})
            try:
                with self.store.transaction():
                    self.store.put('calibration_validations',final)
                    self.store.put('calibration_access',CalibrationAccess(dataset_id=validation.dataset_id,actor=actor,
                        kind='HOLDOUT_RELEASE',sample_ids=[s.sample_id for s in self.get_dataset(validation.dataset_id).samples if s.partition=='HOLDOUT'],
                        details={'validation_id':validation_id,'status':status,'release_time':released}))
            finally: lease.close()
        return final

    def comparison_view(self,comparison_id,actor):
        comparison=self.store.get('calibration_comparisons',comparison_id)
        for rid in (comparison.baseline_run_id,comparison.candidate_run_id):
            view=self.run_view(rid,actor)
            if view['hidden_sample_count']: raise ValueError('ANNOTATION_REQUIRED_BEFORE_RESULTS')
        return comparison

    def hypothesis(self,dataset_id,sample_id,run_id,actor,causes,reason):
        from .calibration_models import CalibrationHypothesis
        if set(causes)-set(CAUSES): raise ValueError('HYPOTHESIS_CAUSE_INVALID')
        view=self.run_view(run_id,actor)
        if view['run']['dataset_id']!=dataset_id or sample_id not in {r.sample_id for r in view['results']}:
            raise ValueError('HYPOTHESIS_SAMPLE_INVALID')
        with self.store.transaction(): return self.store.put('calibration_hypotheses',CalibrationHypothesis(
            dataset_id=dataset_id,sample_id=sample_id,run_id=run_id,actor=actor,causes=causes,reason=reason))

    def issue_access(self,run_id,sample_id,actor):
        view=self.run_view(run_id,actor)
        if sample_id not in {r.sample_id for r in view['results']}:
            raise ValueError('ANNOTATION_REQUIRED_BEFORE_RESULTS')
        return view

    def issue_source(self,run_id,case_id,actor,source_type='RETRIEVAL_RUN',source_id=None):
        from .calibration_issue_workflow import IssueWorkflow
        return IssueWorkflow(self).source(run_id,case_id,actor,source_type,source_id)

    def create_issue(self,dataset_id,sample_id,run_id,actor,title,layer,owner,description,**details):
        from .calibration_issue_workflow import IssueWorkflow
        return IssueWorkflow(self).create(dataset_id,sample_id,run_id,actor,title,layer,owner,description,**details)

    def issue_events(self,issue_id):
        from .calibration_issue_workflow import IssueWorkflow
        return IssueWorkflow(self).events(issue_id)

    def issues_view(self,dataset_id,actor,source_type=None,run_id=None):
        from .calibration_issue_workflow import IssueWorkflow
        return IssueWorkflow(self).view(dataset_id,actor,source_type,run_id)

    def update_issue(self,issue_id,actor,to_status,note,previous_event_id=None,change_summary='',verification_run_id=None,outcome=None,**details):
        from .calibration_issue_workflow import IssueWorkflow
        return IssueWorkflow(self).update(issue_id,actor,to_status,note,previous_event_id,change_summary,verification_run_id,outcome,**details)

    def conclude(self,comparison_id,decision,reason,actor,validation_id=None):
        comparison=self.comparison_view(comparison_id,actor)
        validation=self.store.get('calibration_validations',validation_id) if validation_id else None
        if validation and (validation.comparison_id!=comparison_id or not validation.released_at): raise ValueError('VALIDATION_NOT_COMPLETE')
        if decision=='ADOPT' and (not validation or validation.status!='COMPLETE' or not comparison.comparable):
            raise ValueError('ADOPTION_REQUIRES_FINAL_VALIDATION')
        refs=comparison.reference_snapshot;sample_ids={s.sample_id for s in self.get_dataset(comparison.dataset_id).samples}
        complete=all((refs.get(sid,{}).get('judgment') or {}).get('verdict') in {'PASS','FAIL'} for sid in sample_ids)
        restrictions=adoption_restrictions(comparison.model_dump(mode='json'))
        state='PENDING'
        if complete and validation and validation.status=='COMPLETE' and comparison.comparable and not restrictions:
            state='COMPLETED_WITH_SINGLE_ANNOTATOR' if any(refs[sid]['state']=='SINGLE' for sid in sample_ids) else 'COMPLETED_WITH_ADJUDICATED_REFERENCE'
        if decision=='ADOPT' and not complete: raise ValueError('INDEPENDENT_HUMAN_REFERENCE_REQUIRED')
        if decision=='ADOPT' and restrictions: raise ValueError('ADOPTION_REQUIRES_COMPLETE_EVALUATION')
        dataset=self.get_dataset(comparison.dataset_id)
        report={'dataset':dataset.model_dump(mode='json'),'comparison':comparison.model_dump(mode='json'),
            'runs':[self.store.get('calibration_runs',r).model_dump(mode='json') for r in (comparison.baseline_run_id,comparison.candidate_run_id)],
            'validation':validation.model_dump(mode='json') if validation else None,
            'adoption_gate':{'eligible':state!='PENDING','restrictions':restrictions,
                'human_reference_complete':complete,'full_scope_decisions_required':True},
            'human_agreement':self.human_agreement(dataset.dataset_id,self.store.get('calibration_runs',comparison.baseline_run_id).rubric_id),
            'hypotheses':[h.model_dump(mode='json') for h in self.store.list('calibration_hypotheses') if h.dataset_id==dataset.dataset_id],
            'issues':[{'issue':i.model_dump(mode='json'),'events':[e.model_dump(mode='json') for e in self.issue_events(i.issue_id)]}
                      for i in self.store.list('calibration_issues') if i.dataset_id==dataset.dataset_id],
            'annotations':[a.model_dump(mode='json') for a in self.store.list('calibration_annotations') if a.dataset_id==dataset.dataset_id],
            'adjudications':[a.model_dump(mode='json') for a in self.store.list('calibration_adjudications') if a.dataset_id==dataset.dataset_id],
            'access_records':[a.model_dump(mode='json') for a in self.store.list('calibration_access') if a.dataset_id==dataset.dataset_id],
            'limitations':['软件验收不证明 Judge 已校准；没有独立人工参照时研究待完成。',
                '首版只提供工作流隔离，开发者可读本地数据；不是第三方盲测。',
                '植入错误的诊断样本不代表自然错误率；比例显示实际分母；单轮差异不证明因果。',
                '若保留结果用于后续修改，需增加新保留样本。']}
        if restrictions:
            report['limitations'].append('冻结验证范围仍有未判定、执行失败或 ID 对账异常；不能采用为已验证评分方案：'+', '.join(restrictions))
        if decision=='REVISE' and validation:
            with self.store.transaction():
                self.store.put('calibration_access',CalibrationAccess(dataset_id=dataset.dataset_id,actor=actor,
                    kind='HOLDOUT_INVALIDATED',details={'reason':reason,'validation_id':validation_id}))
        with self.store.transaction(): return self.store.put('calibration_conclusions',CalibrationConclusion(
            dataset_id=dataset.dataset_id,comparison_id=comparison_id,validation_id=validation_id,decision=decision,
            reason=reason,research_status=state,report_snapshot=report))

    def history(self):
        return {'datasets':[{k:getattr(d,k) for k in ('dataset_id','name','created_at','content_hash')} |
            {'calibration_count':sum(s.partition=='CALIBRATION' for s in d.samples),'holdout_count':sum(s.partition=='HOLDOUT' for s in d.samples)}
            for d in self.store.list('calibration_datasets')], 'rubrics':self.store.list('calibration_rubrics'),
            'protocols':self.store.list('calibration_protocols'), 'runs':[self.summary(r) for r in self.store.list('calibration_runs')],
            'validations':self.store.list('calibration_validations'),
            'conclusions':[{k:getattr(c,k) for k in ('conclusion_id','dataset_id','comparison_id','validation_id','decision','research_status','created_at','reason')}
                           for c in self.store.list('calibration_conclusions')]}

    def export(self,conclusion_id):
        c=self.store.get('calibration_conclusions',conclusion_id);report=c.model_dump(mode='json')
        data=c.report_snapshot;comparison=data['comparison']
        lines=['# Agent Eval 评测校准报告',f'\n决策：{c.decision}。研究状态：{c.research_status}。',
            f'\n理由：{c.reason}',f"\n样本集：{data['dataset']['name']}（{data['dataset']['content_hash']}）",
            f"\n优先指标：{data['dataset']['priority_metric']}。可接受代价：{data['dataset']['acceptable_cost']}。",
            f"\n可比较：{comparison['comparable']}。原因：{', '.join(comparison['reasons']) or '冻结条件一致'}。",
            '\n| 指标 | 基线 | 候选 |','| --- | --- | --- |']
        for key,label in [('agreement','人机一致率'),('false_pass','错误放行率'),('false_fail','错误拒绝率'),('critical_miss','关键错误漏检'),('coverage','评测覆盖率')]:
            def display(side):
                v=comparison[side][key];return f"{v['numerator']}/{v['denominator']}（{v['value']:.1%}）" if v['value'] is not None else '0/0（不可计算）'
            lines.append(f"| {label} | {display('metrics_before')} | {display('metrics_after')} |")
        for side in ('metrics_before','metrics_after'):
            lines.extend([f'\n{side} 执行健康：{json.dumps(comparison[side]["health"],ensure_ascii=False)}',
                f'\n{side} 请求及 usage：{json.dumps(comparison[side]["cost"],ensure_ascii=False)}'])
        lines.extend(['\n## 逐项分歧','\n| 样本／重复 | 人工 | 基线 | 候选 |','| --- | --- | --- |'])
        for pair in comparison['pairs']:
            a=pair['before'];b=pair['after'] or {}
            lines.append(f"| {pair['key']} | {a['human'] or '未裁决'} | {a['machine'] or a['execution_status']} | {b.get('machine') or b.get('execution_status','缺失')} |")
        lines.extend(['\n## 协议差异',f"\n单组成部分变化：{comparison['single_component_change']}；因果归因：未建立。",
            '\n```json',json.dumps(comparison['protocol_differences'],ensure_ascii=False,indent=2),'```',
            '\n## 证据与局限',*['\n- '+x for x in data['limitations']],
            '\n完整冻结样本、双层政策、逐维判定、引用、版本、标注参照、分场景指标和解封记录见配套 JSON。'])
        return {'markdown':'\n'.join(lines)+'\n','json':report}
