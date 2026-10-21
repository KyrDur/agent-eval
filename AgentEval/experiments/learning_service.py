"""Server controlled teaching workflow with append-only, idempotent records."""
from copy import deepcopy
from datetime import datetime
import re
from .canonical import digest
from .models import now
from .learning_models import LearningAttempt, LearningEvent, LearningJudgment, LearningReview
from .learning_pack import BY_ID, CASES, TRANSFERS, PACK_ID, PACK_VERSION, PACK_HASH, NOTICE, FAMILY_CODES, catalog, public_case

REQUEST_ID = re.compile(r'[A-Za-z0-9_-]{8,100}\Z')

class LearningError(ValueError):
    pass


def require(condition, code='LEARNING_STAGE_INVALID'):
    if not condition:
        raise LearningError(code)


class LearningService:
    def __init__(self, experiments):
        self.experiments = experiments
        self.store = experiments.store

    def catalog(self):
        return catalog()

    def events(self, identifier):
        self.store.get('learning_attempts', identifier)
        return sorted((e for e in self.store.list('learning_events') if e.attempt_id == identifier), key=lambda e:e.sequence)

    def _event(self, attempt, name, payload, request_id, request_hash, events):
        event = LearningEvent(attempt_id=attempt.attempt_id, sequence=len(events)+1,
                              request_id=request_id, request_hash=request_hash, name=name, payload=payload)
        self.store.put('learning_events', event)
        return event

    def start(self, case_id, mode, request_id):
        require(bool(REQUEST_ID.fullmatch(request_id)), 'LEARNING_INPUT_INVALID')
        require(case_id in {c['case_id'] for c in CASES}, 'LEARNING_CASE_INVALID')
        require(mode in {'TRAINING','FREE'}, 'LEARNING_INPUT_INVALID')
        fingerprint = digest({'case_id':case_id, 'mode':mode, 'pack_version':PACK_VERSION})
        with self.store.transaction():
            previous = next((a for a in self.store.list('learning_attempts') if a.request_id == request_id), None)
            if previous:
                require(previous.request_hash == fingerprint, 'IDEMPOTENCY_CONFLICT')
                return self.view(previous.attempt_id)
            value = BY_ID[case_id]
            attempt = LearningAttempt(request_id=request_id, request_hash=fingerprint,
                                      pack_id=PACK_ID, pack_version=PACK_VERSION,
                                      case_id=case_id, family_id=value['family_id'], mode=mode)
            self.store.put('learning_attempts', attempt)
            self._event(attempt, 'practice_started', {'highest_hint':3 if mode=='FREE' else 0,
                        'answer_exposed':mode=='FREE','pack_hash':PACK_HASH}, request_id, fingerprint, [])
            return self.view(attempt.attempt_id)

    def _state(self, attempt, events):
        by = lambda name: next((e for e in reversed(events) if e.name==name), None)
        initial = by('initial_judgment_saved')
        highest = max([3 if attempt.mode=='FREE' else 0] + [e.payload.get('level',0) for e in events if e.name=='hint_revealed'])
        transfer = by('transfer_started')
        submitted = by('transfer_submitted')
        exposed = by('transfer_feedback_revealed')
        return dict(initial=initial, highest_hint=highest, plan=by('prediction_saved'),
                    replay=by('verification_completed'), decision=by('adoption_decided'),
                    transfer=transfer, submitted=submitted, exposed=exposed,
                    terminal=by('practice_exited') or by('practice_failed'))

    def view(self, identifier):
        attempt = self.store.get('learning_attempts', identifier)
        events = self.events(identifier)
        state = self._state(attempt, events)
        value = BY_ID[attempt.case_id]
        last = events[-1] if events else None
        initial_independent = bool(state['initial'] and state['initial'].payload.get('independent'))
        transfer_id = state['transfer'].payload['transfer_case_id'] if state['transfer'] else None
        submitted = state['submitted']
        reviews = sorted((r for r in self.store.list('learning_reviews') if r.attempt_id==identifier), key=lambda r:r.created_at)
        review = reviews[-1] if reviews else None
        result = {'schema_version':'learning-1','attempt_id':identifier,'created_at':attempt.created_at,
                  'pack_id':attempt.pack_id,'pack_version':attempt.pack_version,'mode':attempt.mode,
                  'notice':NOTICE,'case':public_case(attempt.case_id),
                  'highest_hint':state['highest_hint'],'initial_independent':initial_independent,
                  'stage':('EXITED' if state['terminal'] and state['terminal'].name=='practice_exited' else 'TECHNICAL_FAILED' if state['terminal'] else
                           'COMPLETE_PENDING_REVIEW' if submitted else 'TRANSFER' if state['transfer'] else
                           'DECIDED' if state['decision'] else 'REPLAYED' if state['replay'] else
                           'PREDICTED' if state['plan'] else 'JUDGED' if state['initial'] else 'STARTED'),
                  'events':[e.model_dump(mode='json') for e in events],
                  'hints':value['hints'][:state['highest_hint']],
                  'reference':deepcopy(value['reference']) if state['highest_hint']>=3 else None,
                  'proposed_change':value['proposed_change'] if state['initial'] or attempt.mode=='FREE' else None,
                  'replay':(deepcopy(value['replay']) if state['plan'].payload['choice']=='APPLY' else
                            {'target':'保留原版，未实施候选修改。','regression':'未进行新模型调用或真实复测。','decision_guidance':'保留原版是有效选择；写清证据与未验证部分。'}) if state['replay'] else None,
                  'transfer':public_case(transfer_id) if transfer_id else None,
                  'transfer_independent_eligible':state['transfer'].payload['independent_eligible'] if transfer_id else None,
                  'transfer_reference':deepcopy(BY_ID[transfer_id]['reference']) if transfer_id and (submitted or state['exposed']) else None,
                  'review_status':review.outcome if review else 'PENDING_HUMAN_REVIEW' if submitted else 'NOT_SUBMITTED',
                  'review':review.model_dump(mode='json') if review else None,
                  'transfer_judgment_verified':bool(review and review.outcome=='MEETS_CRITERIA'),
                  'learning_effect_verified':False,
                  'actual_model_requests':0,
                  'analytics_event':self._analytics(attempt,last,state) if last else None}
        if not state['initial'] and attempt.mode=='TRAINING':
            result['case'].pop('machine_verdict',None)
        if result['transfer'] and not submitted and not state['exposed']:
            result['transfer'].pop('machine_verdict',None)
        return result

    def _analytics(self, attempt, event, state):
        # The only learning metadata eligible for analytics. No answer, quotes,
        # policies, names, free text, or submitted content crosses this boundary.
        return {'event_id':event.event_id,'attempt_id':attempt.attempt_id,'name':event.name,
                'pack_id':attempt.pack_id,'pack_version':attempt.pack_version,
                'case_id':attempt.case_id,'family_id':FAMILY_CODES[attempt.family_id],'mode':attempt.mode,
                'hint_level':state['highest_hint'],'sequence':event.sequence,
                'independent':bool(event.payload.get('independent',False)),
                'stage':event.name,'review_status':'PENDING_HUMAN_REVIEW' if state['submitted'] else 'NOT_SUBMITTED'}

    def history(self):
        return [{'attempt_id':a.attempt_id,'case_id':a.case_id,'title':BY_ID[a.case_id]['title'],
                 'mode':a.mode,'created_at':a.created_at,'stage':self.view(a.attempt_id)['stage']}
                for a in sorted(self.store.list('learning_attempts'),key=lambda a:a.created_at,reverse=True)]

    def mutate(self, identifier, action, payload, request_id):
        require(bool(REQUEST_ID.fullmatch(request_id)), 'LEARNING_INPUT_INVALID')
        fingerprint = digest({'action':action,'payload':payload})
        with self.store.transaction():
            attempt = self.store.get('learning_attempts', identifier)
            events = self.events(identifier)
            previous = next((e for e in events if e.request_id==request_id),None)
            if previous:
                require(previous.request_hash==fingerprint, 'IDEMPOTENCY_CONFLICT')
                return self.view(identifier)
            state = self._state(attempt, events)
            require(not state['terminal'], 'LEARNING_ATTEMPT_CLOSED')
            value = BY_ID[attempt.case_id]
            if action in {'initial','revision','transfer-submit'}:
                judgment = LearningJudgment.model_validate(payload)
                transfer = action=='transfer-submit'
                require(not state['submitted'], 'LEARNING_ALREADY_SUBMITTED')
                if transfer:
                    require(bool(state['transfer']))
                    trace = BY_ID[state['transfer'].payload['transfer_case_id']]
                else:
                    require(not state['transfer'])
                    trace = value
                sources = {item['evidence_id']:item['text'] for item in trace['evidence']}
                sources['answer'] = trace['answer']
                for quote in judgment.evidence:
                    require(quote.evidence_id in sources and quote.quote in sources[quote.evidence_id], 'LEARNING_EVIDENCE_INVALID')
                if action=='initial':
                    require(not state['initial'], 'LEARNING_ALREADY_SUBMITTED')
                    independent = attempt.mode=='TRAINING' and state['highest_hint']==0 and judgment.source=='SELF'
                    name = 'initial_judgment_saved'
                elif action=='revision':
                    require(bool(state['initial']))
                    independent = False
                    name = 'diagnosis_revised'
                else:
                    independent = bool(state['transfer'].payload['independent_eligible'] and not state['exposed'] and judgment.source=='SELF')
                    name = 'transfer_submitted'
                body = {'judgment':judgment.model_dump(mode='json'),'independent':independent,
                        'highest_hint':state['highest_hint'],'assistance':'AI_TEACHING_HINT' if state['highest_hint'] else judgment.source,
                        'reference_kind':'LEARNER_WORK_NOT_HUMAN_GOLD'}
                if transfer:
                    body['review_status']='PENDING_HUMAN_REVIEW'
                    body['transfer_case_id']=trace['case_id']
            elif action=='hint':
                require(bool(state['initial']) or attempt.mode=='FREE', 'LEARNING_INITIAL_REQUIRED')
                require(not state['transfer'])
                level = payload['level']
                require(level==state['highest_hint']+1 and level<=3, 'LEARNING_HINT_ORDER_INVALID')
                name, body = 'hint_revealed', {'level':level,'source':'AI_AUTHORED_TEACHING_REFERENCE','reference_status':'DRAFT_AWAITING_MAINTAINER_REVIEW'}
            elif action=='prediction':
                require(bool(state['initial']) and not state['plan'])
                name, body = 'prediction_saved', payload
            elif action=='replay':
                require(bool(state['plan']) and not state['replay'])
                name, body = 'verification_completed', {'source':'CONSTRUCTED_TEACHING_REPLAY','actual_model_requests':0,
                        'choice':state['plan'].payload['choice'],'not_a_real_experiment':True}
            elif action=='decision':
                require(bool(state['replay']) and not state['decision'])
                require(state['plan'].payload['choice']=='APPLY' or payload['decision']=='KEEP', 'LEARNING_DECISION_INVALID')
                name, body = 'adoption_decided', payload
            elif action=='transfer-start':
                require(bool(state['decision']) and not state['transfer'])
                trace = next(t for t in TRANSFERS if t['family_id']==value['family_id'])
                seen = any(e.name=='transfer_started' and e.payload.get('transfer_case_id')==trace['case_id'] for e in self.store.list('learning_events'))
                name, body = 'transfer_started', {'transfer_case_id':trace['case_id'],
                    'independent_eligible':attempt.mode=='TRAINING' and not seen,'seen_in_workspace':seen,
                    'exposure_scope':'WORKSPACE_WORKFLOW_ONLY_NOT_ANTI_CHEAT'}
            elif action=='transfer-feedback':
                require(bool(state['transfer']) and not state['exposed'])
                require(bool(state['submitted']) or attempt.mode=='FREE', 'LEARNING_TRANSFER_SUBMIT_REQUIRED')
                name, body = 'transfer_feedback_revealed', {'before_submission':not bool(state['submitted']),
                        'reference_status':'DRAFT_AWAITING_MAINTAINER_REVIEW'}
            elif action=='feedback':
                require(bool(state['submitted']))
                name, body = 'feedback_recorded', payload
            elif action in {'exit','technical-failure'}:
                require(not state['submitted'])
                name = 'practice_exited' if action=='exit' else 'practice_failed'
                body = payload
            else:
                raise LearningError('LEARNING_INPUT_INVALID')
            self._event(attempt,name,body,request_id,fingerprint,events)
            return self.view(identifier)

    def review(self, identifier, reviewer, checks, reason, independent_human_attested, outcome):
        """Local maintainer import only. No anonymous web route can call this."""
        with self.store.transaction():
            attempt = self.store.get('learning_attempts',identifier)
            state = self._state(attempt,self.events(identifier))
            require(bool(state['submitted']), 'LEARNING_TRANSFER_SUBMIT_REQUIRED')
            require(state['submitted'].payload['independent'], 'LEARNING_NOT_INDEPENDENT')
            required={'evidence_relevant','hypotheses_reasonable','check_distinguishes_causes','limits_recognized'}
            require(set(checks)==required and all(type(v) is bool for v in checks.values()),'LEARNING_REVIEW_INVALID')
            require(independent_human_attested is True and bool(reviewer.strip()) and len(reason.strip())>=2,'LEARNING_REVIEW_INVALID')
            require(outcome!='MEETS_CRITERIA' or all(checks.values()),'LEARNING_REVIEW_INVALID')
            record=LearningReview(attempt_id=identifier,transfer_event_id=state['submitted'].event_id,
                    reviewer=reviewer.strip(),independent_human_attested=True,outcome=outcome,checks=checks,reason=reason.strip())
            self.store.put('learning_reviews',record)
            return record

    def summary(self):
        attempts=self.store.list('learning_attempts')
        views=[self.view(a.attempt_id) for a in attempts]
        initial=sum(v['initial_independent'] for v in views)
        entered=sum(v['transfer'] is not None for v in views)
        submitted=sum(v['review_status']!='NOT_SUBMITTED' for v in views)
        independent=sum(any(e['name']=='transfer_submitted' and e['payload']['independent'] for e in v['events']) for v in views)
        passed=sum(v['review_status']=='MEETS_CRITERIA' for v in views)
        return {'unit':'尝试次数，不是人数','attempts_started':len(views),'first_judgment_completed':sum(any(e['name']=='initial_judgment_saved' for e in v['events']) for v in views),
                'initial_independent':initial,'exited':sum(v['stage']=='EXITED' for v in views),
                'technical_failures':sum(v['stage']=='TECHNICAL_FAILED' for v in views),
                'transfer_entered':entered,'transfer_submitted':submitted,'transfer_independent_submitted':independent,
                'transfer_unsubmitted':entered-submitted,'pending_human_review':sum(v['review_status']=='PENDING_HUMAN_REVIEW' for v in views),
                'verified_meets_criteria':passed,'verified_not_yet':sum(v['review_status']=='NOT_YET' for v in views),
                'independent_completion_rate':independent/entered if entered else None,
                'verified_success_rate':passed/entered if entered else None,
                'denominator_notice':'达标与独立提交分母为全部进入迁移的尝试，包含未提交、待评、退出与技术失败；未自动评价学习效果。'}

    def export(self,identifier):
        view=self.view(identifier)
        # Export only information the workflow has already authorized to reveal.
        lines=['# 个人诊断练习记录', '',NOTICE,'',f"练习：{view['case']['title']}",f"模式：{view['mode']}；尝试：{identifier}",
               f"提示前独立初判：{'是' if view['initial_independent'] else '否/尚未提交'}；最高提示：{view['highest_hint']}",
               f"学习核验：{view['review_status']}；真实模型请求：0",'',
               '来源边界：教学回放不是本人开发或真实线上提升；学员作答不是校准 HUMAN 金标。','']
        for event in view['events']:
            lines.extend([f"## {event['sequence']}. {event['name']}",f"时间：{event['created_at']}"])
            payload=event['payload']
            if 'judgment' in payload:
                j=payload['judgment']
                lines.extend([f"本人输入来源声明：{j['source']}；已记录协助：{payload['assistance']}",j['judgment'],
                      f"候选原因：{', '.join(j['candidate_causes'])}",f"不确定项：{j['uncertainty']}",f"区分检查：{j['distinguishing_check']}"])
                lines.extend(f"- 引用 {q['evidence_id']}：{q['quote']}" for q in j['evidence'])
            else:
                lines.extend(f'{k}：{v}' for k,v in payload.items())
            lines.append('')
        if view['replay']:
            lines.extend(['## 教学回放结果']+[f'{k}：{v}' for k,v in view['replay'].items()])
        if view['review']:
            lines.extend(['','## 本地维护者核验',str(view['review'])])
        lines.extend(['','局限：参考分析尚待维护者确认；需真实任务观察，不能由填写完整性推断理解或求职效果。'])
        return {'filename':f'learning-{identifier}.md','markdown':'\n'.join(lines),'record':view}
