import test from 'node:test'
import assert from 'node:assert/strict'
import {recommendedNextStep} from '../src/retrieval-change-options.js'
import {evidenceCount} from '../src/evidence-display.js'
import {completeLog,consultationText,splitMaterial,safeMaterial} from '../src/consultation-material.js'
import {sourcePassages,passageValid,referenceDraft} from '../src/source-passages.js'
import {comparisonSummary} from '../src/comparison-summary.js'
import {savedCheckAssessment,factPrediction,regressionRisk} from '../src/change-checks.js'
import {flowController} from '../src/retest-flow.js'
import {reactive} from 'vue'
const view=()=>({run:{run_id:'base',status:'COMPLETE',verify_answers:true,retrieval_config:{top_k:3,candidate_pool_size:20},execution_order:['a'],controls:{index_snapshot:{chunks:[1,2,3]}},provider_call_count:2,case_results:[{case_id:'a',status:'SUCCESS',query:'question',results:[],pre_rerank_results:[1,2,3],evidence_path:{knowledge:{status:'FULL',review_status:'CONFIRMED'},candidates:{status:'MISSING'},context:{status:'MISSING'}}}]},effective_answer_results:[{case_id:'a',execution_status:'SUCCESS',turn_evidence:[{response:'saved answer'}]}]})
test('recommendations require reviewed evidence and reduce exhausted candidate-pool priority',()=>{
 const v=view(),r=v.run.case_results[0]
 r.evidence_path.knowledge.review_status='DRAFT';assert.equal(recommendedNextStep(v,'a').action,'review')
 assert.match(evidenceCount({status:'UNREVIEWED',included_count:2,required_count:2}),/2 条文本匹配/)
 r.evidence_path.knowledge.review_status='CONFIRMED';const n=recommendedNextStep(v,'a')
 assert.equal(n.method,'RETRIEVAL_MODE_CHANGE');assert.ok(!n.alternatives.includes('CANDIDATE_POOL_CHANGE'))
 r.evidence_path.candidates.status='FULL';r.evidence_path.selected={status:'MISSING'};assert.equal(recommendedNextStep(v,'a').method,'RERANK_TOGGLE')
 r.evidence_path.selected.status='FULL';assert.equal(recommendedNextStep(v,'a').action,'source')
 v.effective_answer_results=[];assert.equal(recommendedNextStep(v,'a').action,'answer-setup')
})
test('full saved logs retain unknown fields, errors and usage without mutating reactive source',()=>{
 const v=reactive(view());v.run.original_event={unknown_field:'retained',error:'FAILED',cost:null};v.run.api_key='private-key'
 const before=JSON.stringify(v),data=completeLog({view:v,caseId:'a'})
 assert.equal(data.records.view.run.original_event.unknown_field,'retained');assert.equal(data.records.view.run.api_key,'[认证信息已移除]')
 assert.equal(JSON.stringify(v),before);assert.ok(!JSON.stringify(data).includes('private-key'))
 const redacted=safeMaterial({authorization:'Bearer abcdefghijkl',text:'secret-business sk-1234567890abc',url:'http://user:pass@x/?api_key=secret'},{redactions:['secret-business']})
 assert.ok(!JSON.stringify(redacted.data).includes('abcdefg'));assert.ok(!JSON.stringify(redacted.data).includes('1234567890abc'));assert.ok(!JSON.stringify(redacted.data).includes('user:pass'))
 const material=consultationText({kind:'plan',context:{text:'business'},logOptions:{view:v,redactions:['business']}})
 assert.ok(!material.includes('"text": "business"'))
})
test('a completed batch log retains its matching single-case trial without mixing its statistics',()=>{
 const v=view(),trial={flow:{flow_id:'trial',inputs:{baseline_run_id:'base',selected_case_ids:['a']}},view:{run:{run_id:'single',execution_order:['a'],provider_call_count:2}}}
 const data=completeLog({view:v,trial})
 assert.equal(data.records.single_case_trial.view.run.run_id,'single')
 assert.equal(data.records.view.run.provider_call_count,2)
 assert.equal(completeLog({view:v,trial:{...trial,flow:{inputs:{baseline_run_id:'different'}}}}).records.single_case_trial,undefined)
 assert.equal(completeLog({view:v,trial,caseId:'other'}).records.single_case_trial,undefined)
})
test('long material splits losslessly on Unicode boundaries',()=>{
 const text='政策😀原文'.repeat(30000),parts=splitMaterial(text,7000)
 assert.equal(parts.join(''),text);assert.ok(parts.length>5);assert.ok(parts.every(x=>!/[\uD800-\uDBFF]$/.test(x)))
})
test('source selection keeps exact Unicode offsets and draft never invents a policy',()=>{
 const docs=[{document_id:'p',text:'😀政策\n七日内可退。\n定制商品除外。'}],rows=sourcePassages(docs)
 for(const q of rows)assert.ok(passageValid(q,docs))
 assert.equal(rows[1].source_start,4)
 const draft=referenceDraft({expected_answer:'七日内可退。第二天到账。'},docs)
 assert.equal(draft.length,1);assert.equal(draft[0].draft_origin,'EXACT_REFERENCE_SOURCE_MATCH')
 assert.equal(passageValid({...rows[1],source_start:0},docs),false)
})
test('comparison counts missing and unreviewed answers separately and never infers answer improvements from retrieval',()=>{
 const pair={case_id:'a',baseline:{status:'SUCCESS',results:[]},retest:{status:'SUCCESS',results:[]},baseline_answer:{execution_status:'SUCCESS'},retest_answer:{execution_status:'SUCCESS'},transition:'RETRIEVAL_IMPROVED',answer_transition:'NOT_COMPARABLE'}
 const c={comparable:true,case_pairs:[pair,{...pair,case_id:'b',retest:null},{...pair,case_id:'c',answer_transition:'PASS→FAIL'}]}
 const s=comparisonSummary(c,view(),view(),{selected_case_ids:['a']})
 assert.equal(s.counts.improved,0);assert.equal(s.retrieval.improved,3);assert.equal(s.counts.incomplete,1);assert.equal(s.counts.regressed,1);assert.equal(s.counts.notComparable,1);assert.equal(s.rows[0].case_id,'c')
 assert.equal(s.afterCost.fee,'未知')
})
test('uncertain flow submission only reads the receipt and stores no content',async()=>{
 const data=new Map(),posts=[],gets=[],states=[]
 const storage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)}
 const controller=flowController({storage,autoPoll:false,client:{post:async(path,body)=>{posts.push({path,body});throw new Error('lost response')},get:async path=>{gets.push(path);return {flow_id:[...data.values()][0],stage:'RUNNING'}}},onChange:s=>states.push(s),onArtifacts:async()=>{}})
 await controller.start({privateBusinessText:'never-store-content'})
 assert.equal(posts.length,1);assert.equal(gets.length,1);assert.ok(!JSON.stringify([...data]).includes('never-store-content'))
 await controller.sync();assert.equal(posts.length,1);assert.equal(gets.length,2);controller.dispose()
})

