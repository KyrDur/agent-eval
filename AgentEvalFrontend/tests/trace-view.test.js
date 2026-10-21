import test from 'node:test'
import assert from 'node:assert/strict'
import {responseText,parseSavedJson,requestPayload,judgeFormatIssues,traceSteps,preferredTraceStep} from '../src/trace-view.js'

const judgment=()=>({dimensions:Object.fromEntries(['faithfulness','conditions','relevance','actionability'].map(key=>[key,{score:2}]))})
const callFor=data=>({model_outputs:{content:[{type:'text',text:JSON.stringify(data)}]}})
test('Saved output extraction handles legacy, absent and malformed envelopes',()=>{
 assert.equal(responseText({model_outputs:{content:'plain'}}),'plain')
 assert.equal(responseText({model_outputs:{content:{unexpected:true}}}),'')
 assert.equal(responseText({model_outputs:{content:[{type:'tool_use'},null,{type:'text',text:'one'},{type:'text',text:'two'}]}}),'one\ntwo')
 assert.equal(parseSavedJson('not JSON'),null)
 assert.deepEqual(parseSavedJson('```json\n{"a":1}\n```'),{a:1})
})
test('Request inspection uses the saved user message and does not add facts',()=>{
 assert.deepEqual(requestPayload({model_inputs:{messages:[{role:'system',content:'ignore'},{role:'user',content:'{"query":"refund"}'}]}}),{query:'refund'})
 assert.equal(requestPayload({model_inputs:{messages:{bad:true}}}),null)
})
test('Null, string scores and booleans identify exact fields without correcting the result',()=>{
 const data=judgment();data.dimensions.actionability.score=null
 const call=callFor(data),before=JSON.stringify(call),issues=judgeFormatIssues(call)
 assert.equal(issues.length,1);assert.equal(issues[0].path,'dimensions.actionability.score');assert.match(issues[0].message,/null/)
 assert.equal(JSON.stringify(call),before)
 for(const value of ['2',true,false]){data.dimensions.actionability.score=value;assert.equal(judgeFormatIssues(callFor(data)).length,1)}
 for(const value of [0,1,2,'NA','INSUFFICIENT']){data.dimensions.actionability.score=value;assert.deepEqual(judgeFormatIssues(callFor(data)),[])}
})
test('A truncated snapshot does not become evidence of an invalid original response',()=>{
 const data=judgment();data.dimensions.actionability.score=null
 assert.deepEqual(judgeFormatIssues({...callFor(data),output_truncated:true}),[])
})
test('A successful model request can belong to a failed evaluation stage',()=>{
 const calls=[{operation:'ANSWER',status:'SUCCESS',call_id:'answer'},{operation:'JUDGE',status:'SUCCESS',call_id:'judge'}]
 const steps=traceSteps({status:'SUCCESS'},{execution_status:'SUCCESS',judge_status:'FAILED',judge_error:'JUDGMENT_SCHEMA_INVALID'},calls,true)
 assert.equal(preferredTraceStep(steps),'JUDGE');assert.equal(steps[4].status,'FAILED');assert.equal(steps[4].calls[0].status,'SUCCESS');assert.equal(steps[4].calls[0].request_number,2)
})
test('Multiple attempts remain visible in order and legacy role calls are retained',()=>{
 const calls=[{operation:'ANSWER',status:'FAILED'},{operation:'ANSWER',status:'SUCCESS'},{stage:'technical',status:'SUCCESS'}]
 const steps=traceSteps({status:'SUCCESS'},null,calls,true)
 assert.deepEqual(steps.find(s=>s.operation==='ANSWER').calls.map(c=>c.request_number),[1,2])
 assert.equal(steps.find(s=>s.operation==='TECHNICAL').calls.length,1)
})
