import {test} from 'node:test'
import assert from 'node:assert/strict'
import {confirmGeneratedEvidence,requiresPolicyReference} from '../src/ai-assistance.js'
test('AI draft acceptance requires an explicit policy-coverage confirmation and leaves its source intact',()=>{
 const original=[{case_id:'policy',reference_complete:null,generation:{question_type:'常规'}}]
 assert.throws(()=>confirmGeneratedEvidence(original,false),/核对/)
 const accepted=confirmGeneratedEvidence(original,true)
 assert.equal(accepted[0].reference_complete,true)
 assert.equal(accepted[0].reference_completeness.method,'USER_CONFIRMED_POLICY_COVERAGE')
 assert.equal(original[0].reference_complete,null)
})
test('An out-of-knowledge question checks honest fallback without claiming a complete policy',()=>{
 const [accepted]=confirmGeneratedEvidence([{case_id:'outside',reference_complete:null,generation:{question_type:'知识范围外'}}],true)
 assert.equal(accepted.reference_complete,null)
 assert.equal(accepted.scenario_rules.template_id,'MISSING_KNOWLEDGE')
 assert.equal(requiresPolicyReference(accepted),false)
})
test('A known evidence gap cannot be overwritten by bulk confirmation',()=>{
 assert.throws(()=>confirmGeneratedEvidence([{reference_complete:false}],true),/已知的政策缺口/)
})
test('Clarification, handoff and refusal use their declared evidence requirements',()=>{
 assert.equal(requiresPolicyReference({}),true)
 for(const expected_behavior of ['CLARIFY','HANDOFF','REFUSE'])assert.equal(requiresPolicyReference({scenario_rules:{expected_behavior}}),false)
 assert.equal(requiresPolicyReference({scenario_rules:{template_id:'CLARIFICATION'}}),false)
})
