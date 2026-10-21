<script setup>
import {computed} from 'vue'
import {checkLabels,taskLabels,behaviorLabels,stageLabels,sourceLabels,ratioText,comparisonMessage} from '../trusted-results.js'
import {questionLabel} from '../question-navigation.js'
import {evidenceReasons} from '../evidence-explanation.js'
const props=defineProps({view:Object,comparison:Object,caseId:String})
const emit=defineEmits(['inspect-case'])
const trust=computed(()=>props.comparison?.trust_summary)
const flow=computed(()=>props.view?.trusted_result?.sample_flow||props.view?.run?.sample_flow)
const identity=computed(()=>props.view?.trusted_result?.experiment_identity||props.view?.run?.experiment_identity)
const current=computed(()=>props.view?.trusted_result?.cases?.find(c=>c.case_id===props.caseId))
const input=computed(()=>props.view?.run?.case_results?.find(c=>c.case_id===props.caseId)?.input_package)
const states=computed(()=>Object.entries(flow.value?.states||{}).filter(([,value])=>value.count>0))
function caseDetails(id){const row=props.view?.run?.case_results?.find(c=>c.case_id===id);const item=props.view?.trusted_result?.cases?.find(c=>c.case_id===id);const answer=props.view?.effective_answer_results?.find(c=>c.case_id===id);return {question:row?.query||'本题原问题未记录',reasons:evidenceReasons(answer,row?.input_package,item?.evaluation_state)}}
const caseNumber=id=>(props.view?.run?.case_results||[]).findIndex(c=>c.case_id===id)+1
const currentReasons=computed(()=>caseDetails(props.caseId).reasons)
const judgeLabels={HUMAN_REVIEW:'人工复核',MACHINE:'评分模型',EXECUTABLE_RULE:'规则检查',UNKNOWN:'未记录'}
const changeLabels={QUERY_REWRITE_TOGGLE:'改写查询',RERANK_TOGGLE:'调整排序',TOP_K_CHANGE:'调整返回条数',KNOWLEDGE_UPDATE:'更新知识库'}
</script>
<template>
 <section v-if="caseId&&current" class="trusted-case" aria-label="本题状态与证据边界">
  <h4>这题为什么这样判？</h4><p><strong>{{checkLabels[current.evaluation_state]}}</strong> · {{judgeLabels[current.judged_by]||'未记录判定来源'}}</p><p>问题解决情况：{{taskLabels[current.task_outcome]}} · 回答方式：{{behaviorLabels[current.current_turn_behavior]||'未记录'}}</p>
  <p v-if="current.task_outcome!=='COMPLETED'&&['CLARIFY','HANDOFF','REFUSE','REASONABLE_CLARIFICATION','REASONABLE_REFUSAL','REASONABLE_HANDOFF','REFUSED_OR_ESCALATED'].includes(current.current_turn_behavior)" class="muted">这次追问或转交可能是合理的，但客户的问题还没有解决。</p>
  <p v-if="input?.missing_items.length" class="note warning">还缺这些资料：{{input.missing_items.join('；')}}</p>
  <p v-if="input?.truncated_items.length" class="note warning">部分输入过长或被截断，本次可能缺少关键资料。</p>
  <div v-if="currentReasons.length" class="evidence-reasons"><div v-for="r in currentReasons" :key="r.code"><p><strong>{{r.message}}</strong></p><p>{{r.next_step}}</p></div></div>
  <details><summary>逐项检查结果</summary><ul class="check-list"><li v-for="c in current.checks" :key="c.name">{{({retrieval:'有没有查到资料',generation:'有没有生成回答',evidence:'资料是否适用于这道题',quality:'回答是否符合规则',critical_errors:'有没有严重问题',business_tools:'是否执行了业务操作'})[c.name]}}：{{checkLabels[c.status]}}<small v-if="c.rule"> · 此客服不能实际查订单或退款</small></li></ul><p class="muted">失败的检查项可以帮你缩小范围，还需要核对原文才能确定原因。</p></details>
  <details v-if="input"><summary>这次评分用的资料</summary><p>来源：{{sourceLabels[input.source_type]||'未知'}}。实际交互记录也不一定代表线上流量。</p><p>资料是否齐全：{{input.check.reference_completeness_status}} · {{input.reference_completeness?.reason||'没有人工核对说明'}}</p><p v-for="(issue,i) in input.check.issues" :key="i" class="note warning">{{issue.scope}} / {{issue.evidence_id}}：{{issue.reason}}</p><details><summary>版本与原始标识</summary><p>输入 {{input.input_id}} · 上一版本 {{input.parent_input_id||'未记录'}}</p><p>会话 {{input.conversation_id||'未记录'}} · 第 {{input.turn_id||'未知'}} 轮 · 提问时间 {{input.question_time||'未记录'}} · 时区 {{input.question_timezone||'未记录'}}</p><p v-if="input.truncated_items.length">截断记录：{{JSON.stringify(input.truncated_items)}}</p><p>原文与校验值均保留。引用能对上原文，不代表它一定支持这句回答。</p></details></details>
 </section>
 <section v-else-if="view&&flow" class="panel trusted-results" aria-label="可信结果与样本流转">
  <h2>评测结果</h2><p v-if="view.trusted_result?.historical_metadata_unknown" class="note warning">这份旧记录没有保存部分信息，缺少的项目显示为未知。</p>
  <p v-if="flow.historical_recheck_required" class="note warning">这份历史记录使用旧证据约束，建议按新规则重核；机器原判与封存报告保留。</p>
  <div class="two-column"><div><h3>已判定 / 参评题目</h3><p>{{ratioText(flow.coverage)}}</p></div><div><h3>通过 / 已判定</h3><p>{{ratioText(flow.machine_pass_rate)}}</p></div></div>
  <p v-if="flow.publication_status==='INCOMPLETE'" class="note warning">记录尚未完整对应，本次不发布整批通过率。已完成子集：{{ratioText(flow.partial_pass_rate)}}。请先核对缺失、重复与范围外记录。</p>
  <p class="muted">点击下面的状态或题号，查看每道题的回答与依据。</p>
  <p v-if="flow.coverage.numerator===0&&flow.coverage.denominator>0" class="note warning">这次还没有可判定的题。点开“证据不足”或“执行失败”查看原因。</p>
  <div class="result-counts"><details v-for="[key,value] in states" :key="key"><summary>{{checkLabels[key]}} · {{value.count}}</summary><div class="state-question-links"><button v-for="id in value.sample_ids" :key="id" type="button" class="secondary" :aria-label="'查看'+questionLabel(caseNumber(id))" :title="caseDetails(id).question" @click="emit('inspect-case',id)">{{questionLabel(caseNumber(id))}}</button></div></details></div>
  <details class="result-more"><summary>客户的问题解决了吗？</summary><p v-for="(s,key) in flow.task_outcomes" :key="key">{{taskLabels[key]}}：{{s.count}}</p></details>
  <details class="result-more"><summary>这次检查了什么？</summary><p>检查对象：{{identity?.subject==='AGENT_OPTIMIZATION'?'客服 Agent 的回答和资料查找':identity?.subject||'未记录'}}。</p><p>这次的改动：{{changeLabels[identity?.changed_component]||identity?.changed_component||'第一次运行，还没有改动'}}</p><p v-if="identity?.declared_diff?.length">记录的配置变化：{{JSON.stringify(identity.declared_diff)}}</p><p>不同题目 {{flow.independent_case_count}} 道 · 问题类型 {{flow.problem_family_count}} 组 · 回答 {{flow.answer_count}} 条 · 评分记录 {{flow.scoring_event_count}} 条（包含不可评及跳过记录；实际调用见用量）</p></details>
  <details v-if="flow.cost" class="result-more"><summary>调用次数和用量</summary><p>实际调用模型 {{flow.cost.actual_requests}} 次，包含重试；已知 Token {{flow.cost.known_total_tokens??'未返回'}}，另有 {{flow.cost.unknown_usage_requests}} 次调用未返回用量。</p><p>逐题耗时合计：{{flow.cost.case_latency_ms==null?'未记录':(flow.cost.case_latency_ms/1000).toFixed(2)+' 秒'}}。服务未提供货币费用。</p></details>
  <details class="result-more"><summary>查看统计过程与原始记录</summary><div class="flow-stages"><details v-for="s in flow.stages" :key="s.name"><summary>{{stageLabels[s.name]}} · {{s.count}}</summary><p>{{s.sample_ids.join('、')||'无'}}</p><p v-for="(x,i) in s.excluded||[]" :key="i">未纳入 {{x.sample_id}}：{{x.reason==='OUTSIDE_DECLARED_PARTITION'?'不在本次选定的范围内':x.reason}}</p></details></div><div v-for="(r,key) in {retrieval:flow.retrieval_reconciliation,answer:flow.answer_reconciliation}" :key="key"><template v-if="r"><h4>{{key==='answer'?'回答记录':'检索记录'}} · {{r.complete?'每题都已对应':'记录没有完整对应'}}</h4><p>应有 {{r.expected_count}} 条，收到 {{r.received_count}} 条；缺失 {{r.missing_ids.join('、')||'无'}}；重复 {{r.duplicate_ids.join('、')||'无'}}；未预期的记录 {{r.unexpected_ids.join('、')||'无'}}</p></template></div><p v-for="(s,key) in flow.sources" :key="key">{{sourceLabels[key]||key}}：{{s.count}} 条</p><p>这些样本不能用来推算线上问题发生率。</p></details>
 </section>
 <section v-else-if="comparison" class="panel trusted-comparison" aria-label="全部范围与共同可比子集">
  <h2>改完以后，真的更好吗？</h2><p class="note" :class="trust?.overall_improvement_allowed?'':'warning'">{{comparisonMessage(trust)}}</p>
  <template v-if="trust"><div class="two-column"><div><h3>修改前</h3><p>能判断的题：{{ratioText(trust.baseline.coverage)}}</p><p>其中通过：{{ratioText(trust.baseline.machine_pass_rate)}}</p></div><div><h3>修改后</h3><p>能判断的题：{{ratioText(trust.retest.coverage)}}</p><p>其中通过：{{ratioText(trust.retest.machine_pass_rate)}}</p></div></div>
   <p>两次都能判断的 {{trust.common_subset.count}} 道题中：{{trust.common_subset.improved_ids.length}} 道变好，{{trust.common_subset.regressed_ids.length}} 道变差，{{trust.common_subset.unchanged_ids.length}} 道没变。</p><p>这 {{trust.common_subset.count}} 道题的通过情况：{{ratioText(trust.common_subset.baseline_pass_rate)}} → {{ratioText(trust.common_subset.retest_pass_rate)}}</p>
   <p v-if="trust.full_scope.added_ids.length||trust.full_scope.removed_ids.length||trust.lost_valid_decision_ids.length" class="note warning">新增题：{{trust.full_scope.added_ids.join('、')||'无'}}；移除题：{{trust.full_scope.removed_ids.join('、')||'无'}}；这次无法再判断的题：{{trust.lost_valid_decision_ids.join('、')||'无'}}。</p>
   <details v-if="trust.problem_families?.length"><summary>同类问题改善与退化</summary><p v-for="family in trust.problem_families" :key="family.family_id">{{family.family_id}} · {{family.sample_ids.length}} 题：改善 {{family.improved}}，退化 {{family.regressed}}，仍失败 {{family.still_failed}}，不变 {{family.unchanged}}，无法比较 {{family.not_comparable}}</p><p>离线控制变量对照；单次分差不证明因果。</p></details><details><summary>查看每题的前后结果</summary><p v-for="t in trust.full_scope.state_transitions" :key="t.sample_id">{{t.sample_id}}：{{checkLabels[t.before]||'未参加'}} → {{checkLabels[t.after]||'未参加'}} · {{t.comparable?'可以比较':'这题无法比较'}}</p></details>
  </template>
 </section>
</template>
<style scoped>
.trusted-case{padding:16px;margin:14px 0;border:1px solid var(--border,#ddd);border-radius:10px;overflow-wrap:anywhere}.trusted-results,.trusted-comparison{overflow-wrap:anywhere}.flow-stages{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.flow-stages details{padding:10px;background:var(--surface-soft,#f5f5f2)}.check-list{padding-left:20px}summary{cursor:pointer}.two-column>*{min-width:0}.result-counts{display:grid;gap:12px;margin:20px 0}.state-question-links{display:flex;flex-wrap:wrap;gap:8px;padding-top:12px}.state-question-links button{font-size:13px;padding:8px 12px}.state-case{padding:14px 0;border-bottom:1px solid var(--border,#ddd)}.state-case p{font-size:14px;line-height:1.7;margin:8px 0}.evidence-reasons{padding:12px 16px;background:var(--surface-soft,#f7f7f4);border-radius:8px}.evidence-reasons p{font-size:14px;margin:8px 0}.result-more{margin:14px 0}.trusted-results h3,.trusted-comparison h3{font-size:14px}.trusted-results .two-column p,.trusted-comparison .two-column>div>p:first-of-type{font-size:20px;margin-top:10px}
</style>
