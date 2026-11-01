import test from 'node:test'
import assert from 'node:assert/strict'
import {supplementReference,supplementSource,latestReferenceSupplement} from '../src/knowledge-supplement.js'
import {proposedChange} from '../src/change-analysis-prompt.js'
import {createWorkspace} from '../src/workspace.js'
import {createRetrievalWorkspace} from '../src/retrieval-workspace.js'
const clone=v=>JSON.parse(JSON.stringify(v))
const session={provider_session_id:'session-one',credential_status:'PRESENT',text_connection_status:'READY'}
function fixture(){
 const knowledge={knowledge_dataset_id:'knowledge-one',version:1,name:'原知识库',documents:[{document_id:'original',title:'原资料',text:'原规则完整保留',metadata:{source:'USER_UPLOADED'}}],metadata:{owner_note:'preserve'}}
 const index={index_id:'index-one',knowledge_dataset_id:'knowledge-one',knowledge_version:1,chunk_config:{algorithm:'source-section-v1',chunk_size:200,chunk_overlap:20},embedding_snapshot:{model:'original-model'}}
 const view={run:{run_id:'run-one',status:'COMPLETE',case_results:[{case_id:'case-one',query:'签收第五天能退吗？'}],controls:{knowledge_snapshot:knowledge,index_snapshot:index,eval_set_snapshot:{retrieval_eval_set_id:'tests-one',version:1,cases:[{case_id:'case-one',query:'签收第五天能退吗？',partition:'DEBUG',expected_answer:'7天内可申请；包装完整、不影响二次销售。定制商品不适用。'}]}}}}
 let latest=clone(knowledge),lost=false
 const calls=[]
 const client={get:async path=>{calls.push(['get',path]);assert.equal(path,'/knowledge-datasets/knowledge-one');return clone(latest)},post:async(path,body)=>{
  calls.push(['post',path,clone(body)])
  if(path==='/ai/evaluation-chat')return {turn_id:'turn-one',created_at:'2026-10-30T13:00:00Z',answer:'AI 的错误建议：把时限改为90天。',provider_call_count:1,usage:{known_total_tokens:25}}
  assert.equal(path,'/knowledge-datasets');latest={...clone(body),version:latest.version+1}
  if(lost){lost=false;throw new Error('saved response lost')}
  return clone(latest)
 }}
 return {view,client,calls,get latest(){return latest},set latest(value){latest=value},loseNextSave(){lost=true}}
}
const generate=f=>supplementReference({view:f.view,caseId:'case-one',session,client:f.client})
test('supplement saves the exact complete reference, keeps old documents, and records AI separately from policy',async()=>{
 const f=fixture(),frozen=clone(f.view),r=await generate(f)
 assert.deepEqual(r.knowledge.documents[0],frozen.run.controls.knowledge_snapshot.documents[0]);assert.deepEqual(f.view,frozen)
 assert.equal(r.document.text,'问题：签收第五天能退吗？\n参考答案：\n7天内可申请；包装完整、不影响二次销售。定制商品不适用。')
 assert.doesNotMatch(r.document.text,/90天/);assert.match(r.document.metadata.reference_supplement.ai_explanation,/90天/)
 assert.equal(r.document.metadata.reference_supplement.source_run_id,'run-one');assert.equal(r.knowledge.metadata.owner_note,'preserve')
})
test('clicking again reuses the saved supplement without another model call or version',async()=>{
 const f=fixture();const a=await generate(f),b=await generate(f)
 assert.equal(b.alreadyAdded,true);assert.equal(b.document.document_id,a.document.document_id);assert.equal(b.knowledge.version,2)
 assert.equal(f.calls.filter(c=>c[0]==='post').length,2)
})
test('a lost knowledge-save response is recovered by reading the saved document, without duplicating it',async()=>{
 const f=fixture();f.loseNextSave();await assert.rejects(generate(f),/response lost/)
 const recovered=await generate(f);assert.equal(recovered.alreadyAdded,true);assert.equal(recovered.knowledge.documents.length,2)
 assert.equal(f.calls.filter(c=>c[1]==='/ai/evaluation-chat').length,1);assert.equal(f.latest.version,2)
})
test('model failure does not save a supplement or claim completion',async()=>{
 const f=fixture();f.client.post=async()=>{throw new Error('model unavailable')}
 await assert.rejects(generate(f),/model unavailable/);assert.equal(f.latest.version,1);assert.equal(f.latest.documents.length,1)
})
test('edits made while the model is running survive the supplement',async()=>{
 const f=fixture(),post=f.client.post
 f.client.post=async(path,body)=>{const value=await post(path,body);if(path==='/ai/evaluation-chat')f.latest={...f.latest,version:2,documents:[...f.latest.documents,{document_id:'concurrent',text:'保留同时新增的资料',metadata:{}}]};return value}
 const r=await generate(f);assert.equal(r.knowledge.version,3);assert.equal(r.knowledge.documents[1].text,'保留同时新增的资料')
})
test('holdout, unexecuted and reference-less cases cannot become training material',()=>{
 const f=fixture();f.view.run.controls.eval_set_snapshot.cases[0].partition='HOLDOUT';assert.throws(()=>supplementSource(f.view,'case-one'),/调试题/)
 f.view.run.controls.eval_set_snapshot.cases[0].partition='DEBUG';f.view.run.controls.eval_set_snapshot.cases[0].expected_answer='';assert.throws(()=>supplementSource(f.view,'case-one'),/没有参考答案/)
 assert.throws(()=>supplementSource(f.view,'never-run'),/调试题/)
})
test('supplement notices require a matching run, and can return to a previously supplemented question',()=>{
 assert.equal(latestReferenceSupplement({documents:[{metadata:{}}]}),null)
 const docs=['a','b'].map((id,i)=>({document_id:id,metadata:{reference_supplement:{source_run_id:'run',source_case_id:id,created_at:String(i)}}}))
 assert.equal(latestReferenceSupplement({documents:docs},'run','a').document_id,'a');assert.equal(latestReferenceSupplement({documents:docs},'another'),null)
})
test('knowledge update prepares the same index configuration and keeps the frozen baseline and original test set',async()=>{
 const f=fixture(),base=clone(f.view),newIndex={...clone(base.run.controls.index_snapshot),index_id:'index-two',knowledge_version:2}
 newIndex.chunk_config={chunk_size:200,chunk_overlap:20,algorithm:'source-section-v1'}
 const originalGet=f.client.get,originalPost=f.client.post,job={job_id:'job-one',status:'READY',index_id:'index-two'};let requestId
 f.client.post=async(path,body)=>{if(path.endsWith('/index-tasks')){assert.deepEqual(body.chunk_config,base.run.controls.index_snapshot.chunk_config);assert.equal(body.embedding_model,'original-model');requestId=body.request_id;return {...job,request_id:requestId}}return originalPost(path,body)}
 f.client.get=async path=>path==='/index-tasks/job-one'?{...job,request_id:requestId}:path==='/knowledge-indices/index-two'?newIndex:originalGet(path)
 const memory=new Map(),storage={getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)}
 const work=createWorkspace(storage,f.client,{autoPoll:false}),rag=createRetrievalWorkspace(work,storage,f.client,{autoPoll:false})
 work.state.session=session;Object.assign(rag.state,{baseline:f.view,knowledge:base.run.controls.knowledge_snapshot,index:base.run.controls.index_snapshot,evalSet:base.run.controls.eval_set_snapshot})
 await rag.supplementFromReference({view:f.view,caseId:'case-one'})
 assert.equal(work.state.error,null);assert.equal(work.state.step,'knowledge');assert.equal(rag.state.index.index_id,'index-two')
 assert.equal(proposedChange({view:rag.state.baseline,caseId:'case-one',type:'KNOWLEDGE_UPDATE',index:rag.state.index}).valid,true)
 assert.deepEqual(rag.state.baseline,base);assert.deepEqual(rag.state.evalSet,base.run.controls.eval_set_snapshot)
 assert.equal(JSON.parse(memory.get('agenteval.retrieval.v1')).supplementCase,'case-one');rag.dispose();work.dispose()
})
