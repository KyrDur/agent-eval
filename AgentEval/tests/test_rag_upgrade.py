"""Cross-stage invariants: evidence is not a document hit or a judge verdict."""
from copy import deepcopy
from types import SimpleNamespace
import asyncio
import pytest
from test_retrieval import fixture, pair
from experiments.rag_evidence import coverage, RequirementSet, evidence_path
from experiments.rag_retrieval import search,assemble
from experiments.retrieval_models import ChunkConfig,RetrievalConfig,RetrievalCase
from experiments.retrieval_knowledge import chunks_for
from experiments.rag_index_controls import validate_index_change,index_control_reasons
from experiments.canonical import text_hash

DOCS=[{'document_id':'policy','title':'退货','text':'# 退货\n普通商品七日内可退。定制商品除外。\n# 退款\n审核后五个工作日到账。'}]
REQ={'review_status':'CONFIRMED','source':'USER','reviewer':'test fixture declaration',
     'facts':[{'fact_id':'rule','description':'七日内', 'alternatives':[[{'document_id':'policy','quote':'普通商品七日内可退。'}]]},
              {'fact_id':'exception','description':'定制除外','alternatives':[[{'document_id':'policy','quote':'定制商品除外。'}]]}]}

def test_document_hit_does_not_imply_fact_coverage():
    assert coverage(REQ,DOCS)['coverage']==1
    c=coverage(REQ,DOCS,[{'document_id':'policy','text':'普通商品七日内可退。'}])
    assert c['coverage']==.5 and c['status']=='PARTIAL'
    missing=deepcopy(REQ);missing['facts'][1]['alternatives']=[]
    assert coverage(missing,DOCS)['status']=='PARTIAL'
    draft={**REQ,'review_status':'DRAFT'}
    assert coverage(draft,DOCS)['coverage'] is None
    assert coverage({**REQ,'scope':'OUT_OF_SCOPE','facts':[]},DOCS)['status']=='OUT_OF_SCOPE'
    with pytest.raises(ValueError):RequirementSet.model_validate({**REQ,'source':'AI'})

def test_alternatives_joint_support_and_source_version():
    req=deepcopy(REQ);req['facts']=req['facts'][:1]
    req['facts'][0]['alternatives'][0].append({'document_id':'policy','quote':'定制商品除外。'})
    assert coverage(req,DOCS,[{'document_id':'policy','text':'普通商品七日内可退。'}])['coverage']==0
    req['facts'][0]['alternatives'].append([{'document_id':'policy','quote':'七日内'}])
    assert coverage(req,DOCS,[{'document_id':'policy','text':'普通商品七日内可退。'}])['coverage']==1
    req['facts'][0]['alternatives'][0][0]['source_hash']='0'*64
    assert coverage(req,DOCS)['status']=='FULL'  # Valid OR alternative survives a stale citation.
    req['facts'][0]['alternatives']=req['facts'][0]['alternatives'][:1]
    assert coverage(req,DOCS)['status']=='CONFLICT'
    path=evidence_path(REQ,DOCS,{'status':'FAILED','results':DOCS})
    assert path['knowledge']['coverage']==1 and path['context']['coverage'] is None

def test_structure_preserves_unicode_offsets_and_sections():
    raw='前言😀Ａ\r\n# 退货\r\n'+('普通商品七日内可退。定制商品除外。'*20)+'\n# 退款\n审核后到账。'
    ds=SimpleNamespace(documents=[{**DOCS[0],'text':raw}])
    config=ChunkConfig(chunk_size=80,chunk_overlap=10,algorithm='source-section-v1')
    chunks=chunks_for(ds,config)
    assert chunks==chunks_for(ds,config)
    assert len(chunks)>3
    for c in chunks:
        assert raw[c['source_start']:c['source_end']]==c['text']
        assert c['source_hash']==text_hash(raw)
        assert c['parent_start']<=c['source_start']<c['source_end']<=c['parent_end']
    assert not any('# 退款' in c['text'] and '定制' in c['text'] for c in chunks)

