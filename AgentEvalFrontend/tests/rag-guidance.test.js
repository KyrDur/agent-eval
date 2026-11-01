import {test} from 'node:test'
import assert from 'node:assert/strict'
import {caseGuidance,candidateGuidance,factNote,coverageNote} from '../src/rag-guidance.js'
import {explainEvidenceItem} from '../src/evidence-explanation.js'
const view=()=>({run:{verify_answers:false,retrieval_config:{top_k:3,candidate_pool_size:20,rerank:false},case_results:[{case_id:'one',pre_rerank_results:[{},{}],results:[{}],evidence_path:{knowledge:{review_status:'DRAFT',facts:[{fact_id:'time'},{fact_id:'escalate'}]}}}],controls:{index_snapshot:{chunks:[{},{}]},eval_set_snapshot:{cases:[{case_id:'one'}]}}},effective_answer_results:[]})
test('retrieval-only evidence is not presented as an answer or a second-score opportunity',()=>{
 const v=view(),g=caseGuidance(v,'one');assert.equal(g.canCompareAnswer,false);assert.equal(g.reviewed,false);assert.match(g.missingAnswer,/没有生成/)
 assert.match(factNote,/退款超时/);assert.match(coverageNote,/不代表清单没有漏项/)
 v.run.verify_answers=true;v.effective_answer_results=[{case_id:'one',execution_status:'FAILED',turn_evidence:[{response:'partial'}]}]
 assert.equal(caseGuidance(v,'one').canCompareAnswer,false)
 v.effective_answer_results[0].execution_status='SUCCESS';assert.equal(caseGuidance(v,'one').canCompareAnswer,true)
})
test('candidate and final counts explain different effects and show an inapplicable-change warning',()=>{
 const v=view(),pool=candidateGuidance(v,'one','CANDIDATE_POOL_CHANGE',5,40),top=candidateGuidance(v,'one','TOP_K_CHANGE',5,40)
 assert.equal(pool.nextPool,40);assert.equal(pool.nextK,3);assert.equal(top.nextPool,20);assert.equal(top.nextK,5)
 assert.match(pool.caution,/没有开启重排/);assert.match(pool.limitedByCorpus,/全部 2 段/)
 v.run.retrieval_config.retrieval_mode='HYBRID';assert.equal(candidateGuidance(v,'one','CANDIDATE_POOL_CHANGE',5,40).caution,null)
 v.run.retrieval_config={...v.run.retrieval_config,retrieval_mode:'VECTOR',rerank:true};assert.equal(candidateGuidance(v,'one','CANDIDATE_POOL_CHANGE',5,40).caution,null)
})
test('raw missing-reference codes have a plain-language description and next action',()=>{
 const e=explainEvidenceItem('REFERENCE_COMPLETENESS_UNCONFIRMED');assert.match(e.message,/参考答案是否完整/);assert.match(e.nextStep,/测试题/)
 assert.ok(!explainEvidenceItem('SOME_INTERNAL_CODE').message.includes('SOME_INTERNAL_CODE'))
})
