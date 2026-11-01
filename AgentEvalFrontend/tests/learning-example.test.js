import test from 'node:test'
import assert from 'node:assert/strict'
import {optimizationExamples,optimizationExample,writingExample} from '../src/learning-example.js'
import {changeOptions} from '../src/retrieval-change-options.js'
import {changeMethodPrinciples} from '../src/change-method-principles.js'

test('every supported change has exactly one complete teaching example and matching new marker',()=>{
 assert.equal(new Set(optimizationExamples.map(m=>m.id)).size,optimizationExamples.length)
 assert.deepEqual(optimizationExamples.map(m=>m.id).sort(),changeOptions.map(m=>m.value).sort())
 assert.deepEqual(Object.keys(changeMethodPrinciples).sort(),changeOptions.map(m=>m.value).sort())
 for(const m of optimizationExamples){
  assert.equal(optimizationExample(m.id),m)
  assert.equal(m.added,!!changeOptions.find(option=>option.value===m.id).added)
  for(const field of ['question','policy','evidence','before','after','judgment','quote','cause','check','notFor','beforeLabel','afterLabel','fixed','prediction','potentialCost','decision','reason','limitations'])assert.ok(m[field],`${m.id}: ${field}`)
  assert.equal(m.diagnosis.length,3);assert.equal(m.comparisons.length,3)
  assert.ok(m.beforeItems.length&&m.afterItems.length)
 }
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
test('candidate pool and result count examples teach different controls',()=>{
 const pool=optimizationExample('CANDIDATE_POOL_CHANGE'),topK=optimizationExample('TOP_K_CHANGE')
 assert.match(pool.evidence,/已开启重排/)
 assert.match(pool.beforeLabel,/20.*3/);assert.match(pool.afterLabel,/40.*3/)
 assert.match(pool.fixed,/Top K 固定为 3/)
 assert.match(pool.notFor,/知识库没有/)
 assert.match(topK.fixed,/返回条数 3 → 5/)
})
test('index changes and context expansion keep their scope and costs distinct',()=>{
 const embedding=optimizationExample('EMBEDDING_CHANGE'),chunking=optimizationExample('CHUNKING_CHANGE'),context=optimizationExample('CONTEXT_STRATEGY_CHANGE'),hybrid=optimizationExample('RETRIEVAL_MODE_CHANGE')
 assert.match(embedding.fixed,/回答模型.*不变/);assert.match(embedding.potentialCost,/下载模型和重新编码/)
 assert.match(chunking.fixed,/长度与重叠设置保持不变/);assert.match(chunking.check,/对照索引/)
 assert.match(context.fixed,/原始命中和 Top K 不变/);assert.match(context.cause,/同版本/)
 assert.ok(context.comparisons.some(row=>row.state==='regressed'));assert.match(context.decision,/暂不保留/)
 assert.match(hybrid.fixed,/原文、索引、匹配模型/);assert.match(hybrid.notFor,/不能.*选定/)
})
test('each writing example follows the selected method, while untried changes never claim an improvement',()=>{
 for(const x of optimizationExamples){
  assert.deepEqual(writingExample('judgment',false,x.id),[['你的看法',x.judgment],['引用的原文',x.quote]])
  assert.equal(writingExample('prediction',false,x.id)[0][1],x.prediction)
  assert.ok(writingExample('decision',false,x.id).some(([,t])=>t===x.decision))
  assert.match(writingExample('decision',true,x.id)[0][1],/还没有改后的结果/)
 }
})