def test_hybrid_rank_fusion_and_context_do_not_change_selection():
    chunks=[{'chunk_id':str(i),'document_id':'policy','chunk_index':i,'parent_id':'p','text':t} for i,t in enumerate(['X-17 七日退货','定制商品除外','其他物流规则'])]
    index=SimpleNamespace(chunks=chunks)
    knowledge=SimpleNamespace(search=lambda *a:[{**chunks[2],'rank':1,'score':.9},{**chunks[0],'rank':2,'score':.1}])
    config=RetrievalConfig(top_k=1,retrieval_mode='HYBRID',context_strategy='PARENT')
    result=search(knowledge,index,'X-17',config)
    assert result[0]['chunk_id']=='0'
    assert result[0]['source_ranks']=={'VECTOR':2,'BM25':1}
    selected=result[:1];before=deepcopy(selected)
    expanded,trace=assemble(index,selected,config)
    assert selected==before and len(expanded)==3 and len(trace['added_ids'])==2
    long=SimpleNamespace(chunks=[{**chunks[0],'text':'长'*12001}])
    context,trace=assemble(long,[long.chunks[0]],config)
    assert not context and trace['removed_ids']==['0']

def test_legacy_serialization_is_unchanged():
    assert 'retrieval_mode' not in RetrievalConfig().model_dump()
    assert 'context_strategy' not in RetrievalConfig().model_dump()
    assert 'knowledge_requirements' not in RetrievalCase(case_id='a',query='q').model_dump()


def test_derived_chunk_index_control_and_actual_comparison(fixture,pair):
    rag,sid,d,index,ev,_=fixture;a,_,_=pair
    target=rag.knowledge.build(d.knowledge_dataset_id,d.version,{'chunk_size':50,'chunk_overlap':5,'algorithm':'source-section-v1'},'sha256-lexical-bigram-v1')
    validate_index_change('CHUNKING_CHANGE',index,target)
    with pytest.raises(ValueError):validate_index_change('EMBEDDING_CHANGE',index,target)
    change=rag.propose_change(a.run_id,'CHUNKING_CHANGE',a.retrieval_config.model_dump(),'检查条款边界，保持其他条件不变',['rag_1'],True,target_index_id=target.index_id)
    change=rag.apply(change.change_id)
    b=asyncio.run(rag.run(sid,change.target_eval_set_id,run_type='RETEST',parent_run_id=a.run_id,change_id=change.change_id,verify_answers=True))
    assert not index_control_reasons(a.controls,b.controls,'CHUNKING_CHANGE')
    altered=deepcopy(b.controls);altered['eval_set_snapshot']['cases'][0]['query']='changed'
    assert 'TEST_SEMANTICS_CHANGED' in index_control_reasons(a.controls,altered,'CHUNKING_CHANGE')
    comparison=rag.compare(a.run_id,b.run_id)
    assert comparison


def test_diagnostic_frozen_input_idempotency_and_export(fixture,pair):
    from experiments.rag_lab import diagnostic,export_deepeval
    rag,sid,d,_,_,_=fixture;a,_,_=pair
    q=[{'document_id':'opened','quote':d.documents[0]['text']}]
    first=asyncio.run(diagnostic(rag,a.run_id,'rag_1','diagnostic-test',q,'fixture author',sid))
    assert first.status=='COMPLETE',first.error
    assert first.request_count<=2 and first.frozen_input['subject']=='DIAGNOSTIC_CONTEXT'
    second=asyncio.run(diagnostic(rag,a.run_id,'rag_1','diagnostic-test',q,'fixture author',sid))
    assert first.model_dump()==second.model_dump()
    with pytest.raises(ValueError,match='SOURCE_MISMATCH'):
        asyncio.run(diagnostic(rag,a.run_id,'rag_1','invalid',[{'document_id':'opened','quote':'this is an answer label'}],'author',sid))
    export=export_deepeval(rag,a.run_id)
    assert export['test_cases'] and all(c['expected_output'] is None for c in export['test_cases'])


