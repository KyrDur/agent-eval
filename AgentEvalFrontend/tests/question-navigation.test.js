import {test} from 'node:test'
import assert from 'node:assert/strict'
import {questionLabel,selectedQuestion,questionStatus,answerExplanation,questionAnswerOutcome} from '../src/question-navigation.js'

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
test('answer colors use saved answer outcomes and never label retrieval hits as correct',()=>{
 const row={case_id:'a',retrieval_status:'TOP_1_HIT'}
 const view={run:{verify_answers:true,case_results:[row]},effective_answer_results:[{case_id:'a',final_status:'PASS'}]}
 assert.deepEqual(questionAnswerOutcome(view,row),{status:'答对',tone:'pass'})
 view.effective_answer_results[0].final_status='FAIL'
 assert.deepEqual(questionAnswerOutcome(view,row),{status:'答错',tone:'fail'})
 view.run.verify_answers=false
 assert.deepEqual(questionAnswerOutcome(view,row),{status:'未检查回答',tone:'unknown'})
})
test('trusted reviews and incomplete scoring cannot be presented as a correct answer',()=>{
 const row={case_id:'a'},view={run:{verify_answers:true,case_results:[row]},effective_answer_results:[{case_id:'a',final_status:'PASS',execution_status:'SUCCESS'}]}
 view.trusted_result={cases:[{case_id:'a',evaluation_state:'FAIL'}]}
 assert.equal(questionAnswerOutcome(view,row).tone,'fail')
 view.trusted_result.cases[0].evaluation_state='EVIDENCE_INSUFFICIENT'
 assert.deepEqual(questionAnswerOutcome(view,row),{status:'证据不足',tone:'unknown'})
 delete view.trusted_result
 view.effective_answer_results[0].judge_status='FAILED'
 assert.deepEqual(questionAnswerOutcome(view,row),{status:'评分未完成',tone:'unknown'})
 view.effective_answer_results[0]={case_id:'a',final_status:'PASS',execution_status:'FAILED'}
 assert.deepEqual(questionAnswerOutcome(view,row),{status:'执行失败',tone:'unknown'})
})
test('missing results in the selected run remain unexecuted rather than borrowing old answers',()=>{
 const view={run:{verify_answers:true,case_results:[]},effective_answer_results:[{case_id:'a',final_status:'PASS'}]}
 assert.deepEqual(questionAnswerOutcome(view,{case_id:'a'}),{status:'尚未执行',tone:'unknown'})
 assert.deepEqual(questionAnswerOutcome(null,{case_id:'a'}),{status:'尚未评测',tone:'unknown'})
})
test('Judge format failure is labelled scoring failure while a human verdict still takes precedence',()=>{
 const row={case_id:'a'},answer={case_id:'a',execution_status:'SUCCESS',judge_status:'FAILED',final_status:'INVALID',evidence_evaluation:{validation_issues:[{code:'NA_NOT_ALLOWED',field_path:'dimensions.conditions.score',actual:'NA'}]}}
 const view={run:{verify_answers:true,case_results:[row]},effective_answer_results:[answer],trusted_result:{cases:[{case_id:'a',evaluation_state:'EXECUTION_FAILED'}]}}
 assert.equal(questionStatus(view,row),'评分失败')
 assert.match(answerExplanation(answer),/回答已生成.*条件覆盖.*仅重评本题/)
 assert.deepEqual(questionAnswerOutcome(view,row),{status:'评分失败',tone:'unknown'})
 view.trusted_result.cases[0].evaluation_state='PASS'
 assert.equal(questionStatus(view,row),'通过')
 answer.execution_status='FAILED';view.trusted_result.cases[0].evaluation_state='EXECUTION_FAILED'
 assert.equal(questionStatus(view,row),'执行失败')
 assert.match(answerExplanation(answer),/Agent 的回答未完成/)
})
