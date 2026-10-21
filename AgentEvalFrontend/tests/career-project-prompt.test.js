import test from 'node:test'
import assert from 'node:assert/strict'
import {careerProjectContext,careerProjectPrompt} from '../src/career-project-prompt.js'

function fixture(){
 const cases=[{case_id:'shipping',query:'质量问题退货运费谁出？',source:'ai_generated',expected_answer:'商家承担。'},{case_id:'warranty',query:'保修多久？',source:'user_created'},{case_id:'spec',query:'桌面是什么材质？',source:'platform_preset'}]
 const result=(id,status)=>({case_id:id,execution_status:'SUCCESS',judge_status:status==='INVALID'?'FAILED':'SUCCESS',evaluation_error:status==='INVALID'?'JUDGMENT_SCHEMA_INVALID':null,original_status:status,final_status:status,original_reason:status==='FAIL'?'遗漏运费责任。':'已保存判定',turn_evidence:[{response:'已保存的回答 '+id}],metadata:{api_key:'NEVER_EXPORT_RESULT_METADATA'}})
 const base={run:{run_id:'base',run_type:'BASELINE',status:'COMPLETE',verify_answers:true,provider_configuration_snapshot:{api_key:'NEVER_EXPORT_PROVIDER_SECRET'},retrieval_config:{top_k:3,candidate_pool_size:20,query_rewrite:false,rerank:false},execution_order:cases.map(c=>c.case_id),case_results:cases.map(c=>({case_id:c.case_id,query:c.query,results:[{document_id:'returns',chunk_id:'chunk1',text:'质量问题商家承担退货运费。',metadata:{secret:'NEVER_EXPORT_CHUNK_METADATA'}}]})),controls:{eval_set_snapshot:{cases},knowledge_snapshot:{version:1,documents:[{document_id:'returns',title:'退货政策',text:'质量问题商家承担退货运费。'}]},index_snapshot:{chunk_config:{chunk_size:200,chunk_overlap:20},embedding_snapshot:{model:'fixed'}}}},effective_answer_results:[result('shipping','FAIL'),result('warranty','PASS'),result('spec','INVALID')]}
 return {kind:'RETRIEVAL',experiment:{baseline:base},conclusions:[]}
}
function change(){return {change_id:'change',baseline_run_id:'base',change_type:'TOP_K_CHANGE',implemented_status:'PROPOSED',selected_case_ids:['shipping'],reason:'系统整理的待验证方案',before_config:{top_k:3,candidate_pool_size:20,query_rewrite:false,rerank:false},after_config:{top_k:5,candidate_pool_size:20,query_rewrite:false,rerank:false}}}
function addAfter(o){
 o.experiment.change=change();o.experiment.change.implemented_status='APPLIED'
 o.experiment.retest=structuredClone(o.experiment.baseline)
 Object.assign(o.experiment.retest.run,{run_id:'after',run_type:'RETEST',parent_run_id:'base',change_id:'change'})
 o.experiment.retest.run.retrieval_config.top_k=5
 o.experiment.retest.run.controls.knowledge_snapshot.version=2
 o.experiment.comparison={comparison_id:'comparison',baseline_run_id:'base',retest_run_id:'after',comparable:true,comparison_completeness:'PARTIAL',single_recorded_change:true,attributable:false,case_pairs:[{case_id:'shipping',answer_transition:'FAIL→PASS'}]}
}