test('a passing answer or failed scoring never becomes evidence for an answer prompt change',()=>{
 const v=view(),r=v.run.case_results[0];r.evidence_path.context.status='FULL';r.evidence_path.candidates.status='FULL'
 v.effective_answer_results[0].final_status='PASS';assert.equal(recommendedNextStep(v,'a').method,null)
 v.effective_answer_results[0].judge_status='FAILED';assert.equal(recommendedNextStep(v,'a').action,'logs')
})

test('plan checks use only predefined measurements and mark unreviewed data as unknown',()=>{
 const change={selected_case_ids:['a'],verification_plan:{prediction:'FACT_INCLUSION',risk:'ANSWER_REGRESSION'},reason:'用户预测（待验证）：'+factPrediction+'\n用户担心的退化（待验证）：'+regressionRisk}
 const summary={answers:true,rows:[{case_id:'a',baseline:{status:'SUCCESS'},retest:{status:'SUCCESS'},facts:null},{case_id:'b',category:'notComparable'}]}
 let checks=savedCheckAssessment(change,{comparable:true},summary);assert.equal(checks[0].status,'无法判断');assert.equal(checks[1].status,'无法判断')
 summary.rows[0].facts={added:[{fact_id:'new'}],lost:[]};summary.rows[1].category='regressed'
 checks=savedCheckAssessment(change,{comparable:true},summary);assert.equal(checks[0].status,'本次观察支持');assert.equal(checks[1].status,'本轮观察到风险')
 assert.equal(savedCheckAssessment({...change,verification_plan:null,reason:'用户预测（待验证）：'+factPrediction},{comparable:true},summary)[0].status,'无法判断')
})
