import test from 'node:test'
import assert from 'node:assert/strict'
import {scoreCheckContext,scoreCheckPrompt,operationScoreCheckView} from '../src/score-check-prompt.js'
import {savedScoreView,savedOperationsRow} from './fixtures/score-check.js'
const context=(view,caseId='case-1')=>scoreCheckContext({view,caseId})

test('copy includes selected question, exact answer, frozen evidence, original judgment and rubric',()=>{
 const view=savedScoreView(),c=context(view),p=scoreCheckPrompt(c)
 assert.equal(c.用户问题,'订单实付 89 元，寄上海包邮吗？')
 assert.equal(c.客服原回答,'可以，您的订单可以包邮。')
 assert.equal(c.原评分.状态,'不通过')
 assert.equal(c.当时给客服的资料[0].编号,'chunk-1')
 assert.equal(c.完整参考规则[0].编号,'ref-1')
 assert.equal(c.当时的评分规则.细则.维度.conditions.各档条件[0],'遗漏决定性条件')
 assert.equal(c.当时的评分规则.细则.最低分.conditions,2)
 assert.equal(c.当时的评分规则.细则.严重错误规则.unsupported_promise,'不得凭空承诺包邮')
 assert.match(p,/先根据问题、客服原回答与参考规则，独立说明/)
 assert.match(p,/AI 建议冒充本人判断或独立人工校准/)
})
test('changing question excludes the previous question, answer and judgment',()=>{
 const view=savedScoreView(),p=scoreCheckPrompt(context(view,'case-2'))
 assert.match(p,/300 毫升/)
 assert.doesNotMatch(p,/89 元|99 元|可以，您的订单可以包邮。|ref-1|chunk-1/)
})
test('whitelist excludes sessions, provider credentials, arbitrary metadata and other questions',()=>{
 const view=savedScoreView()
 view.run.controls.eval_set_snapshot.cases.push({case_id:'holdout',query:'UNEXECUTED_HOLDOUT_MUST_NOT_COPY',expected_answer:'HOLDOUT_ANSWER_MUST_NOT_COPY'})
 view.run.answer_results[0].metadata={secret:'RESULT_METADATA_MUST_NOT_COPY'}
 const p=scoreCheckPrompt(context(view))
 assert.doesNotMatch(p,/SECRET_MUST_NOT_COPY|METADATA_MUST_NOT_COPY|HOLDOUT_MUST_NOT_COPY|HOLDOUT_ANSWER_MUST_NOT_COPY|provider_session_id/)
 assert.equal(context(view,'holdout'),null)
})
test('copy is pure and never rewrites saved results or frozen snapshots',()=>{
 const v=savedScoreView(),before=structuredClone(v)
 const a=scoreCheckPrompt(context(v)),b=scoreCheckPrompt(context(v))
 assert.equal(a,b);assert.deepEqual(v,before)
})
test('human override does not replace the original machine judgment',()=>{
 const v=savedScoreView();Object.assign(v.effective_answer_results[0],{human_evaluation_state:'PASS',human_reason:'本人核对后的意见',final_status:'PASS'})
 const c=context(v)
 assert.equal(c.原评分.状态,'不通过')
 assert.equal(c.原评分.理由,'实付 89 元未满 99 元，回答却承诺包邮。')
 assert.equal(c.当前人工复核.状态,'通过')
 assert.equal(c.当前人工复核.理由,'本人核对后的意见')
})
test('failed grading is kept as technical failure, never converted to a failed answer',()=>{
 const v=savedScoreView();Object.assign(v.run.answer_results[0],{original_status:'INVALID',judge_status:'FAILED',evaluation_error:'评分服务超时',evidence_evaluation:null})
 const c=context(v)
 assert.equal(c.原评分.状态,'执行或评分无效');assert.equal(c.原评分.评分执行状态,'FAILED')
 assert.match(c.原评分.评分错误,/超时/)
 assert.match(scoreCheckPrompt(c),/执行失败或资料缺失，不能直接算回答不通过/)
})
test('missing and unexecuted cases never fall back to another question',()=>{
 assert.equal(context(savedScoreView(),'not-found'),null)
 assert.equal(scoreCheckContext(),null);assert.equal(scoreCheckPrompt(null),'')
})
test('empty frozen evidence is not replaced with the current knowledge library',()=>{
 const v=savedScoreView();v.run.case_results[0].input_package.evidence=[]
 const c=context(v);assert.deepEqual(c.完整参考规则,[]);assert.deepEqual(c.当时给客服的资料,[])
})
test('missing frozen package uses frozen documents and honestly notes missing rubric',()=>{
 const v=savedScoreView();delete v.run.case_results[0].input_package;delete v.run.controls.scoring_profile
 const c=context(v);assert.equal(c.完整参考规则[0].原文,v.run.controls.knowledge_snapshot.documents[0].text)
 assert.match(c.当时的评分规则.细则,/原记录未附/)
 assert.match(c.本次提问的内容边界.join(),/未附完整评分细则/)
})
test('protocol examples stay out of the current-question prompt with an explicit limitation',()=>{
 const v=savedScoreView();v.run.controls.scoring_profile.protocol.examples=[{question:'OTHER_EXAMPLE_MUST_NOT_COPY',answer:'OTHER_ANSWER_MUST_NOT_COPY'}]
 const c=context(v);assert.match(c.本次提问的内容边界.join(),/原评分协议包含示例/)
 assert.doesNotMatch(scoreCheckPrompt(c),/OTHER_EXAMPLE_MUST_NOT_COPY|OTHER_ANSWER_MUST_NOT_COPY/)
})
test('long answers and evidence are explicitly bounded',()=>{
 const v=savedScoreView(),p=v.run.case_results[0].input_package
 p.current_answer='长'.repeat(17000);p.evidence=Array.from({length:30},(_,i)=>({scope:'REFERENCE',evidence_id:`ref-${i}`,text:'据'.repeat(7000)}))
 const c=context(v),bounds=c.本次提问的内容边界.join('\n')
 assert.match(bounds,/客服原回答仅附前 16000/);assert.match(bounds,/参考规则共 30 条，仅附前 24 条/)
 assert.match(bounds,/不能认定未附的后文不存在/)
 assert.equal(c.完整参考规则.length,24)
})
test('malformed object fields cannot smuggle arbitrary configuration into copied context',()=>{
 const v=savedScoreView(),secret={api_key:'NESTED_SECRET_MUST_NOT_COPY'}
 v.run.status=secret;v.run.answer_results[0].judge_status=secret;v.run.controls.scoring_profile.calibration_status=secret
 v.run.case_results[0].input_package.reference_complete=secret
 assert.doesNotMatch(scoreCheckPrompt(context(v)),/NESTED_SECRET_MUST_NOT_COPY/)
})
test('legacy behavior prompt contains only selected turns and bounded tool identity',()=>{
 const r={case_id:'tool-case',case:{title:'查询退款进度'},original_status:'PASS',original_reason:'工具已查询',human_final_status:'FAIL',human_reason:'本人有疑问',scores:{accuracy:1,extra:'SECRET'},turn_evidence:[{question:'退款到哪了？',response:'退款已到账',tool_traces:[{tool_name:'refund_status',success:true,args:{token:'TOOL_SECRET_MUST_NOT_COPY'},result:{personal:'RESULT_SECRET_MUST_NOT_COPY'}}]}]}
 const c=scoreCheckContext({caseId:'tool-case',runId:'run-tool',behaviorResult:r,thresholds:{accuracy:.8}})
 assert.equal(c.原评分.状态,'通过');assert.equal(c.人工复核.状态,'不通过');assert.equal(c.原评分.门槛.accuracy,.8)
 assert.match(c.资料范围,/未附原始参数及结果/)
 assert.doesNotMatch(scoreCheckPrompt(c),/SECRET_MUST_NOT_COPY|"extra"/)
 assert.equal(scoreCheckContext({caseId:'another-case',behaviorResult:r}),null)
})
test('batch copy uses frozen job rules and package completeness, machine and human remain separate',()=>{
 const {job,row}=savedOperationsRow(),before=structuredClone({job,row}),view=operationScoreCheckView(job,row),c=context(view)
 assert.equal(c.来源.评测轮次,'已有回答重评');assert.equal(view.run.fixed_answer_review,true)
 assert.equal(c.当时的评分规则.名称,'批次冻结规则');assert.equal(c.证据范围.参考是否完整,true)
 assert.equal(c.原评分.状态,'不通过');assert.equal(c.当前人工复核.状态,'通过')
 assert.deepEqual({job,row},before)
})
test('batch rows without scoring never pretend to have successful grading',()=>{
 const {job,row}=savedOperationsRow();row.event=null
 let c=context(operationScoreCheckView(job,row));assert.equal(c.原评分.状态,'尚未执行');assert.equal(c.原评分.评分执行状态,'NOT_RUN')
 row.event={evaluation_state:'NOT_RUN'};c=context(operationScoreCheckView(job,row));assert.equal(c.原评分.评分执行状态,'NOT_RUN')
 row.event={evaluation_state:'EXECUTION_FAILED',error:'评分超时'};c=context(operationScoreCheckView(job,row));assert.equal(c.原评分.状态,'执行失败');assert.equal(c.原评分.评分执行状态,'FAILED')
 assert.equal(operationScoreCheckView(job,{}),null)
})
