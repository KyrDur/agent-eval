import test from 'node:test'
import assert from 'node:assert/strict'
import {optimizationExamples,optimizationExample,writingExample} from '../src/learning-example.js'

test('five teaching methods match the actual supported change types',()=>{
 assert.deepEqual(optimizationExamples.map(m=>m.id),['RERANK_TOGGLE','QUERY_REWRITE_TOGGLE','TOP_K_CHANGE','ANSWER_PROMPT_CHANGE','KNOWLEDGE_UPDATE'])
 for(const m of optimizationExamples){assert.equal(optimizationExample(m.id),m);assert.ok(m.fixed&&m.notFor&&m.decision&&m.limitations);assert.equal(m.comparisons.length,3)}
})
test('reranking changes order without adding candidates or changing the number supplied',()=>{
 const x=optimizationExample('RERANK_TOGGLE')
 assert.deepEqual(x.beforeItems.map(i=>i.text).sort(),x.afterItems.map(i=>i.text).sort())
 assert.equal(x.beforeItems.filter(i=>i.used).length,2);assert.equal(x.afterItems.filter(i=>i.used).length,2)
 assert.equal(x.beforeItems.find(i=>i.relevant).used,undefined);assert.equal(x.afterItems.find(i=>i.relevant).used,true)
})
test('changing result count preserves order and demonstrates a regression with a non-adoption decision',()=>{
 const x=optimizationExample('TOP_K_CHANGE')
 assert.deepEqual(x.beforeItems.map(i=>i.text),x.afterItems.map(i=>i.text))
 assert.equal(x.beforeItems.filter(i=>i.used).length,3);assert.equal(x.afterItems.filter(i=>i.used).length,5)
 assert.ok(x.comparisons.some(c=>c.state==='regressed'));assert.match(x.decision,/暂不保留/)
})
test('knowledge addition preserves the original documents and identifies the added business source',()=>{
 const x=optimizationExample('KNOWLEDGE_UPDATE')
 assert.deepEqual(x.afterItems.slice(0,x.beforeItems.length),x.beforeItems)
 assert.match(x.afterItems.at(-1).text,/已确认来源/);assert.match(x.notFor,/正确答案也变了/)
})
test('each writing example follows the selected method, while untried changes never claim an improvement',()=>{
 for(const x of optimizationExamples){
  assert.deepEqual(writingExample('judgment',false,x.id),[['你的看法',x.judgment],['引用的原文',x.quote]])
  assert.equal(writingExample('prediction',false,x.id)[0][1],x.prediction)
  assert.ok(writingExample('decision',false,x.id).some(([,t])=>t===x.decision))
  assert.match(writingExample('decision',true,x.id)[0][1],/还没有改后的结果/)
 }
})
