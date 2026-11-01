import test from 'node:test'
import assert from 'node:assert/strict'
import {ref} from 'vue'
import {createApi,ApiError,prepareWorkspace} from '../src/api.js'
import {createWorkspace} from '../src/workspace.js'
import {createRetrievalWorkspace} from '../src/retrieval-workspace.js'
import {createEntryStorage,createExperimentEntry} from '../src/experiment-entry.js'

const session={provider_session_id:'saved-session',credential_status:'UNAVAILABLE',configuration:{model:'saved-model'}}
function fixture(fetcher,{timeoutMs=1000,mode='RETRIEVAL',pointers={session:'saved-session'}}={}){
  const values=new Map([['agenteval.workspace.v1',JSON.stringify({step:'setup',session:'saved-session'})],['agenteval.retrieval.v1',JSON.stringify(pointers)]])
  const storage={getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value)}
  const held=createEntryStorage(storage),client=createApi(fetcher)
  const work=createWorkspace(held,client),rag=createRetrievalWorkspace(work,held,client)
  const entry=createExperimentEntry(work,rag,ref(mode),held,{client,timeoutMs})
  return {values,work,rag,entry}
}
const response=(data,ok=true,status=200)=>({ok,status,json:async()=>data})
const healthy=async url=>response(url.endsWith('/retrieval-history')?[]:session)

test('opening the entry performs no historical reads and navigation cannot erase saved pointers',()=>{
  const calls=[],f=fixture(async url=>{calls.push(url);return healthy(url)})
  const before=[...f.values]
  f.work.go('learning');f.rag.persist()
  assert.equal(f.entry.state.pending,true);assert.equal(f.entry.state.hasSaved,true)
  assert.deepEqual(calls,[]);assert.deepEqual([...f.values],before)
})
test('only an explicit resume loads the remembered experiment and preserves an unavailable credential',async()=>{
  const calls=[],f=fixture(async url=>{calls.push(url);return healthy(url)})
  assert.equal(await f.entry.resume(),true)
  assert.equal(f.work.state.session.provider_session_id,'saved-session')
  assert.equal(f.work.state.session.credential_status,'UNAVAILABLE')
  assert.equal(f.entry.state.pending,false)
  assert(!calls.some(path=>/artifacts|ai\/drafts|chat-conversations|calibration/.test(path)))
  f.entry.dispose();f.work.dispose();f.rag.dispose()
})
test('a failed restoration cannot apply partially loaded state or replace remembered pointers',async()=>{
  const f=fixture(async url=>url.endsWith('/retrieval-history')?response([{run_id:'old-run'}]):response({detail:'not_found'},false,404))
  const before=[...f.values]
  assert.equal(await f.entry.resume(),false)
  assert.equal(f.work.state.session,null);assert.deepEqual(f.rag.state.history,[])
  assert.deepEqual([...f.values],before);assert.equal(f.entry.state.pending,true)
  assert.equal(f.entry.state.error.title,'记录无法找到')
})
test('starting fresh cancels recovery; a late response cannot overwrite the new experiment',async()=>{
  let release
  const f=fixture(url=>url.endsWith('/retrieval-history')?new Promise(resolve=>{release=()=>resolve(response([]))}):healthy(url))
  const pending=f.entry.resume()
  f.entry.startFresh()
  assert.equal(await pending,false)
  release();await new Promise(resolve=>setImmediate(resolve))
  assert.equal(f.work.state.session,null);assert.equal(f.rag.state.baseline,null)
  assert.equal(f.work.state.step,'setup');assert.equal(f.entry.state.pending,false)
  assert.equal(f.entry.state.loading,false);assert.equal(f.entry.state.error,null)
  assert.deepEqual(JSON.parse(f.values.get('agenteval.retrieval.v1')),{})
})
test('a stalled read times out, keeps original pointers, and can be retried successfully',async()=>{
  let stalled=true
  const f=fixture(url=>stalled?new Promise(()=>{}):healthy(url),{timeoutMs:15})
  const before=[...f.values]
  assert.equal(await f.entry.resume(),false)
  assert.equal(f.entry.state.error.title,'读取记录超时')
  assert.equal(f.entry.state.loading,false);assert.deepEqual([...f.values],before)
  stalled=false
  assert.equal(await f.entry.resume(),true);assert.equal(f.entry.state.error,null)
  f.entry.dispose()
})
test('cancelling leaves the chooser available without touching the last experiment',async()=>{
  const f=fixture(()=>new Promise(()=>{}))
  const before=[...f.values],pending=f.entry.resume()
  f.entry.cancel();assert.equal(await pending,false)
  assert.equal(f.entry.state.pending,true);assert.equal(f.entry.state.loading,false)
  assert.equal(f.entry.state.error,null);assert.deepEqual([...f.values],before)
})
test('the behavior path also restores only after a choice',async()=>{
  const calls=[],f=fixture(async url=>{
    calls.push(url)
    return response(url.includes('/artifacts/')?{items:[],total:0}:session)
  },{mode:'AGENT_BEHAVIOR'})
  assert.deepEqual(calls,[])
  assert.equal(await f.entry.resume(),true)
  assert(calls.some(url=>url.includes('/artifacts/runs')))
  assert.equal(f.work.state.session.provider_session_id,'saved-session')
  assert(!calls.some(url=>url.includes('/retrieval-history')))
  f.entry.dispose();f.work.dispose()
})
test('a response body that stalls is bounded by the read timeout',async()=>{
  const client=createApi(async()=>({ok:true,status:200,json:()=>new Promise(()=>{})}))
  await assert.rejects(client.get('/retrieval-history',{timeoutMs:10}),error=>error instanceof ApiError&&error.code==='RECORD_READ_TIMEOUT')
})
test('identity initialization can also be cancelled without erasing remembered pointers',async()=>{
  const values=new Map([['agenteval.workspace.v1','remembered']])
  const storage={getItem:key=>values.get(key),setItem:(key,value)=>values.set(key,value)}
  const abort=new AbortController()
  const request=prepareWorkspace(storage,()=>new Promise(()=>{}),{signal:abort.signal})
  abort.abort()
  await assert.rejects(request,ApiError)
  assert.equal(values.get('agenteval.workspace.v1'),'remembered')
})
