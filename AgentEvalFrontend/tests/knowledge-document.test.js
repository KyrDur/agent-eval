import test from 'node:test'
import assert from 'node:assert/strict'
import {knowledgeSections,editKnowledgeSection} from '../src/knowledge-document.js'
const generated=()=>({document_id:'refund',title:'退款规则',text:'核验订单后说明退款。\n保留原段落。\n适用条件：普通商品\n例外：定制商品',metadata:{source:'AI_GENERATED_SIMULATION',generation_id:'generation_1',applicability:'普通商品',exceptions:'定制商品'}})
test('formatted preview preserves the exact retrieval text and provenance',()=>{
 const doc=generated(),before=JSON.stringify(doc)
 assert.deepEqual(knowledgeSections(doc),{body:'核验订单后说明退款。\n保留原段落。',applicability:'普通商品',exceptions:'定制商品'})
 assert.equal(JSON.stringify(doc),before)
})
test('editing sections synchronizes retrieval text and metadata without duplicate headings',()=>{
 const doc=generated()
 editKnowledgeSection(doc,'applicability','未发货的普通商品')
 editKnowledgeSection(doc,'body','核验退款状态。\n不承诺已退款。')
 editKnowledgeSection(doc,'exceptions','已发货需先退货')
 assert.equal(doc.text,'核验退款状态。\n不承诺已退款。\n适用条件：未发货的普通商品\n例外：已发货需先退货')
 assert.equal(doc.metadata.applicability,'未发货的普通商品')
 assert.equal(doc.metadata.exceptions,'已发货需先退货')
 assert.equal(doc.document_id,'refund');assert.equal(doc.metadata.generation_id,'generation_1')
 assert.equal((doc.text.match(/适用条件：/g)||[]).length,1)
})
test('older whole-text edits retain their actual conditions when another section is edited',()=>{
 const doc=generated();doc.text=doc.text.replace('普通商品','会员普通商品')
 assert.equal(knowledgeSections(doc).applicability,'会员普通商品')
 editKnowledgeSection(doc,'exceptions','按实际订单核验')
 assert.equal(doc.metadata.applicability,'会员普通商品')
 assert.ok(doc.text.includes('适用条件：会员普通商品'))
})
test('uploaded prose and embedded section labels are not interpreted as generated schema',()=>{
 const doc={text:'原始资料。\n适用条件：正文的一部分\n例外：也属于原文',metadata:{source:'USER_UPLOADED'}}
 const before=doc.text
 assert.equal(knowledgeSections(doc).body,before)
 editKnowledgeSection(doc,'applicability','另加的说明')
 assert.equal(doc.text,before)
})
