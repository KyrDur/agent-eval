import {test} from 'node:test'
import assert from 'node:assert/strict'
import {questionLabel,selectedQuestion,questionStatus,answerExplanation} from '../src/question-navigation.js'

test('Question numbering stays readable at ten, twenty and larger sets',()=>{
 for(const [n,label] of [[1,'第一题'],[8,'第八题'],[10,'第十题'],[11,'第十一题'],[20,'第二十题'],[21,'第二十一题'],[100,'第100题']])assert.equal(questionLabel(n),label)
})
test('Selection retains the requested question and falls back after removal or a run change',()=>{
 const items=[{case_id:'a'},{case_id:'b'}]
 assert.equal(selectedQuestion(items,'b'),items[1])
 assert.equal(selectedQuestion(items,'old'),items[0])
 assert.equal(selectedQuestion([],'a'),null)
})
test('Retrieval success cannot become an answer pass or override a trusted failure',()=>{
 const row={case_id:'a',retrieval_status:'TOP_1_HIT'}
 assert.equal(questionStatus({run:{verify_answers:true},effective_answer_results:[]},row),'待判断')
 assert.equal(questionStatus({run:{verify_answers:true},effective_answer_results:[{case_id:'a',final_status:'PASS'}],trusted_result:{cases:[{case_id:'a',evaluation_state:'EVIDENCE_INSUFFICIENT'}]}},row),'证据不足')
 assert.equal(questionStatus({run:{verify_answers:false}},row),'已找到')
})
test('A scoring execution error has an actionable explanation and preserves valid reasons',()=>{
 assert.match(answerExplanation({judge_status:'FAILED',original_reason:'JUDGMENT_SCHEMA_INVALID'}),/评分未完成.*运行日志/)
 assert.equal(answerExplanation({execution_status:'SUCCESS',judge_status:'SUCCESS',original_reason:'回答遗漏了退货条件。'}),'回答遗漏了退货条件。')
})
