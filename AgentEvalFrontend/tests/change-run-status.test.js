import test from 'node:test'
import assert from 'node:assert/strict'
import {changeRunBlocker} from '../src/change-run-status.js'
const ready={credential_status:'PRESENT',text_connection_status:'READY'}
const base={type:'ANSWER_PROMPT_CHANGE',session:ready,plan:{valid:true}}
test('an unchanged answer prompt explains which control to use, and an actual change clears the blocker',()=>{
 const blocker=changeRunBlocker({...base,plan:{valid:false,problem:'回答提示词还没有变化。'}})
 assert.match(blocker.title,/还没有改动回答规则/);assert.match(blocker.detail,/勾选/);assert.equal(blocker.action,'settings')
 assert.equal(changeRunBlocker(base),null)
})
test('lost model or judge connectivity has a recovery action even when the plan is valid',()=>{
 for(const session of [null,{...ready,credential_status:'MISSING'},{...ready,text_connection_status:'FAILED'},{...ready,judge_connection:{available:false}}])assert.equal(changeRunBlocker({...base,session}).action,'connect')
})
test('a pending index receipt gives a read-progress action instead of asking for another build',()=>{
 const blocker=changeRunBlocker({...base,type:'CHUNKING_CHANGE',indexJob:{status:'UNKNOWN'},plan:{valid:false}})
 assert.equal(blocker.action,'read-index');assert.match(blocker.detail,/读取/)
})
test('automatic index preparation remains runnable without requiring a manually selected index',()=>{
 for(const type of ['CHUNKING_CHANGE','EMBEDDING_CHANGE'])assert.equal(changeRunBlocker({...base,type,plan:{valid:false}}),null)
})
test('old chunk bindings have an explanation and cannot be used for an incompatible knowledge change',()=>{
 const blocker=changeRunBlocker({...base,type:'KNOWLEDGE_UPDATE',index:{index_id:'new'},chunkBound:true})
 assert.equal(blocker.action,'tests');assert.match(blocker.title,/旧资料片段/)
})
test('busy, locked and loading states explain the real reason instead of suggesting a parameter change',()=>{
 assert.equal(changeRunBlocker({...base,busy:true}).tone,'info')
 assert.equal(changeRunBlocker({...base,locked:true}).action,'return')
 const input={...base,type:'KNOWLEDGE_UPDATE',index:{index_id:'new'}}
 assert.match(changeRunBlocker({...input,indexLoading:true}).title,/读取/)
 assert.equal(changeRunBlocker({...input,indexLoading:false}),null)
})
test('knowledge still needing a supplement points to the AI action',()=>{
 const blocker=changeRunBlocker({...base,type:'KNOWLEDGE_UPDATE',plan:{valid:false}})
 assert.equal(blocker.action,'settings');assert.match(blocker.detail,/AI 整理并补充到知识库/)
})