test('project prompt is ready from a saved initial run without creating career artifacts',()=>{
 assert.equal(careerProjectContext(),null);assert.equal(careerProjectPrompt(), '')
 const o=fixture(),before=structuredClone(o),c=careerProjectContext(o)
 assert.equal(c.项目设定.我的角色,'产品设计');assert.match(c.项目设定.实践工作台的目标用户,/18–24/)
 assert.equal(c.原始初测.已保存题目数,3);assert.equal(c.原始初测.有效判定题数,2)
 assert.equal(c.原始初测.通过率分子,1);assert.equal(c.原始初测.通过率分母,2)
 assert.equal(c.原始初测.各类结果数量.执行失败,1);assert.equal(c.已保存的修改,null)
 assert.match(c.复测,/尚无对应复测/);assert.deepEqual(o,before)
})
test('prompt explicitly asks for Nowcoder research, original links, drafts and honest ownership',()=>{
 const p=careerProjectPrompt(fixture())
 for(const value of ['到牛客（nowcoder.com）','AI 产品经理 校招 实习 项目经历','原文链接','不能联网','不要先让我重新整理记录','约 2 分钟','3 个最可能的追问','有效判定分母','不能把别人做过的功能','预设或 AI 生成的题目不写成我独立设计'])assert.ok(p.includes(value),value)
})
test('export whitelists saved records without sessions, arbitrary metadata or unrelated history',()=>{
 const o=fixture();o.experiment.session={api_key:'NEVER_EXPORT_CURRENT_SESSION'}
 o.experiment.history=[{text:'NEVER_EXPORT_OTHER_RUN'}]
 o.evidence={baseline_run_id:'other',context:{user_contribution:'NEVER_EXPORT_OLD_CONTEXT'}}
 const p=careerProjectPrompt(o)
 for(const token of ['NEVER_EXPORT_PROVIDER_SECRET','NEVER_EXPORT_RESULT_METADATA','NEVER_EXPORT_CHUNK_METADATA','NEVER_EXPORT_CURRENT_SESSION','NEVER_EXPORT_OTHER_RUN','NEVER_EXPORT_OLD_CONTEXT'])assert.ok(!p.includes(token),token)
 assert.ok(p.includes('质量问题退货运费谁出？'));assert.ok(p.includes('已保存的回答 shipping'))
})
test('retrieval-only evaluation never becomes answer quality results',()=>{
 const o=fixture();o.experiment.baseline.run.verify_answers=false;o.experiment.baseline.effective_answer_results=[]
 o.experiment.baseline.trusted_result={cases:[{case_id:'shipping',evaluation_state:'PASS'}]}
 const c=careerProjectContext(o)
 assert.equal(c.原始初测.通过率分母,0);assert.equal(c.原始初测.各类结果数量.未检查回答,3)
})
test('a proposed change is not recorded as applied or tested',()=>{
 const o=fixture();o.experiment.change=change()
 const c=careerProjectContext(o)
 assert.match(c.已保存的修改.应用状态,/尚未应用/);assert.equal(c.已保存的修改.修改前.返回资料条数,3);assert.equal(c.已保存的修改.修改后.返回资料条数,5)
 assert.equal(c.已保存的修改.是否在本次复测中使用,false)
 assert.deepEqual(c.已保存的操作.map(s=>s.操作),['运行初测并保存过程','保存修改方案'])
})
test('matched comparison keeps limits, real knowledge versions and only its confirmed conclusions',()=>{
 const o=fixture();addAfter(o)
 o.conclusions=[{comparison_id:'comparison',decision:'REVISE',reason:'需要继续检查退化',user_confirmed:true,decision_scope:'LIMITED_OBSERVATION'},{comparison_id:'other',reason:'NEVER_BORROW_OTHER_CONCLUSION',user_confirmed:true}]
 const c=careerProjectContext(o)
 assert.equal(c.前后比较.可否因果归因,false);assert.equal(c.前后比较.范围是否完整,'不完整')
 assert.equal(c.原始初测.知识版本,1);assert.equal(c.复测.知识版本,2)
 assert.equal(c.已保存的修改.是否在本次复测中使用,true);assert.equal(c.已保存的本人结论.length,1)
 assert.equal(c.已保存的本人结论[0].适用范围,'局部观察')
 assert.ok(!careerProjectPrompt(o).includes('NEVER_BORROW_OTHER_CONCLUSION'))
})
test('stale retest, comparison and career completions cannot leak into the current project',()=>{
 const o=fixture();addAfter(o);o.experiment.retest.run.parent_run_id='other'
 o.evidence={evidence_object_id:'old',baseline_run_id:'base',experiment_type:'RETRIEVAL',retest_run_id:'after',comparison_id:'comparison'}
 o.careerView={evidence_object_id:'old',completions:[{text:'NEVER_BORROW_STALE_JUDGMENT'}]}
 const c=careerProjectContext(o)
 assert.equal(typeof c.复测,'string');assert.equal(typeof c.前后比较,'string');assert.deepEqual(c.已保存的个人补充,[])
 assert.ok(c.缺少的记录.some(x=>x.includes('不属于所选初测')));assert.ok(!careerProjectPrompt(o).includes('NEVER_BORROW_STALE_JUDGMENT'))
})
test('new prompt settings and reused historical personal notes remain explicitly scoped',()=>{
 const o=fixture();o.experiment.change={...change(),change_type:'ANSWER_PROMPT_CHANGE',before_config:{answer_prompt:'旧要求'},after_config:{answer_prompt:'新要求'}}
 o.evidence={evidence_object_id:'same',baseline_run_id:'base',experiment_type:'RETRIEVAL',retest_run_id:null,comparison_id:null}
 o.careerView={evidence_object_id:'same',completions:[{field:'root_cause',text:'也许查找用语有问题',temporal_scope:'RETROSPECTIVE'}]}
 const c=careerProjectContext(o)
 assert.deepEqual(c.已保存的修改.回答提示词,{原版本:'旧要求',新版本:'新要求'})
 assert.equal(c.已保存的个人补充[0].性质,'待验证根因假设');assert.equal(c.已保存的个人补充[0].时间,'事后回顾')
})
test('long case excerpts are marked and sampling does not shrink recorded totals',()=>{
 const o=fixture(),run=o.experiment.baseline.run
 run.case_results=Array.from({length:15},(_,i)=>({case_id:'c'+i,query:'长'.repeat(1601),results:[]}));run.execution_order=run.case_results.map(c=>c.case_id)
 const c=careerProjectContext(o)
 assert.equal(c.原始初测.已保存题目数,15);assert.equal(c.原始初测.逐题记录.length,12)
 assert.match(c.原始初测.逐题记录[0].问题,/节选/)
 assert.ok(c.提问内容边界.some(x=>x.includes('共 15 条')))
})
test('behavior path uses its own effective answers and never claims RAG work',()=>{
 const o=fixture();o.kind='AGENT_BEHAVIOR'
 o.experiment.baseline.effective_results=o.experiment.baseline.effective_answer_results
 o.experiment.baseline.run.eval_set_snapshot={case_snapshot:[{case_id:'shipping',input:'帮我退款',source:'platform_preset'}]}
 const c=careerProjectContext(o)
 assert.equal(c.原始初测.有效判定题数,2);assert.match(c.项目设定.AI与RAG的用途,/不使用知识检索/)
 assert.equal(c.原始初测.查找设置,undefined)
})