def test_index_background_receipt_cancel_recover_and_immutability(tmp_path):
    from experiments.store import JsonStore
    from experiments.retrieval_knowledge import FrozenKnowledge
    from experiments.rag_index_jobs import submit,read,cancel,_tasks,key,IndexBuild
    store=JsonStore(tmp_path/'jobs');ds=FrozenKnowledge(store).create(DOCS,'jobs')
    inputs={'dataset_id':ds.knowledge_dataset_id,'version':1,'config':{'chunk_size':100,'chunk_overlap':0},'embedding_model':'sha256-lexical-bigram-v1'}
    async def flow():
        job=await submit(store,'first',inputs)
        same=await submit(store,'first',inputs)
        assert job.job_id==same.job_id
        with pytest.raises(ValueError,match='IDEMPOTENCY'):
            await submit(store,'first',{**inputs,'version':2})
        await _tasks[key(store,job.job_id)]
        done=read(store,job.job_id)
        assert done.status=='READY',done.error
        assert store.get('knowledge_indices',done.index_id).status=='READY'
        with pytest.raises(ValueError):store.put('index_builds',done.model_copy(update={'status':'FAILED'}))
        stopped=await submit(store,'cancel-immediate',inputs)
        terminal=await cancel(store,stopped.job_id)
        assert terminal.status=='CANCELLED'
        assert read(store,stopped.job_id).status=='CANCELLED'
    asyncio.run(flow())
    import fcntl,tempfile
    from pathlib import Path
    with (Path(tempfile.gettempdir())/'agent-eval-index-resource.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(ValueError,match='INDEX_RESOURCE_BUSY'):
            FrozenKnowledge(store).build(ds.knowledge_dataset_id,1,embedding_model='sha256-lexical-bigram-v1')
    lost=IndexBuild(request_id='lost',input_hash='hash',inputs=inputs)
    store.put('index_builds',lost)
    assert read(store,lost.job_id).error=='INDEX_BUILD_INTERRUPTED'


def test_policy_pack_is_draft_and_does_not_serve_holdout():
    from experiments.rag_policy_pack import public_pack
    pack=public_pack()
    assert len(pack['debug_cases'])==16 and pack['holdout_count']==8
    for case in pack['debug_cases']:
        RetrievalCase.model_validate(case)
        assert case['partition']=='DEBUG'
        audit=coverage(case['knowledge_requirements'],pack['documents'])
        assert audit['status']=='UNREVIEWED' and audit['coverage'] is None
        assert audit['included_count']==audit['required_count']


def test_joint_original_spans_include_cross_chunk_fact_without_fabricated_offsets():
    from experiments.rag_evidence import included_quote,SourceEvidence
    raw='主规则😀可以退货，但定制商品除外。'
    e=SourceEvidence(document_id='p',quote=raw)
    doc={'document_id':'p','text':raw}
    a={'document_id':'p','text':raw[:8],'source_start':0,'source_end':8,'source_hash':text_hash(raw),'offset_unit':'UNICODE_CODEPOINT'}
    b={**a,'text':raw[8:],'source_start':8,'source_end':len(raw)}
    assert included_quote(e,doc,[a,b])
    assert not included_quote(e,doc,[a])
    assert not included_quote(e,doc,[a,{**b,'source_hash':'wrong'}])


def test_deepeval_optional_real_http_budget_boundary(tmp_path):
    import json,subprocess,threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from pathlib import Path
    executable=Path(__file__).resolve().parents[2]/'.venv-deepeval/bin/python'
    if not executable.exists():pytest.skip('optional pinned DeepEval environment not installed')
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            text=data['messages'][0]['content'];schema=json.loads(text.split('Return only JSON conforming to this schema:\n')[-1]);calls.append(schema['title'])
            shapes={'Truths':{'truths':['政策']},'Claims':{'claims':['回答']},'Verdicts':{'verdicts':[{'verdict':'yes','reason':'controlled transport fixture','statement':'规则','expected_output':'规则'}]},'FaithfulnessScoreReason':{'reason':'controlled fixture'},'ContextualRecallScoreReason':{'reason':'controlled fixture'}}
            body=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(shapes[schema['title']])}}],'usage':{'prompt_tokens':3,'completion_tokens':2}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    worker=Path(__file__).resolve().parents[1]/'experiments/deepeval_worker.py'
    payload={'configuration':{'model':'controlled-fixture','provider':'openai-compatible','base_url':f'http://127.0.0.1:{server.server_port}/v1','max_tokens':1024},'credential':'local-test-only','request_limit':3,
     'test_cases':[{'case_id':'c','input':'q','actual_output':'a','retrieval_context':['policy'],'expected_output':'reference','reference_reviewed':True}]}
    try:
        result=subprocess.run([str(executable),str(worker)],input=json.dumps(payload),capture_output=True,text=True,timeout=30)
        assert result.returncode==0,result.stderr[-500:]
        report=json.loads(result.stdout)
        assert len(calls)==report['request_count']==3
        assert all(m['score'] is None and m['status']=='FAILED' for m in report['observations'])
        assert all(c['usage']=={'prompt_tokens':3,'completion_tokens':2} for c in report['provider_requests'])
    finally:server.shutdown();server.server_close()


