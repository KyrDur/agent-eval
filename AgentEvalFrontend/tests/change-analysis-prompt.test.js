import test from 'node:test'
import assert from 'node:assert/strict'
import {proposedChange,changeAnalysisContext,changeAnalysisPrompt,changePlanRecord} from '../src/change-analysis-prompt.js'
const fixture=()=>({run:{run_id:'base-1',run_type:'BASELINE',status:'COMPLETE',verify_answers:true,provider_configuration_snapshot:{api_key:'NEVER_EXPORT_CONFIG_SECRET'},retrieval_config:{top_k:3,query_rewrite:false,rerank:false,candidate_pool_size:20,answer_prompt:'原回答提示'},case_results:[{case_id:'one',query:'有质量问题退货，运费谁出？',effective_query:'质量问题退货运费',status:'SUCCESS',relevant_document_ids:['returns'],metrics:{relevant_rank:4,returned_relevant_rank:null},results:[{chunk_id:'logistics-1',document_id:'logistics',rank:1,text:'配送资料',metadata:{api_key:'NEVER_EXPORT_METADATA_SECRET'}}],pre_rerank_results:[{chunk_id:'returns-1',document_id:'returns',rank:4,text:'质量问题退货，运费由商家承担。'}],input_package:{reference_complete:true,missing_items:[],truncated_items:[],necessary_history:[{role:'user',content:'这是刚买的书桌。'}],evidence:[{evidence_id:'P1',document_id:'returns',scope:'REFERENCE',text:'质量问题退货，运费由商家承担。'}]}},{case_id:'two',query:'UNRELATED_CASE_QUESTION',results:[]}],controls:{eval_set_snapshot:{cases:[{case_id:'one',expected_answer:'说明商家承担。'},{case_id:'two',expected_answer:'UNRELATED_EXPECTED'}]},knowledge_snapshot:{version:1,documents:[{document_id:'returns',text:'质量问题退货，运费由商家承担。'}]},index_snapshot:{index_id:'idx1',knowledge_dataset_id:'kb',knowledge_version:1,chunk_config:{chunk_size:200,chunk_overlap:20},embedding_snapshot:{model:'fixed'}}}},effective_answer_results:[{case_id:'one',execution_status:'SUCCESS',judge_status:'SUCCESS',original_status:'FAIL',original_reason:'没有回答运费承担方。',turn_evidence:[{response:'无法确认运费。'}]},{case_id:'two',turn_evidence:[{response:'UNRELATED_CASE_ANSWER'}]}]})
const options=(extra={})=>({view:fixture(),caseId:'one',type:'TOP_K_CHANGE',nextK:5,...extra})

test('prepared prompt is scoped to the selected saved question and excludes credentials and other cases',()=>{
 const p=changeAnalysisPrompt(options())
 for(const value of ['有质量问题退货，运费谁出？','无法确认运费','质量问题退货，运费由商家承担','3 → 5','不要预设它正确'])assert.ok(p.includes(value),value)
 for(const value of ['NEVER_EXPORT_CONFIG_SECRET','NEVER_EXPORT_METADATA_SECRET','UNRELATED_CASE_QUESTION','UNRELATED_CASE_ANSWER','UNRELATED_EXPECTED'])assert.ok(!p.includes(value),value)
 assert.ok(p.includes('这是刚买的书桌。'))
})
test('there is no fallback to another question when the requested case is missing',()=>{assert.equal(changeAnalysisPrompt(options({caseId:'missing'})),'');assert.equal(changeAnalysisContext(options({type:'UNKNOWN'})),null)})
test('a numeric change preserves every other setting and rejects an unchanged or invalid value',()=>{
 const o=options(),before=structuredClone(o.view)
 const p=proposedChange(o);assert.equal(p.valid,true);assert.deepEqual(p.afterConfig,{...o.view.run.retrieval_config,top_k:5});assert.deepEqual(o.view,before)
 for(const n of [3,0,21,4.5,undefined])assert.equal(proposedChange(options({nextK:n})).valid,false)
})
test('turning rewrite or rerank on/off changes only the selected switch',()=>{
 for(const [type,field] of [['QUERY_REWRITE_TOGGLE','query_rewrite'],['RERANK_TOGGLE','rerank']]){
  const o=options({type});assert.deepEqual(proposedChange(o).afterConfig,{...o.view.run.retrieval_config,[field]:true})
  o.view.run.retrieval_config[field]=true;assert.equal(proposedChange(o).afterConfig[field],false)
 }
})
test('prompt change includes the actual before and candidate text, with grading held constant',()=>{
 const o=options({type:'ANSWER_PROMPT_CHANGE',answerPrompt:'先核对适用条件再回答。'}),c=changeAnalysisContext(o)
 assert.equal(c.回答提示词.原版本,'原回答提示');assert.equal(c.回答提示词.拟用版本,o.answerPrompt);assert.match(c.回答提示词.评分标准,/保持原来的评分标准/)
 assert.equal(proposedChange({...o,answerPrompt:'原回答提示'}).valid,false);assert.equal(proposedChange({...o,answerPrompt:''}).valid,false)
})
test('absent candidate details and clipped context remain explicit, never invented evidence',()=>{
 const o=options();o.view.run.case_results[0].pre_rerank_results=[];o.view.effective_answer_results[0].turn_evidence[0].response='长'.repeat(10001)
 const c=changeAnalysisContext(o);assert.equal(c.证据范围.原记录没有候选详情,true);assert.deepEqual(c.本轮检索记录.原候选,[]);assert.match(c.Agent原回答,/此处有截断/);assert.ok(c.本次提问的内容边界.some(x=>x.includes('Agent 原回答')))
})
test('score execution failure and missing reference completeness stay visible to the external analyst',()=>{
 const o=options();o.view.effective_answer_results[0].judge_status='FAILED';o.view.effective_answer_results[0].evaluation_error='SCHEMA_INVALID';o.view.run.case_results[0].input_package.reference_complete=false
 const c=changeAnalysisContext(o);assert.equal(c.已保存判定.评分执行状态,'FAILED');assert.equal(c.已保存判定.评分错误,'SCHEMA_INVALID');assert.equal(c.证据范围.参考是否完整,false)
})
test('knowledge context does not claim old documents were deleted when the new version was not loaded',()=>{
 const o=options({type:'KNOWLEDGE_UPDATE',index:{index_id:'idx2',knowledge_dataset_id:'kb',knowledge_version:2,chunk_config:{chunk_size:200,chunk_overlap:20},embedding_snapshot:{model:'fixed'}}})
 assert.equal(proposedChange(o).valid,true);const c=changeAnalysisContext(o);assert.equal(c.知识更新.删除的文档,'无法核对');assert.match(c.知识更新.新增或修改的文档,/未读取/)
 o.knowledge={knowledge_dataset_id:'kb',version:2,documents:[{document_id:'returns',text:'补充后的质量问题退货规则'}]};assert.equal(changeAnalysisContext(o).知识更新.新增或修改的文档.length,1)
 o.index.chunk_config.chunk_size=400;assert.equal(proposedChange(o).valid,false)
})
test('saving an empty optional note records a proposed experiment, not a fabricated personal diagnosis',()=>{
 const text=changePlanRecord(options())
 assert.match(text,/系统按已保存记录与所选设置整理/);assert.match(text,/不是独立根因分析/);assert.match(text,/尚未形成根因结论或备选方案比较/);assert.match(text,/3 → 5/);assert.doesNotMatch(text,/用户补充/)
 const withAI=changePlanRecord(options(),'AI 认为要加资料',{id:'draft',text:'可能是排序问题'})
 assert.match(withAI,/可能含 AI 建议/);assert.match(withAI,/待核对节选/);assert.ok(withAI.length<3000)
})

