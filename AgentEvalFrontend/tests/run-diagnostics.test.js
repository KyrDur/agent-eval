import test from 'node:test'
import assert from 'node:assert/strict'
import {diagnoseCase,diagnosticSteps,tokenSummary,callUsage,elapsed} from '../src/run-diagnostics.js'

test('unknown old usage and missing provider usage are distinct from measured zeros',()=>{
 assert.equal(tokenSummary([],false).text,'历史未记录')
 assert.equal(tokenSummary([],true).text,'未调用模型')
 assert.equal(tokenSummary([{stage:'general'}]).text,'历史未记录')
 assert.equal(tokenSummary([{trace_version:1,usage:null}]).text,'提供商未提供')
 assert.deepEqual(callUsage({usage:{input_tokens:0,output_tokens:0}}),{input:0,output:0,total:0})
 assert.equal(elapsed(null),'未记录')
})
test('partial token coverage does not pretend to be the total for every call',()=>{
 const result=tokenSummary([{trace_version:1,usage:{input_tokens:12,output_tokens:3}},{trace_version:1,usage:null}])
 assert.equal(result.known,15);assert.equal(result.missing,1);assert.match(result.text,/用量缺失/)
})
test('failed Judge is not treated as answer quality failure',()=>{
 const diagnosis=diagnoseCase({status:'SUCCESS',metrics:{recall_at_k:1}},{execution_status:'SUCCESS',judge_status:'FAILED',original_status:'INVALID'},true)
 assert.equal(diagnosis.kind,'judge_error')
})
test('candidate outside Top K differs from missing knowledge and absent labels',()=>{
 assert.equal(diagnoseCase({status:'SUCCESS',top_k:3,metrics:{recall_at_k:0,relevant_rank:5}}).kind,'outside_k')
 assert.equal(diagnoseCase({status:'SUCCESS',metrics:{recall_at_k:0,relevant_rank:null}}).kind,'not_retrieved')
 assert.equal(diagnoseCase({status:'SUCCESS',metrics:{unavailable_reason:'NO_RELEVANCE_LABELS'}}).kind,'labels')
})
test('disabled stage differs from a stage blocked by an earlier failure',()=>{
 const steps=diagnosticSteps({status:'INVALID',rerank_enabled:true,rerank_status:'NOT_REQUIRED',
  steps:[{operation:'QUERY_REWRITE',status:'FAILED',latency_ms:20,error:'TIMEOUT'}]},null,[],true)
 assert.equal(steps[0].status,'FAILED');assert.equal(steps[1].status,'NOT_RUN');assert.equal(steps[2].status,'NOT_RUN')
 assert.equal(diagnosticSteps({status:'SUCCESS',rerank_status:'NOT_REQUIRED'},null,[],false)[2].status,'SKIPPED')
})
test('retrieval-only and ungraded chat do not claim answer quality passed',()=>{
 assert.equal(diagnoseCase({status:'SUCCESS',metrics:{recall_at_k:1}},null,false).kind,'retrieval_only')
 assert.equal(diagnoseCase({status:'SUCCESS'},{execution_status:'SUCCESS',judge_status:'NOT_REQUIRED'},true,'chat').kind,'ungraded')
})
test('successful model response with invalid Judge JSON still fails the evaluation step',()=>{
 const steps=diagnosticSteps({status:'SUCCESS'},{execution_status:'SUCCESS',judge_status:'FAILED',judge_error:'INVALID_JUDGE_JSON'},
  [{operation:'JUDGE',status:'SUCCESS',latency_ms:20}],true)
 assert.equal(steps[4].status,'FAILED');assert.equal(steps[4].error,'INVALID_JUDGE_JSON')
 assert.equal(steps[4].latency_ms,20);assert.equal(steps[4].timing_scope,'MODEL_CALLS')
})
