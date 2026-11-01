"""Knowledge audit, preview and bounded diagnostic reruns on acquired cases only."""
import asyncio
from pydantic import Field
from .models import Artifact,uid,now
from .canonical import digest,text_hash
from .rag_evidence import coverage


class DiagnosticRun(Artifact):
    diagnostic_id: str = Field(default_factory=uid)
    request_id: str
    request_hash: str
    parent_run_id: str
    case_id: str
    reviewer: str
    status: str = 'RUNNING'
    frozen_input: dict
    result: dict | None = None
    error: str | None = None
    finished_at: str | None = None
    observations: list[dict] = Field(default_factory=list)
    request_count: int = 0


def audit(rag,evalset_id):
    ev=rag.store.get('retrieval_evalsets',evalset_id)
    index=rag.store.get('knowledge_indices',ev.index_id)
    docs=rag.store.get('knowledge_datasets',index.knowledge_dataset_id,index.knowledge_version).documents
    return {'eval_set_id':ev.retrieval_eval_set_id,'version':ev.version,'index_id':index.index_id,
        'knowledge_version':index.knowledge_version,
        'cases':[{'case_id':c.case_id,'query':c.query,'coverage':coverage(c.knowledge_requirements,docs)} for c in ev.cases if c.partition=='DEBUG'],
        'holdout_count':sum(c.partition=='HOLDOUT' for c in ev.cases),
        'notice':'只检查开发题；原文包含不等于语义充分，未审核项不计为完整覆盖。'}


async def diagnostic(rag,run_id,case_id,request_id,quotes,reviewer,provider_session_id):
    from .retrieval_models import RetrievalCase
    from .retrieval_runtime import evaluate_answer
    from .provider_transport import ObservedProvider
    run=rag.store.get('retrieval_runs',run_id)
    if run.status not in {'COMPLETE','PARTIAL'} or not any(c['case_id']==case_id for c in run.case_results):
        raise ValueError('ACQUIRED_DEBUG_CASE_REQUIRED')
    if not run.verify_answers or not any(a.case_id==case_id and a.execution_status=='SUCCESS' and any(t.response.strip() for t in a.turn_evidence) for a in run.answer_results):
        raise ValueError('DIAGNOSTIC_BASELINE_ANSWER_REQUIRED')
    case=next(RetrievalCase.model_validate(c) for c in run.controls['eval_set_snapshot']['cases'] if c['case_id']==case_id)
    if case.partition!='DEBUG':raise ValueError('HOLDOUT_LOCKED')
    session=rag.providers.get(provider_session_id)
    if session.configuration.model_dump()!=run.provider_configuration_snapshot or session.text_connection_status!='READY':
        raise ValueError('PROVIDER_CONFIG_CHANGED')
    docs=run.controls['knowledge_snapshot']['documents'];by_id={d['document_id']:d for d in docs}
    if not reviewer.strip() or not quotes or len(quotes)>20 or sum(len(q['quote']) for q in quotes)>12000:
        raise ValueError('DIAGNOSTIC_EVIDENCE_INVALID')
    contexts=[]
    for i,q in enumerate(quotes):
        doc=by_id.get(q['document_id'])
        if not doc or not q['quote'].strip() or q['quote'] not in doc['text']:
            raise ValueError('DIAGNOSTIC_SOURCE_MISMATCH')
        start=q.get('source_start') if q.get('source_start') is not None else doc['text'].find(q['quote'])
        end=q.get('source_end') if q.get('source_end') is not None else start+len(q['quote'])
        if doc['text'][start:end]!=q['quote'] or q.get('source_hash') and q['source_hash']!=text_hash(doc['text']):
            raise ValueError('DIAGNOSTIC_SOURCE_MISMATCH')
        contexts.append({'document_id':q['document_id'],'chunk_id':'manual_'+str(i),
            'text':q['quote'],'source':'USER_SELECTED_SOURCE_NOT_REFERENCE_ANSWER',
            'source_hash':text_hash(doc['text']),'source_start':start,
            'source_end':end,'offset_unit':'UNICODE_CODEPOINT'})
    frozen={'case':case.model_dump(),'contexts':contexts,'provider_config':session.configuration.model_dump(),
        'scoring_profile':run.controls.get('scoring_profile'),'evaluation_config':run.controls['evaluation_config'],
        'answer_prompt':run.retrieval_config.answer_prompt,'reference_documents':docs,
        'subject':'DIAGNOSTIC_CONTEXT','not_production_retrieval':True,'request_limit':2}
    request_hash=digest({'run':run_id,'case':case_id,'quotes':quotes,'reviewer':reviewer,'frozen':frozen})
    with rag.store.transaction():
        prior=next((d for d in rag.store.list('rag_diagnostics') if d.request_id==request_id),None)
        if prior:
            if prior.request_hash!=request_hash:raise ValueError('IDEMPOTENCY_CONFLICT')
            return prior
        record=DiagnosticRun(request_id=request_id,request_hash=request_hash,parent_run_id=run_id,case_id=case_id,
            reviewer=reviewer,frozen_input=frozen)
        lease=rag.store.acquire_run_lease(record.diagnostic_id,'rag_diagnostics')
        rag.store.put('rag_diagnostics',record)
    provider=None;result=None;error=None
    try:
        provider=ObservedProvider(session.configuration,rag.providers.credential(provider_session_id),rag.providers.judge_credential(provider_session_id))
        provider.request_limit=2
        row={'status':'SUCCESS','query':case.query,'effective_query':case.query,'index_id':run.controls['index_snapshot']['index_id'],
            'top_k':len(contexts),'results':contexts,'case_id':case_id,'run_id':record.diagnostic_id}
        answer=await asyncio.wait_for(evaluate_answer(provider,case,row,run.controls['evaluation_config'],
            run.controls.get('scoring_profile'),docs,run.retrieval_config.answer_prompt),timeout=90)
        result=answer.to_dict()
    except asyncio.TimeoutError:error='DIAGNOSTIC_TIMEOUT'
    except asyncio.CancelledError:error='DIAGNOSTIC_INTERRUPTED'
    except Exception:error='DIAGNOSTIC_EXECUTION_FAILED'
    finally:
        if provider:await provider.close()
        record=record.model_copy(update={'status':'FAILED' if error else 'COMPLETE','result':result,'error':error,
            'finished_at':now(),'observations':provider.observations if provider else [],'request_count':provider.call_count if provider else 0})
        with rag.store.transaction():rag.store.put('rag_diagnostics',record)
        lease.close()
    return record


