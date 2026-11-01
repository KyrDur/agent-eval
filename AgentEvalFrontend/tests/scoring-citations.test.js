import test from 'node:test'
import assert from 'node:assert/strict'
import {retrievalCitation,retrievalCitationSummary} from '../src/scoring-citations.js'

const rows=[{chunk_id:'refund-a',document_id:'refund',rank:1,text:'质量问题可退运费。'},
 {chunk_id:'points',document_id:'points',rank:2,text:'积分原路返还。'},
 {chunk_id:'refund-b',document_id:'refund',rank:3,text:'退款按原支付路径退回。'}]
const retrieval={top_k:5,results:rows,selected_results:rows}
const docs=[{document_id:'refund',title:'退款规则'},{document_id:'points',title:'积分规则'}]
const cite=(id,quote,scope='RETRIEVED')=>({evidence_id:id,scope,quote})

test('citation order and shared document IDs do not change the recorded chunk rank',()=>{
 const citations=[cite('refund-b','原支付路径'),cite('refund-a','可退运费'),cite('refund-b','退款按原支付路径退回。')]
 assert.deepEqual(citations.map(c=>retrievalCitation(c,retrieval,docs).rank),[3,1,3])
 assert.equal(retrievalCitation(citations[0],retrieval,docs).title,'退款规则')
 assert.equal(retrievalCitation(citations[0],retrieval,docs).label,'检索第 3 条')
 assert.equal(retrievalCitationSummary(retrieval),'本次返回 3 条资料 · Top K = 5')
})
test('reference policy never receives a retrieval rank even when the ID also appears in results',()=>{
 const reference=retrieve=>retrievalCitation(cite('refund-a','可退运费','REFERENCE'),retrieve,docs)
 assert.equal(reference(retrieval).rank,null)
 assert.equal(reference(retrieval).label,'')
})
test('legacy missing or ambiguous records never fabricate a rank from display order or document ID',()=>{
 assert.equal(retrievalCitation(cite('refund','可退运费'),retrieval,docs).rank,null)
 assert.equal(retrievalCitation(cite('refund-a','不存在的内容'),retrieval,docs).rank,null)
 assert.equal(retrievalCitation(cite('refund-a','可退运费'),null,docs).label,'未记录检索排名')
 assert.equal(retrievalCitation(cite('refund-a','可退运费'),{results:[rows[0],rows[0]]},docs).rank,null)
 assert.equal(retrievalCitation(cite('refund-a','可退运费'),{results:[{...rows[0],rank:undefined}]},docs).rank,null)
 assert.equal(retrievalCitationSummary(null),'')
})
test('expanded neighboring context is separate from the selected Top K ranks',()=>{
 const row={top_k:1,selected_results:[rows[2]],results:[{...rows[2],rank:undefined,context_origin:'SELECTED'},
  {...rows[0],context_origin:'EXPANDED'}]}
 // The selected item retains its frozen rank, which must fit the recorded Top K.
 row.selected_results=[{...rows[2],rank:1}]
 assert.equal(retrievalCitation(cite('refund-b','原支付路径'),row,docs).rank,1)
 assert.equal(retrievalCitation(cite('refund-a','可退运费'),row,docs).label,'补充上下文')
 assert.equal(retrievalCitationSummary(row),'本次检索选中 1 条 · Top K = 1 · 实际提供 2 条资料')
})
test('saved ranking survives reranking while candidate ranks and invalid values cannot leak in',()=>{
 const row={top_k:1,results:[rows[1]],selected_results:[{...rows[1],rank:1}],pre_rerank_results:rows}
 assert.equal(retrievalCitation(cite('points','积分'),row,docs).rank,1)
 assert.equal(retrievalCitation(cite('refund-a','运费'),row,docs).rank,null)
 assert.equal(retrievalCitation(cite('points','积分'),{...row,selected_results:[{...rows[1],rank:2}]},docs).rank,null)
 assert.equal(retrievalCitation(cite('points','积分'),{...row,selected_results:[{...rows[1],rank:'1'}]},docs).rank,null)
})
test('zero results, unknown limits and a run-config fallback remain distinct',()=>{
 assert.equal(retrievalCitationSummary({results:[],top_k:5}),'本次返回 0 条资料 · Top K = 5')
 assert.equal(retrievalCitationSummary({results:[rows[0]]}),'本次返回 1 条资料')
 assert.equal(retrievalCitationSummary({results:[rows[0]]},3),'本次返回 1 条资料 · Top K = 3')
})
