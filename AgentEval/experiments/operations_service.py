"""Control/data plane: frozen imports, scope review, statistics and job dispatch."""
import asyncio
import csv
import io
import json
import os
import random
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from .canonical import digest
from .models import now
from .operations_models import DomainVersion,EvidenceBatch,InferenceJob,OperationsReview,SamplingPlan,DailyPlan
from .evidence_ingest import parse,project,FIELDS
from .evidence_judge import ALIAS_PROMPT
from evaluation.calibration import RUBRIC_TEMPLATE,validate_rubric

class OperationsService:
    def __init__(self,experiments):
        self.experiments=experiments;self.store=experiments.store;self.providers=experiments.providers
        self.tasks={}

    def domains(self):
        values={}
        for item in self.store.list('operation_domains'):
            if item.domain_id not in values or values[item.domain_id].version<item.version:values[item.domain_id]=item
        return sorted(values.values(),key=lambda v:v.domain_id)

    def domain(self,identifier):
        value=next((v for v in self.domains() if v.domain_id==identifier),None)
        if value is None:raise ValueError('DOMAIN_NOT_FOUND')
        return value

    def save_domain(self,**data):
        definition=deepcopy(data.pop('rubric',None) or RUBRIC_TEMPLATE);validate_rubric(definition)
        data['judge_prompt']=data.get('judge_prompt') or ALIAS_PROMPT
        data['evidence_contract_version']='EVIDENCE_CONTRACT_V2'
        from .judge_jobs import component_identity
        from .judge_contract import VERSION
        data.update(wire_contract_version=VERSION,scoring_components=component_identity())
        with self.store.transaction():
            versions=[v.version for v in self.store.list('operation_domains') if v.domain_id==data['domain_id']]
            value=DomainVersion(**data,version=max(versions,default=0)+1,rubric=definition,content_hash=digest({**data,'rubric':definition}))
            return self.store.put('operation_domains',value)

    def from_rag(self,run_id):
        from .retrieval_models import RetrievalCase
        from .trusted_results import source_identity
        run=self.store.get('retrieval_runs',run_id)
        if run.status=='RUNNING':raise ValueError('SOURCE_RUN_UNAVAILABLE')
        rows=[];by_case={c['case_id']:c for c in run.controls['eval_set_snapshot']['cases']}
        for sid in run.execution_order:
            matches=[a for a in run.answer_results if a.case_id==sid]
            retrieval=[r for r in run.case_results if r['case_id']==sid]
            if len(matches)!=1 or len(retrieval)!=1:raise ValueError('RESULT_RECONCILIATION_INCOMPLETE')
            case=by_case[sid];answer=matches[0];row=retrieval[0]
            rows.append({'sample_id':sid,'question':case['query'],'answer':answer.turn_evidence[-1].response if answer.turn_evidence else '',
                'context':case.get('context',[]),'retrieved_evidence':row.get('results',[]),
                'reference_policy':[{'evidence_id':d['document_id'],**d} for d in run.controls['knowledge_snapshot']['documents']],
                'reference_complete':case.get('reference_complete'),'source_type':source_identity(RetrievalCase.model_validate(case)),
                'family_id':case.get('group_id') or sid,'source_run_id':run_id,'source_run_hash':digest(run.model_dump(mode='json')),
                **{k:v for k,v in case.get('evidence_context',{}).items() if k in {'conversation_id','turn_id','object_ids','question_time','question_timezone','business_domain'}}})
        return {'records':rows,'source_run_id':run_id,'reference_source':'ORIGINAL_FROZEN_KNOWLEDGE_SNAPSHOT','answer_regenerated':False}

    def preview(self,domain_id,content,format='json',mapping=None,history_mode='NECESSARY'):
        raw=parse(content,format);domain=self.domain(domain_id)
        rows,processing=project(raw,mapping or {},domain,history_mode)
        return {'records':rows,'processing':processing,'source_fields':sorted({k for r in raw for k in r}),
            'target_fields':FIELDS,'domain_version':domain.version,'profile_id':domain.profile_id,
            'preview_hash':digest({'raw':raw,'records':rows,'profile':domain.profile_id,'mapping':mapping or {}})}

    def save_batch(self,domain_id,content,format,mapping,history_mode,name,confirmed_by,confirmation_reason,decisions,parent_batch_id=None,preview_hash=None):
        if not confirmed_by.strip() or not confirmation_reason.strip():raise ValueError('SCOPE_CONFIRMATION_REQUIRED')
        value=self.preview(domain_id,content,format,mapping,history_mode)
        if preview_hash!=value['preview_hash']:raise ValueError('PREVIEW_CHANGED_REVIEW_AGAIN')
        choices={v['sample_id']:v for v in decisions}
        if len(choices)!=len(decisions) or set(choices)!={v['sample_id'] for v in value['records']}:raise ValueError('SCOPE_CONFIRMATION_REQUIRED')
        for record in value['records']:
            choice=choices[record['sample_id']]
            if choice.get('state') not in {'INCLUDE','EXCLUDE'} or not str(choice.get('reason','')).strip():raise ValueError('SCOPE_CONFIRMATION_REQUIRED')
            record['scope']={'state':choice['state'],'reason':choice['reason'],'confirmed_by':confirmed_by}
            if 'reference_complete' in choice:
                if choice['reference_complete'] not in (True,False,None):raise ValueError('REFERENCE_CONFIRMATION_INVALID')
                record['reference_complete']=choice['reference_complete']
            if record['reference_complete'] is True and not record['reference_policy']:raise ValueError('REFERENCE_POLICY_REQUIRED')
            record['family_id']=str(choice.get('family_id') or record['family_id'])
            record['error_type']=str(choice.get('error_type') or record['error_type'])
        if parent_batch_id:
            parent=self.store.get('evidence_batches',parent_batch_id)
            if parent.domain_id!=domain_id:raise ValueError('DOMAIN_SCOPE_MISMATCH')
            # Data repair may change evidence/scope, not silently rewrite original answers.
            previous={r['sample_id']:r for r in parent.records}
            if set(previous)!={r['sample_id'] for r in value['records']}:raise ValueError('REPAIR_SAMPLE_IDENTITY_CHANGED')
            if any((previous[r['sample_id']]['question'],previous[r['sample_id']]['answer'])!=(r['question'],r['answer']) for r in value['records']):raise ValueError('REPAIR_FROZEN_ANSWER_CHANGED')
        raw=parse(content,format)
        batch=EvidenceBatch(domain_id=domain_id,profile_id=value['profile_id'],name=name,parent_batch_id=parent_batch_id,
            raw_records=raw,records=value['records'],mapping=mapping,processing=value['processing'],confirmed_by=confirmed_by,
            confirmation_reason=confirmation_reason,content_hash=digest({'raw':raw,'projection':value,'decisions':decisions}))
        with self.store.transaction():return self.store.put('evidence_batches',batch)

    def create_job(self,batch_id,provider_session_id,request_id,window=None,resumed_from_job_id=None):
        batch=self.store.get('evidence_batches',batch_id);profile=self.store.get('operation_domains',batch.profile_id)
        session=self.providers.get(provider_session_id)
        self.providers.credential(provider_session_id)
        if session.text_connection_status!='READY':raise ValueError('CONNECTION_NOT_VERIFIED')
        self.providers.judge_credential(provider_session_id)
        expected=[r['sample_id'] for r in batch.records if r['scope']['state']=='INCLUDE']
        if not expected:raise ValueError('EVALUATION_PARTITION_EMPTY')
        if resumed_from_job_id:
            parent=self.store.get('inference_jobs',resumed_from_job_id)
            if parent.batch_id!=batch_id:raise ValueError('DOMAIN_SCOPE_MISMATCH')
        with self.store.transaction():
            previous=next((j for j in self.store.list('inference_jobs') if j.domain_id==batch.domain_id and j.request_id==request_id),None)
            if previous:
                if (previous.batch_id,previous.provider_session_id,previous.window)!=(batch_id,provider_session_id,window or {}):raise ValueError('IDEMPOTENCY_CONFLICT')
                return previous
            job=InferenceJob(domain_id=batch.domain_id,batch_id=batch_id,profile_id=profile.profile_id,request_id=request_id,
                provider_session_id=provider_session_id,provider_configuration=session.configuration.model_dump(mode='json'),
                rule_snapshot=profile.model_dump(mode='json'),expected_ids=expected,window=window or {},resumed_from_job_id=resumed_from_job_id)
            return self.store.put('inference_jobs',job)

    async def dispatch(self,job_id,retry=False):
        job=self.store.get('inference_jobs',job_id)
        if retry and job.attempt>=job.rule_snapshot['max_attempts']:raise ValueError('MAX_ATTEMPTS_REACHED')
        if job.status=='COMPLETE' and not retry:return job
        if job_id in self.tasks and not self.tasks[job_id].done():return job
        if retry:
            current=self.view(job_id)
            if all(r['evaluation_state'] not in {'EXECUTION_FAILED','NOT_RUN'} for r in current['rows']):return job
            with self.store.transaction():
                job=self.store.put('inference_jobs',job.model_copy(update={'status':'QUEUED'}))
        # A durable FIFO per domain; another domain has a separate process/lease.
        peers=self.store.list('inference_jobs')
        if any(p.domain_id==job.domain_id and p.job_id!=job.job_id and
               (p.status=='RUNNING' or p.status=='QUEUED' and p.created_at<job.created_at) for p in peers):return job
        # Explicit manual retry; ordinary polling never repeats completed calls.
        if job.status not in {'QUEUED','WAITING_CREDENTIALS'} and not retry:return job
        session=self.providers.get(job.provider_session_id)
        key=self.providers.credential(job.provider_session_id);judge_key=self.providers.judge_credential(job.provider_session_id)
        if session.configuration.model_dump(mode='json')!=job.provider_configuration:raise ValueError('PROVIDER_CONFIG_CHANGED')
        async def launch():
            from .worker_dispatch import launch_worker
            code=await launch_worker(self.store.root,job_id,key,judge_key)
            self.ensure_review_queue(self.store.get('inference_jobs',job_id))
            return code
        task=asyncio.create_task(launch());self.tasks[job_id]=task
        return job

    def cancel(self,job_id):
        with self.store.transaction():
            job=self.store.get('inference_jobs',job_id)
            if job.status in {'COMPLETE','CANCELLED'}:return job
            return self.store.put('inference_jobs',job.model_copy(update={'status':'CANCEL_REQUESTED'}))

    def view(self,job_id):
        job=self.store.get('inference_jobs',job_id);batch=self.store.get('evidence_batches',job.batch_id)
        events=[e for e in self.store.list('inference_events') if e.job_id==job_id]
        reviews=sorted([r for r in self.store.list('operations_reviews') if r.job_id==job_id],key=lambda r:r.revision)
        grouped={sid:[] for sid in job.expected_ids};unexpected=[]
        for event in events:
            if event.sample_id in grouped:grouped[event.sample_id].append(event)
            else:unexpected.append(event.sample_id)
        latest={};duplicates=[]
        for sid,items in grouped.items():
            if not items:continue
            attempt=max(i.attempt for i in items);current=[i for i in items if i.attempt==attempt]
            if len(current)!=1:duplicates.append(sid)
            else:latest[sid]=current[0]
        states={sid:e.evaluation_state for sid,e in latest.items()}
        for review in reviews:
            if review.sample_id in states:states[review.sample_id]=review.evaluation_state
        for sid in job.expected_ids:
            if sid not in states:states[sid]='NOT_RUN' if sid not in duplicates else 'EVIDENCE_INSUFFICIENT'
        counts=Counter(states.values());binary=counts['PASS']+counts['FAIL'];denominator=len(job.expected_ids)-counts['NOT_APPLICABLE']
        missing=[sid for sid in job.expected_ids if sid not in latest]
        complete=not missing and not duplicates and not unexpected and job.status=='COMPLETE'
        rows=[]
        by_record={r['sample_id']:r for r in batch.records}
        for sid in job.expected_ids:
            e=latest.get(sid);review=next((r for r in reversed(reviews) if r.sample_id==sid),None)
            rows.append({'record':by_record[sid],'event':e,'review':review,'evaluation_state':states[sid]})
        return {'job':job,'batch':batch,'rows':rows,'events':events,'reviews':reviews,
            'sampling_plans':sorted([p for p in self.store.list('sampling_plans') if p.job_id==job_id],key=lambda p:p.created_at),
            'summary':{'complete':complete,'expected_count':len(job.expected_ids),'missing_ids':missing,'duplicate_ids':duplicates,'unexpected_ids':unexpected,
                'counts':dict(counts),'coverage':{'numerator':binary,'denominator':denominator,'value':binary/denominator if denominator else None},
                'pass_rate':{'numerator':counts['PASS'],'denominator':binary,'value':counts['PASS']/binary if binary and complete else None},
                'completed_subset_pass_rate':counts['PASS']/binary if binary else None,'publication_status':'COMPLETE' if complete else 'INCOMPLETE',
                'raw_count':batch.processing['raw_count'],'deduplicated_count':len(batch.records),
                'excluded':[{'sample_id':r['sample_id'],'reason':r['scope']['reason']} for r in batch.records if r['scope']['state']=='EXCLUDE'],
                'actual_requests':None if job.uncertain_delivery_attempts else sum(e.request_count for e in events),
                'known_request_minimum':sum(e.request_count for e in events),'request_accounting_complete':not job.uncertain_delivery_attempts,
                'uncertain_delivery_attempts':job.uncertain_delivery_attempts,'attempt_count':job.attempt,
                'independent_samples':len(job.expected_ids),'human_review_count':len({r.sample_id for r in reviews}),
                'human_disagreements':sum(row['review'].evaluation_state!=row['event'].evaluation_state for row in rows if row['review'] and row['event']),
                'calibration_status':'MANUAL_REVIEW_IS_NOT_INDEPENDENT_JUDGE_VALIDATION','currency_cost':None}}

    def review(self,job_id,sample_id,evaluation_state,reason,actor):
        view=self.view(job_id)
        if not actor.strip() or not reason.strip():raise ValueError('REVIEW_REASON_REQUIRED')
        selected=next((r for r in view['rows'] if r['record']['sample_id']==sample_id),None)
        if evaluation_state=='PASS' and (not selected or not selected['event'] or selected['event'].evaluation_state in {'EXECUTION_FAILED','NOT_RUN'} or (selected['event'].input_package or {}).get('check',{}).get('status')!='PASS'):
            raise ValueError('REVIEW_EVIDENCE_REQUIRED')
        if not any(r['record']['sample_id']==sample_id and r['event'] for r in view['rows']):raise ValueError('REVIEW_RESULT_MISSING')
        with self.store.transaction():
            prior=[r for r in self.store.list('operations_reviews') if r.job_id==job_id]
            value=OperationsReview(job_id=job_id,sample_id=sample_id,evaluation_state=evaluation_state,reason=reason,actor=actor,
                revision=max([r.revision for r in prior],default=0)+1)
            return self.store.put('operations_reviews',value)

    def ensure_review_queue(self,job):
        if job.status not in {'COMPLETE','PARTIAL','CANCELLED'}:return
        seed=digest([job.job_id,job.attempt,'AUTO_REVIEW'])
        if not any(p.job_id==job.job_id and p.seed==seed for p in self.store.list('sampling_plans')):
            self.sample(job.job_id,min(5,len(job.expected_ids)),seed)

    def sample(self,job_id,count,seed):
        view=self.view(job_id);ids=list(view['job'].expected_ids);rng=random.Random(seed)
        random_ids=set(rng.sample(ids,min(count,len(ids))));selections=[]
        for row in view['rows']:
            sid=row['record']['sample_id'];reasons=[]
            if sid in random_ids:reasons.append('RANDOM')
            if row['evaluation_state']!='PASS':reasons.append('FAILURE_OR_ABSTENTION')
            if row['review'] and row['event'] and row['review'].evaluation_state!=row['event'].evaluation_state:reasons.append('HUMAN_DISAGREEMENT')
            judgment=(row['event'].judgment or {}) if row['event'] else {}
            if judgment.get('critical_errors'):reasons.append('CRITICAL_ERROR')
            if any(d.get('score')==1 for d in judgment.get('dimensions',{}).values()):reasons.append('BOUNDARY_SCORE')
            if reasons:selections.append({'sample_id':sid,'reasons':reasons})
        plan=SamplingPlan(job_id=job_id,seed=seed,random_count=len(random_ids),source_count=len(ids),selections=selections)
        with self.store.transaction():return self.store.put('sampling_plans',plan)

    def calibration_dataset(self,plan_id,actor):
        from .calibration_service import CalibrationService
        plan=self.store.get('sampling_plans',plan_id);view=self.view(plan.job_id);wanted={v['sample_id'] for v in plan.selections}
        samples=[]
        for row in view['rows']:
            r=row['record']
            if r['sample_id'] not in wanted or not r['answer'].strip() or not r['question']:continue
            samples.append({'sample_id':r['sample_id'],'group_id':r['family_id'],'partition':'CALIBRATION','question':r['question'],
                'answer':r['answer'],'context':r['context'],'reference_policy':[{k:v for k,v in e.items() if k!='metadata'} for e in r['reference_policy']],
                'retrieved_evidence':[{k:v for k,v in e.items() if k!='metadata'} for e in r['retrieved_evidence']],
                'reference_complete':r['reference_complete'] is True,'origin':'UNKNOWN','prior_machine_exposure':True,
                'machine_exposed_actors':[actor],'creator_seen_content':True,
                'provenance':{'scenario_rules':r['scenario_rules'],'evidence_context':r['evidence_context'],'import_batch_id':view['batch'].batch_id,
                    'job_id':plan.job_id,'sampling_plan_id':plan_id,'sampling_source_count':plan.source_count,'machine_results_not_independent_labels':True}})
        cal=getattr(self.experiments,'calibration',None) or CalibrationService(self.experiments)
        return cal.create_dataset('抽样复核 '+plan_id[:8],samples,[],True,'错误放行、错误拒绝与弃判','记录真实请求成本，不将定向抽样冒充总体')

    def save_schedule(self,**data):
        try:ZoneInfo(data['timezone'])
        except (KeyError,ValueError):raise ValueError('SCHEDULE_TIMEZONE_INVALID') from None
        batch=self.store.get('evidence_batches',data['batch_id'])
        if batch.domain_id!=data['domain_id']:raise ValueError('DOMAIN_SCOPE_MISMATCH')
        with self.store.transaction():
            previous_id=data.get('replaces_plan_id')
            if not previous_id:
                active=next((p for p in self.schedules() if p.enabled and (p.domain_id,p.timezone,p.hour,p.minute)==
                    (data['domain_id'],data['timezone'],data['hour'],data.get('minute',0))),None)
                if active:
                    if all(getattr(active,k)==v for k,v in data.items() if k!='replaces_plan_id'):return active
                    previous_id=active.plan_id;data['replaces_plan_id']=previous_id
            if previous_id:
                old=self.store.get('daily_plans',previous_id)
                if old.domain_id!=data['domain_id']:raise ValueError('DOMAIN_SCOPE_MISMATCH')
                if any(p.replaces_plan_id==previous_id for p in self.store.list('daily_plans')):raise ValueError('SCHEDULE_REVISION_CONFLICT')
                data['revision']=old.revision+1
            value=DailyPlan(**data)
            return self.store.put('daily_plans',value)

    def schedules(self):
        plans=self.store.list('daily_plans');replaced={p.replaces_plan_id for p in plans if p.replaces_plan_id}
        return [p for p in plans if p.plan_id not in replaced]

    async def tick(self,at=None):
        at=at or datetime.now(timezone.utc)
        for job in self.store.list('inference_jobs'):
            if job.window.get('kind')=='MEMORY_ONLY_RELEASE_HANDOFF':continue
            if job.window.get('kind')=='MEMORY_ONLY_RELEASE_TRANSFER':
                if job.window.get('sender_release')!=os.getenv('AGENTEVAL_RELEASE_ID'):continue
            self.ensure_review_queue(job)
            if job.status in {'RUNNING','CANCEL_REQUESTED'}:
                try:lease=self.store.acquire_run_lease(job.job_id,'inference_jobs')
                except BlockingIOError:continue
                try:
                    with self.store.transaction():
                        current=self.store.get('inference_jobs',job.job_id)
                        if current.status in {'RUNNING','CANCEL_REQUESTED'}:
                            self.store.put('inference_jobs',current.model_copy(update={'status':'CANCELLED' if current.status=='CANCEL_REQUESTED' else 'PARTIAL','last_error':'WORKER_INTERRUPTED_CALL_DELIVERY_UNKNOWN','finished_at':now(),
                                'uncertain_delivery_attempts':sorted(set(current.uncertain_delivery_attempts+([current.attempt] if current.attempt else [])))}))
                finally:lease.close()
            elif job.status in {'QUEUED','WAITING_CREDENTIALS'}:
                try:await self.dispatch(job.job_id)
                except (RuntimeError,FileNotFoundError):
                    with self.store.transaction():
                        current=self.store.get('inference_jobs',job.job_id)
                        if current.status in {'QUEUED','WAITING_CREDENTIALS'}:self.store.put('inference_jobs',current.model_copy(update={'status':'WAITING_CREDENTIALS','last_error':'CREDENTIAL_UNAVAILABLE'}))
        for plan in self.schedules():
            if not plan.enabled:continue
            local=at.astimezone(ZoneInfo(plan.timezone));end=local.replace(hour=plan.hour,minute=plan.minute,second=0,microsecond=0)
            if local<end:continue
            start=end-timedelta(days=1)
            window={'start':start.isoformat(),'end':end.isoformat(),'timezone':plan.timezone,
                'batch_snapshot':plan.batch_id,'late_policy':plan.late_policy,'source_kind':'FROZEN_BATCH_REPLAY','plan_id':plan.plan_id}
            request_id='daily_'+digest([plan.plan_id,end.isoformat()])[:40]
            try:
                job=self.create_job(plan.batch_id,plan.provider_session_id,request_id,window)
                await self.dispatch(job.job_id)
            except (ValueError,RuntimeError,FileNotFoundError):
                # Missing credentials are visible on plan health; never substitute server keys.
                continue

    def schedule_health(self):
        values=[]
        for p in self.schedules():
            try:
                self.providers.credential(p.provider_session_id);health='READY'
            except (RuntimeError,FileNotFoundError):health='WAITING_CREDENTIALS'
            windows=[j.window.get('end') for j in self.store.list('inference_jobs') if j.window.get('plan_id')==p.plan_id]
            watermark=max(windows) if windows else None
            end=datetime.now(timezone.utc).astimezone(ZoneInfo(p.timezone)).replace(hour=p.hour,minute=p.minute,second=0,microsecond=0)
            missed=max(0,(end-datetime.fromisoformat(watermark)).days-1) if watermark else 0
            values.append({'plan':p,'health':health,'input_kind':'FROZEN_BATCH_REPLAY','last_window_end':watermark,'missed_window_count':missed,
                'source_note':'运行指定批次快照；新增或迟到日志需保存新批次并更新计划，不自动假设有数仓增量。'})
        return values

    def compare(self,left_id,right_id):
        a=self.view(left_id);b=self.view(right_id)
        if a['job'].domain_id!=b['job'].domain_id:raise ValueError('DOMAIN_SCOPE_MISMATCH')
        flags=[]
        if a['batch'].content_hash!=b['batch'].content_hash:flags.append('EVIDENCE_OR_SCOPE_CHANGED')
        if a['job'].rule_snapshot!=b['job'].rule_snapshot:flags.append('RUBRIC_OR_JUDGE_PROMPT_CHANGED')
        if a['job'].provider_configuration!=b['job'].provider_configuration:flags.append('JUDGE_CONFIGURATION_CHANGED')
        if not a['summary']['complete'] or not b['summary']['complete']:flags.append('RESULT_RECONCILIATION_INCOMPLETE')
        aa={r['record']['sample_id']:r for r in a['rows']};bb={r['record']['sample_id']:r for r in b['rows']};pairs=[];families={}
        for sid in sorted(set(aa)|set(bb)):
            l=aa.get(sid);r=bb.get(sid);x=l['evaluation_state'] if l else None;y=r['evaluation_state'] if r else None
            comparable=not flags and x in {'PASS','FAIL'} and y in {'PASS','FAIL'}
            state='IMPROVED' if comparable and (x,y)==('FAIL','PASS') else 'REGRESSED' if comparable and (x,y)==('PASS','FAIL') else 'STILL_FAIL' if comparable and y=='FAIL' else 'UNCHANGED' if comparable else 'NOT_COMPARABLE'
            record=(r or l)['record'];family=record['family_id'];families.setdefault(family,Counter())[state]+=1
            pairs.append({'sample_id':sid,'before':x,'after':y,'transition':state,'family_id':family})
        return {'before':a['summary'],'after':b['summary'],'pairs':pairs,'families':{k:dict(v) for k,v in families.items()},
            'scope_added':sorted(set(bb)-set(aa)),'scope_removed':sorted(set(aa)-set(bb)),'change_reasons':flags,
            'experiment_kind':'FIXED_ANSWER_RESCORING','agent_quality_improvement_established':False,
            'limitation':'此入口固定已有回答。分数变化反映取证、范围或评测条件变化；Agent 修复请用主 RAG 的生成复测。'}

    def csv(self,job_id):
        view=self.view(job_id);stream=io.StringIO(newline='')
        fields=['题目ID','问题','Agent实际回答','业务域','问题族','错误类型','机器判定','人工判定','当前有效判定','判定依据','缺失证据','引用与评分','范围','范围说明','输入批次','父批次','规则版本','运行ID','运行状态','统计发布状态','通过分子','通过分母','覆盖分子','覆盖分母','验证类型']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();summary=view['summary']
        def safe(v):
            v='' if v is None else str(v)
            return "'"+v if v.lstrip().startswith(('=','+','-','@','\t','\r')) else v
        for row in view['rows']:
            r=row['record'];e=row['event'];review=row['review']
            values=[r['sample_id'],r['question'],r['answer'],view['job'].domain_id,r['family_id'],r['error_type'],e.evaluation_state if e else 'NOT_RUN',
                review.evaluation_state if review else '',row['evaluation_state'],review.reason if review else e.reason if e else '',
                json.dumps(e.input_package.get('missing_items',[]) if e and e.input_package else r['issues'],ensure_ascii=False),
                json.dumps(e.judgment if e else None,ensure_ascii=False),r['scope']['state'],r['scope']['reason'],view['batch'].batch_id,view['batch'].parent_batch_id,
                view['job'].rule_snapshot['version'],job_id,view['job'].status,summary['publication_status'],summary['pass_rate']['numerator'],summary['pass_rate']['denominator'],
                summary['coverage']['numerator'],summary['coverage']['denominator'],'已有回答离线重评']
            writer.writerow({k:safe(v) for k,v in zip(fields,values)})
        return ('\ufeff'+stream.getvalue()).encode('utf-8')