test('new retrieval interventions each preserve all unselected settings',()=>{
 for(const [type,extra,field,value] of [
  ['RETRIEVAL_MODE_CHANGE',{retrievalMode:'BM25'},'retrieval_mode','BM25'],
  ['CONTEXT_STRATEGY_CHANGE',{contextStrategy:'NEIGHBORS'},'context_strategy','NEIGHBORS'],
  ['CANDIDATE_POOL_CHANGE',{candidatePool:40},'candidate_pool_size',40],
 ]){
  const o=options({type,...extra}),p=proposedChange(o)
  assert.equal(p.valid,true);assert.deepEqual(p.afterConfig,{...o.view.run.retrieval_config,[field]:value})
  const text=changeAnalysisPrompt(o);assert.ok(text.includes(p.summary));assert.ok(!text.includes('NEVER_EXPORT'))
 }
 assert.equal(proposedChange(options({type:'RETRIEVAL_MODE_CHANGE',retrievalMode:'VECTOR'})).valid,false)
 assert.equal(proposedChange(options({type:'CONTEXT_STRATEGY_CHANGE',contextStrategy:'PARENT'})).valid,false)
 assert.equal(proposedChange(options({type:'CANDIDATE_POOL_CHANGE',candidatePool:20})).valid,false)
 assert.equal(proposedChange(options({type:'CANDIDATE_POOL_CHANGE',candidatePool:40.5})).valid,false)
})

test('index plans bind the exact compatible candidate and reject a second factor',async()=>{
 const {compatibleChangeIndices}=await import('../src/change-analysis-prompt.js')
 const o=options({type:'EMBEDDING_CHANGE'}),old=o.view.run.controls.index_snapshot
 Object.assign(old,{knowledge_hash:'same-policy',chunks:[{chunk_id:'stable',text:'policy'}]})
 const next={...structuredClone(old),index_id:'bge',embedding_snapshot:{model:'chinese',index_generation:'new'}}
 assert.equal(proposedChange({...o,index:next}).valid,true)
 assert.equal(proposedChange({...o,index:next}).targetIndexId,'bge')
 assert.deepEqual(compatibleChangeIndices(o.view,o.type,[old,next,{...next,knowledge_version:2},{...next,chunk_config:{chunk_size:500}},{...next,chunks:[]}]).map(i=>i.index_id),['bge'])
 const chunk={...structuredClone(old),index_id:'section',chunk_config:{...old.chunk_config,algorithm:'source-section-v1'},chunks:[{chunk_id:'new'}]}
 assert.equal(proposedChange({...o,type:'CHUNKING_CHANGE',index:chunk}).valid,true)
 assert.equal(proposedChange({...o,type:'CHUNKING_CHANGE',index:{...chunk,embedding_snapshot:{model:'chinese'}}}).valid,false)
})

test('evidence guidance distinguishes unknown knowledge from a loss after candidate recall',async()=>{
 const {changeEvidenceSummary,changeOptions,groupedChangeOptions}=await import('../src/retrieval-change-options.js')
 assert.equal(new Set(changeOptions.map(o=>o.value)).size,10)
 assert.equal(groupedChangeOptions.flatMap(g=>g.options).length,10)
 const v=fixture();assert.match(changeEvidenceSummary(v,'one').observation,/尚未审核/)
 assert.equal(changeEvidenceSummary(v,'one').stages[0].text,'本次未记录')
 v.run.case_results[0].evidence_path={knowledge:{status:'FULL'},candidates:{status:'FULL'},context:{status:'PARTIAL'}}
 assert.match(changeEvidenceSummary(v,'one').observation,/已进入候选/)
 assert.match(changeEvidenceSummary(v,'one').observation,/尚不能确认唯一原因/)
})
