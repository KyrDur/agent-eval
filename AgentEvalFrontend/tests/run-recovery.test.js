import test from 'node:test'
import assert from 'node:assert/strict'
import {createWorkspace} from '../src/workspace.js'
import {createRetrievalWorkspace} from '../src/retrieval-workspace.js'
import {createApi,ApiError} from '../src/api.js'
import {savedScoreView} from './fixtures/score-check.js'
const config={top_k:3,query_rewrite:false,rerank:false,answer_prompt:'PRIVATE_PROMPT_MUST_NOT_PERSIST'}
function fixture(client,memory=new Map(),options={autoPoll:false}){
 const storage={getItem:key=>memory.get(key)||null,setItem:(key,value)=>memory.set(key,value)}
 const work=createWorkspace(storage,client,{autoPoll:false}),rag=createRetrievalWorkspace(work,storage,client,options),v=savedScoreView()
 work.state.session={provider_session_id:'session-check'}
 Object.assign(rag.state,{knowledge:v.run.controls.knowledge_snapshot,index:v.run.controls.index_snapshot,evalSet:v.run.controls.eval_set_snapshot})
 return {work,rag,memory}
}
const start=f=>f.rag.run('BASELINE',config,true,'saved-profile')
test('accepted task survives a failed progress read and manual sync only reads that run',async()=>{
 let disconnected=true,posts=0,history=0
 const v=savedScoreView(),f=fixture({post:async()=>{posts++;return v.run},get:async path=>{
  if(path==='/retrieval-history'){history++;throw new Error('history failure')}
  assert.equal(path,'/retrieval-runs/run-check');if(disconnected)throw new ApiError(null,0);return v
 }})
 await start(f)
 assert.equal(f.work.state.error,null);assert.equal(f.work.state.step,'evaluate')
 assert.equal(f.rag.state.pendingSubmission.run_id,'run-check');assert.match(f.rag.state.progressIssue,/评测已提交/)
 assert.equal(JSON.parse(f.memory.get('agenteval.retrieval.v1')).pendingRun,'run-check')
 disconnected=false;await f.rag.syncProgress()
 assert.equal(f.rag.state.baseline.run.run_id,'run-check');assert.equal(f.rag.state.pendingSubmission,null)
 assert.equal(posts,1);assert.equal(history,0);assert.equal(f.work.state.error,null)
})
test('successful start never depends on a history-list request',async()=>{
 const v=savedScoreView(),gets=[],f=fixture({post:async()=>v.run,get:async path=>{gets.push(path);if(path.includes('history'))throw Error('offline');return v}})
 await start(f);assert.deepEqual(gets,['/retrieval-runs/run-check']);assert.equal(f.work.state.error,null)
})
test('lost submission response recovers the exact durable receipt without another POST',async()=>{
 const v=savedScoreView(),gets=[];let posts=0,id
 const f=fixture({post:async(_,body)=>{id=body.request_id;posts++;throw new ApiError(null,0)},get:async path=>{
  gets.push(path);return path.startsWith('/retrieval-run-tasks/')?{...v.run,request_id:id}:v
 }})
 await start(f);assert.equal(posts,1);assert.equal(f.rag.state.baseline.run.run_id,'run-check')
 assert.deepEqual(gets,[`/retrieval-run-tasks/${id}`,'/retrieval-runs/run-check'])
 assert.equal(f.work.state.error,null)
})
test('reload retains the same request ID and hash, without storing content, and retries only on user action',async()=>{
 let accepted=false;const posts=[],v=savedScoreView(),memory=new Map()
 const client={post:async(_,body)=>{posts.push(body);if(!accepted)throw new ApiError(null,0);return v.run},get:async path=>{
  if(path.startsWith('/retrieval-run-tasks/'))throw new ApiError('RUN_RECEIPT_NOT_FOUND',404)
  return v
 }}
 const first=fixture(client,memory);await start(first)
 const saved=JSON.parse(memory.get('agenteval.retrieval.v1'))
 assert.equal(saved.pendingRequest,posts[0].request_id);assert.match(saved.pendingFingerprint,/^[a-f0-9]{64}$/)
 assert.equal(first.rag.state.canRetrySubmission,true)
 assert.doesNotMatch(memory.get('agenteval.retrieval.v1'),/PRIVATE_PROMPT|top_k|89 元|api_key|configuration/)
 const second=fixture(client,memory)
 assert.equal(posts.length,1);assert.equal(second.rag.state.pendingSubmission.request_id,posts[0].request_id)
 await second.rag.syncProgress();assert.equal(posts.length,1)
 accepted=true;await start(second)
 assert.equal(posts.length,2);assert.equal(posts[0].request_id,posts[1].request_id)
 assert.equal(second.rag.state.pendingSubmission,null)
})
test('unconfirmed receipt never triggers a second submission, even when run is invoked again',async()=>{
 let posts=0;const f=fixture({post:async()=>{posts++;throw new ApiError(null,0)},get:async()=>{throw new ApiError(null,0)}})
 await start(f);await start(f)
 assert.equal(posts,1);assert.equal(f.rag.state.canRetrySubmission,false)
})
test('mismatched receipt and view cannot attach a different evaluation',async()=>{
 const v=savedScoreView();let receiptWrong=true
 const f=fixture({post:async()=>{throw new ApiError(null,0)},get:async path=>path.startsWith('/retrieval-run-tasks/')?
  {...v.run,request_id:receiptWrong?'other-request':f.rag.state.pendingSubmission.request_id}:{...v,run:{...v.run,run_id:'other-run'}}})
 await start(f);assert.equal(f.rag.state.pendingSubmission.run_id,null);assert.equal(f.rag.state.baseline,null)
 receiptWrong=false;await f.rag.syncProgress()
 assert.equal(f.rag.state.pendingSubmission.run_id,'run-check');assert.equal(f.rag.state.baseline,null)
})
test('recovering a new baseline ignores old retest, comparison and mutable-control pointers',async()=>{
 const v=savedScoreView(),memory=new Map(),first=fixture({post:async()=>{throw new ApiError(null,0)},get:async()=>{throw new ApiError(null,0)}},memory)
 await start(first)
 const saved=JSON.parse(memory.get('agenteval.retrieval.v1'))
 memory.set('agenteval.retrieval.v1',JSON.stringify({...saved,baseline:'old-baseline',retest:'old-retest',change:'old-change',comparison:'old-comparison'}))
 const paths=[],f=fixture({get:async path=>{
  paths.push(path)
  if(path.startsWith('/retrieval-run-tasks/'))return {...v.run,request_id:saved.pendingRequest}
  if(path==='/retrieval-history')return []
  if(path==='/retrieval-runs/run-check')return v
  if(path.startsWith('/provider-sessions/'))return {provider_session_id:'session-check'}
  if(path.startsWith('/knowledge-indices/'))return v.run.controls.index_snapshot
  if(path.startsWith('/knowledge-datasets/'))return v.run.controls.knowledge_snapshot
  if(path.startsWith('/retrieval-evalsets/'))return v.run.controls.eval_set_snapshot
  throw Error('Unexpected old record '+path)
 }},memory)
 await f.rag.restore()
 assert.equal(f.rag.state.baseline.run.run_id,'run-check');assert.equal(f.rag.state.retest,null)
 assert.equal(f.rag.state.change,null);assert.equal(f.rag.state.comparison,null);assert.equal(f.rag.state.pendingSubmission,null)
 assert(!paths.some(p=>p.includes('old-')))
})
test('different parameters cannot replace an unresolved request or start a second evaluation',async()=>{
 let posts=0;const f=fixture({post:async()=>{posts++;throw new ApiError(null,0)},get:async()=>{throw new ApiError('RUN_RECEIPT_NOT_FOUND',404)}})
 await start(f);const id=f.rag.state.pendingSubmission.request_id
 await f.rag.run('BASELINE',{...config,top_k:5},true,'saved-profile')
 assert.equal(posts,1);assert.equal(f.rag.state.pendingSubmission.request_id,id)
 assert.equal(f.work.state.error.title,'上次提交仍待确认')
})
test('definitive validation errors remain errors and release the unaccepted receipt',async()=>{
 const f=fixture({post:async()=>{throw new ApiError('CREDENTIAL_UNAVAILABLE',409)}})
 await start(f);assert.equal(f.rag.state.pendingSubmission,null);assert.equal(f.work.state.error.title,'模型凭据需要重新输入')
})
test('late accepted response cannot overwrite a new experiment',async()=>{
 let release,entered;const ready=new Promise(resolve=>entered=resolve),held=new Promise(resolve=>release=resolve)
 const f=fixture({post:async()=>{entered();return held},get:async()=>{throw Error('must not read old task')}})
 const running=start(f);await ready;f.rag.reset();release(savedScoreView().run);await running
 assert.equal(f.rag.state.baseline,null);assert.equal(f.rag.state.pendingSubmission,null)
 assert.equal(f.work.state.error,null)
})
test('constructor does not read history; unresolved pending request cannot attach another matching run',async()=>{
 const v=savedScoreView(),memory=new Map(),first=fixture({post:async()=>{throw new ApiError(null,0)},get:async()=>{throw new ApiError('RUN_RECEIPT_NOT_FOUND',404)}},memory)
 await start(first)
 const gets=[],f=fixture({get:async path=>{
  gets.push(path)
  if(path.startsWith('/retrieval-run-tasks/'))throw new ApiError('RUN_RECEIPT_NOT_FOUND',404)
  if(path==='/retrieval-history')return [{run_id:'unrelated',run_type:'BASELINE',retrieval_eval_set_id:'evalset-check',version:1,created_at:'2026-10-22'}]
  if(path.startsWith('/provider-sessions/'))return {provider_session_id:'session-check'}
  if(path.startsWith('/retrieval-evalsets/'))return v.run.controls.eval_set_snapshot
  if(path.startsWith('/knowledge-indices/'))return v.run.controls.index_snapshot
  if(path.startsWith('/knowledge-datasets/'))return v.run.controls.knowledge_snapshot
  throw new Error('Unexpected '+path)
 }},memory)
 assert.deepEqual(gets,[]);await f.rag.restore()
 assert.equal(f.rag.state.baseline,null);assert.equal(f.rag.state.canRetrySubmission,true)
 assert(!gets.some(p=>p.startsWith('/retrieval-runs/')))
})
test('only opted-in GETs retry; POSTs, validation failures and cancellation do not retry',async()=>{
 let gets=0,posts=0
 const client=createApi(async(_,options)=>{
  if(options.method==='POST'){posts++;throw Error('lost write response')}
  if(++gets===1)throw Error('transient transport')
  return {ok:true,status:200,json:async()=>({saved:true})}
 })
 assert.deepEqual(await client.get('/retrieval-runs/id',{retryReads:true}),{saved:true});assert.equal(gets,2)
 await assert.rejects(client.post('/retrieval-run-tasks',{}),ApiError);assert.equal(posts,1)
 const controller=new AbortController();controller.abort()
 await assert.rejects(client.get('/retrieval-runs/id',{retryReads:true,signal:controller.signal}),ApiError);assert.equal(gets,2)
 let refused=0
 const rejected=createApi(async()=>{refused++;return {ok:false,status:401,json:async()=>({detail:'WORKSPACE_UNAVAILABLE'})}})
 await assert.rejects(rejected.get('/retrieval-runs/id',{retryReads:true}),ApiError);assert.equal(refused,1)
})
test('result-only restore uses frozen snapshots and skips history and duplicate dataset reads',async()=>{
 const v=savedScoreView(),gets=[],memory=new Map([['agenteval.retrieval.v1',JSON.stringify({baseline:'run-check',knowledge:'old-draft',index:'old-index',evalSet:'old-evalset',session:'session-check'})]])
 const f=fixture({get:async path=>{
  gets.push(path)
  if(path==='/retrieval-runs/run-check')return v
  if(path==='/provider-sessions/session-check')return {provider_session_id:'session-check'}
  throw Error('Unnecessary result read '+path)
 }},memory)
 await f.rag.restore({resultsOnly:true})
 assert.deepEqual(gets,['/retrieval-runs/run-check','/provider-sessions/session-check'])
 assert.equal(f.rag.state.evalSet.retrieval_eval_set_id,'evalset-check')
 assert.equal(f.rag.state.index.index_id,'index-check');assert.equal(f.rag.state.knowledge.knowledge_dataset_id,'knowledge-check')
})
test('frozen retest open reads its parent, session and change concurrently without reloading snapshots',async()=>{
 const base=savedScoreView(),retest=structuredClone(base),gets=[],gates=[]
 Object.assign(retest.run,{run_id:'retest-check',run_type:'RETEST',parent_run_id:'run-check',change_id:'change-check'})
 const f=fixture({get:async path=>{
  gets.push(path)
  if(path==='/retrieval-runs/retest-check')return retest
  const value=path==='/retrieval-runs/run-check'?base:path==='/provider-sessions/session-check'?{provider_session_id:'session-check'}:path==='/retrieval-changes/change-check'?{change_id:'change-check'}:null
  assert(value,'Unexpected read '+path)
  return new Promise(resolve=>gates.push(()=>resolve(value)))
 }})
 const opening=f.rag.open('retest-check',{useFrozenControls:true})
 await new Promise(resolve=>setImmediate(resolve))
 assert.equal(gates.length,3);gates.forEach(resolve=>resolve());await opening
 assert.equal(gets.length,4);assert.equal(f.rag.state.baseline.run.run_id,'run-check');assert.equal(f.rag.state.retest.run.run_id,'retest-check')
 assert.equal(f.rag.state.change.change_id,'change-check');assert.equal(f.rag.state.evalSet.retrieval_eval_set_id,'evalset-check')
})
