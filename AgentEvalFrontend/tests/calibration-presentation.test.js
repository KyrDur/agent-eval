import test from 'node:test'
import assert from 'node:assert/strict'
import {newJudgment,verdictFor,judgmentProblems,localFragments,labelFor} from '../src/calibration-presentation.js'

const rubric={rules:{minimum_scores:{faithfulness:2,conditions:2,relevance:1,actionability:1},na_allowed:['actionability']}}
const sample={answer:'**已过期**优惠券不恢复。',retrieved_evidence:[{evidence_id:'r',text:'已过期优惠券不恢复。'}],reference_policy:[{evidence_id:'p',text:'已过期优惠券不恢复。'}],reference_complete:true}
test('numeric human judgments require answer and correctly scoped evidence, honest behavior does not complete the task',()=>{
  const value=newJudgment()
  for(const d of Object.values(value.dimensions)){d.score=2;d.reason='Fixture reason'}
  value.reason='Fixture only';value.task_resolved='NO';value.faithful_to_available='YES'
  assert.ok(judgmentProblems(value,sample,rubric).some(s=>s.includes('当时检索资料')))
  assert.ok(judgmentProblems(value,sample,rubric).some(s=>s.includes('完整参考政策')))
  for(const [key,d] of Object.entries(value.dimensions)){
    d.answer_quotes=[sample.answer]
    d.citations=[{scope:key==='faithfulness'?'RETRIEVED':'REFERENCE',evidence_id:key==='faithfulness'?'r':'p',quote:'已过期优惠券不恢复。'}]
  }
  assert.deepEqual(judgmentProblems(value,sample,rubric),[])
  value.dimensions.conditions.score=0
  assert.equal(verdictFor(value,rubric),'FAIL')
  assert.equal(value.faithful_to_available,'YES')
  assert.equal(value.task_resolved,'NO')
})
test('insufficient information requires an explanation and severe errors dominate the rule',()=>{
  const value=newJudgment();value.reason='No reference'
  for(const d of Object.values(value.dimensions))d.reason='Missing source'
  assert.ok(judgmentProblems(value,sample,rubric).some(s=>s.includes('缺少什么资料')))
  value.insufficient_items=['Missing policy'];assert.deepEqual(judgmentProblems(value,sample,rubric),[])
  assert.equal(verdictFor(value,rubric),'PENDING')
  value.critical_errors=['UNSUPPORTED_PROMISE'];assert.equal(verdictFor(value,rubric),'FAIL')
})
test('human quote fragments preserve exact text including markdown and distinguish evidence scopes',()=>{
  const fragments=localFragments(sample)
  assert.equal(fragments[0].text,sample.answer)
  assert.deepEqual(fragments.map(f=>f.scope),['ANSWER','RETRIEVED','REFERENCE'])
  assert.equal(labelFor('CONTENT_INVALID'),'评分依据校验失败')
})