def export_deepeval(rag,run_id):
    run=rag.store.get('retrieval_runs',run_id)
    if run.status not in {'COMPLETE','PARTIAL'}:raise ValueError('ACQUIRED_RUN_REQUIRED')
    cases={c['case_id']:c for c in run.controls['eval_set_snapshot']['cases']}
    rows={c['case_id']:c for c in run.case_results};out=[];excluded=[]
    for answer in run.answer_results:
        c=cases[answer.case_id];row=rows.get(answer.case_id)
        if c.get('partition')=='HOLDOUT' or not row:continue
        if answer.execution_status!='SUCCESS' or row['status']!='SUCCESS' or not answer.turn_evidence:
            excluded.append({'case_id':answer.case_id,'reason':'EXECUTION_FAILED'});continue
        req=c.get('knowledge_requirements',{})
        expected=c.get('expected_answer') if req.get('review_status')=='CONFIRMED' and req.get('source')=='USER' and req.get('reviewed_answer_hash')==text_hash(c.get('expected_answer') or '') else None
        out.append({'case_id':answer.case_id,'input':c['query'],
            'actual_output':answer.turn_evidence[0].response if hasattr(answer.turn_evidence[0],'response') else answer.turn_evidence[0]['response'],
            'retrieval_context':[x['text'] for x in row['results']],
            'expected_output':expected,'reference_reviewed':bool(expected),
            'source_run_id':run.run_id,'input_hash':digest({'case':c,'row':row})})
    return {'schema_version':'DEEPEVAL_RAG_EXPORT_V1','run_id':run_id,'test_cases':out,'excluded':excluded,
        'notice':'固定回答的独立旁路；原始评分不变；没有已审核参考答案时不运行 Contextual Recall。'}


def recover_diagnostics(rag,run_id):
    records=[]
    for d in rag.store.list('rag_diagnostics'):
        if d.parent_run_id!=run_id:continue
        if d.status=='RUNNING':
            with rag.store.transaction():
                d=rag.store.get('rag_diagnostics',d.diagnostic_id)
                if d.status=='RUNNING':
                    try:lease=rag.store.acquire_run_lease(d.diagnostic_id,'rag_diagnostics')
                    except BlockingIOError:pass
                    else:
                        try:
                            d=d.model_copy(update={'status':'FAILED','error':'DIAGNOSTIC_INTERRUPTED_USAGE_UNKNOWN','finished_at':now()})
                            rag.store.put('rag_diagnostics',d)
                        finally:lease.close()
        records.append(d)
    return records
