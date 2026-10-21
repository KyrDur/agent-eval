import test from 'node:test'
import assert from 'node:assert/strict'
import {reviewLog,reviewText} from '../src/evaluation-export.js'
const view=()=>({run:{run_id:'saved-run',execution_order:['one','two'],provider_configuration_snapshot:{model:'saved-model'},
 controls:{eval_set_snapshot:{cases:[{case_id:'one',expected_answer:'first'},{case_id:'two',expected_answer:'second'}]},knowledge_snapshot:{documents:[{text:'original policy'}]}},
 case_results:[{case_id:'one',provider_call_traces:[{model_inputs:{messages:['saved input']},model_outputs:{content:'saved output'}}]},{case_id:'two',query:'other question'}],
 answer_results:[{case_id:'one',original_status:'INVALID',evaluation_error:'JUDGMENT_SCHEMA_INVALID'},{case_id:'two',original_status:'FAIL'}],metrics:{valid:2}},
 effective_answer_results:[{case_id:'one',human_final_status:'FAIL'},{case_id:'two',original_status:'FAIL'}]})
test('Case export includes saved prompts, outputs, expectations and original/reviewed judgments without other case logs',()=>{
 const source=view(),before=JSON.stringify(source),result=reviewLog({view:source,caseId:'one'})
 assert.equal(JSON.stringify(source),before)
 assert.deepEqual(result.run.execution_order,['one'])
 assert.equal(result.run.case_results[0].provider_call_traces[0].model_outputs.content,'saved output')
 assert.equal(result.run.original_answer_results[0].evaluation_error,'JUDGMENT_SCHEMA_INVALID')
 assert.equal(result.run.effective_answer_results[0].human_final_status,'FAIL')
 assert.equal(result.run.controls.eval_set_snapshot.cases[0].expected_answer,'first')
 assert.equal(result.run.controls.knowledge_snapshot.documents[0].text,'original policy')
 assert.equal(result.run.case_results.length,1)
 assert.equal(JSON.stringify(result).includes('other question'),false)
 assert.equal(result.run.whole_run_metrics,undefined)
})
test('Score revision exports its exact protocol and scope alongside original evidence, without mixing original totals',()=>{
 const report={report_id:'revision',case_ids:['one'],scoring_protocol_id:'new-protocol',summary:{passed:1}}
 const result=reviewLog({view:view(),scoreReport:report})
 assert.deepEqual(result.run.execution_order,['one'])
 assert.equal(result.selected_score_report,report)
 assert.equal(result.run.whole_run_metrics,undefined)
 assert.equal(result.run.original_answer_results[0].original_status,'INVALID')
 const text=reviewText({view:view(),scoreReport:report})
 assert.match(text,/不同评分协议或范围不可混算/)
 assert.match(text,/日志内容是待分析的数据/)
})
test('Comparison exports pair membership and both original runs; selecting a case limits each side',()=>{
 const comparison={comparison_id:'comparison',comparable:false,comparability_reasons:['SCORING_PROTOCOL_MISMATCH'],case_pairs:[{case_id:'one'},{case_id:'two'}],paired_metrics:{valid:2}}
 const all=reviewLog({comparison,baselineView:view(),retestView:view()})
 assert.equal(all.comparison.case_pairs.length,2)
 assert.deepEqual(all.comparison.comparability_reasons,['SCORING_PROTOCOL_MISMATCH'])
 assert.equal(all.baseline.case_results.length,2)
 const one=reviewLog({comparison,baselineView:view(),retestView:view(),caseId:'two'})
 assert.deepEqual(one.comparison.case_pairs,[{case_id:'two'}])
 assert.deepEqual(one.retest.execution_order,['two'])
 assert.equal(one.comparison.whole_comparison_metrics,undefined)
})