def test_cancel_kills_live_worker_process_group(fixture,monkeypatch):
    import sys
    import experiments.rag_index_jobs as jobs
    rag,_,d,_,_,_=fixture
    original=asyncio.create_subprocess_exec;spawned=[]
    async def slow_worker(*args,**kwargs):
        # Real OS process group using the same launcher/cancellation boundary;
        # fixture inference sleeps instead of consuming model resources.
        process=await original(sys.executable,'-c','import time;time.sleep(30)',**kwargs)
        spawned.append(process);return process
    monkeypatch.setattr(jobs.asyncio,'create_subprocess_exec',slow_worker)
    async def exercise():
        job=await jobs.submit(rag.store,'live-cancel',{'dataset_id':d.knowledge_dataset_id,'version':1,'embedding_model':'sha256-lexical-bigram-v1'})
        while not spawned:await asyncio.sleep(.01)
        stopped=await jobs.cancel(rag.store,job.job_id)
        assert stopped.status=='CANCELLED'
        assert spawned[0].returncode is not None
        assert jobs.key(rag.store,job.job_id) not in jobs._processes
    asyncio.run(exercise())


def test_new_learning_cases_use_existing_private_transfer_flow(tmp_path):
    from experiments.learning_service import LearningService
    from experiments.store import JsonStore
    from test_learning import progress
    service=LearningService(SimpleNamespace(store=JsonStore(tmp_path/'learning-rag')))
    for i in range(1,7):
        result=progress(service,case=f'rag-p{i}',request=f'new-learning-{i}')
        assert result['transfer']['case_id']==f'rag-t{i}'
        assert 'reference' not in result['transfer']
        assert result['actual_model_requests']==0
        assert not result['learning_effect_verified']


def test_manual_context_comparison_requires_an_acquired_baseline_answer(fixture):
    from experiments.rag_lab import diagnostic
    rag,sid,d,_,ev,_=fixture
    run=asyncio.run(rag.run(sid,ev.retrieval_eval_set_id,verify_answers=False))
    before=len(rag.store.list('rag_diagnostics'))
    with pytest.raises(ValueError,match='DIAGNOSTIC_BASELINE_ANSWER_REQUIRED'):
        asyncio.run(diagnostic(rag,run.run_id,'rag_1','no-baseline-answer',[{'document_id':'opened','quote':d.documents[0]['text']}],'software fixture',sid))
    assert len(rag.store.list('rag_diagnostics'))==before
