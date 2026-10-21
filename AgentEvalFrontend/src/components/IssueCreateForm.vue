<script setup>
import {computed,reactive,watch} from 'vue'
import {issueLayers,issueRoutes,lines,newRepairPlan,repairPlan} from '../issue-workflow.js'
const props=defineProps({sampleId:{type:String,default:''},initialTitle:{type:String,default:''},disabled:Boolean})
const emit=defineEmits(['create'])
const draft=reactive({title:'',layer:'DATA',owner:'',description:'',related_evidence:'',possible_impact:'',candidate_causes:'',alternative_explanations:'',next_check:'',agent_component:'UNKNOWN',severity:'UNKNOWN',observed_count:'',observed_denominator:'',sampling_source:'',repair_cost:'',plan:newRepairPlan(),sampleIds:''})
watch(()=>[props.sampleId,props.initialTitle],()=>{draft.title=props.initialTitle;draft.sampleIds=props.sampleId;draft.plan=newRepairPlan(props.sampleId)},{immediate:true})
const ready=computed(()=>props.sampleId&&[draft.title,draft.owner,draft.description,draft.related_evidence,draft.candidate_causes,draft.alternative_explanations,draft.next_check,...['success_criteria','target_error','potential_regressions','validation_scope'].map(k=>draft.plan[k])].every(v=>v.trim())&&lines(draft.sampleIds).includes(props.sampleId))
function submit(){
  const {plan,sampleIds,...body}=draft
  emit('create',{...body,related_evidence:lines(body.related_evidence),candidate_causes:lines(body.candidate_causes),repair_plan:repairPlan(plan,sampleIds),observed_count:body.observed_count?Number(body.observed_count):null,observed_denominator:body.observed_denominator?Number(body.observed_denominator):null})
}
</script>
<template>
  <form @submit.prevent="submit"><h3>记录问题与可区分的假设</h3>
    <label>问题标题<input v-model="draft.title" maxlength="200" required /></label>
    <div class="two-column"><label>优先排查环节<select v-model="draft.layer" aria-label="优先排查环节"><option v-for="(label,key) in issueLayers" :key="key" :value="key">{{label}}</option></select></label><label>负责人<input v-model="draft.owner" maxlength="100" required /></label></div>
    <p class="note">{{issueRoutes[draft.layer]}} 初步环节仍是待验证假设。</p>
    <label v-if="draft.layer==='AGENT'">候选 Agent 环节<select v-model="draft.agent_component"><option value="UNKNOWN">尚不能定位</option><option value="KNOWLEDGE">知识</option><option value="RETRIEVAL">检索</option><option value="GENERATION">生成</option><option value="TOOL" disabled>工具（当前政策问答没有业务工具执行）</option></select></label>
    <label>观察到的现象<textarea v-model="draft.description" rows="2" maxlength="3000" required /></label>
    <label>相关证据 · 每行一条<textarea v-model="draft.related_evidence" rows="2" required placeholder="引用原文、片段 ID 或复核记录；区分观察与解释" /></label>
    <label>可能影响<textarea v-model="draft.possible_impact" rows="2" maxlength="2000" /></label>
    <div class="two-column"><label>候选原因 · 每行一个<textarea v-model="draft.candidate_causes" rows="3" required placeholder="允许多个候选，也可填写尚不能定位" /></label><label>其他解释<textarea v-model="draft.alternative_explanations" rows="3" maxlength="3000" required placeholder="哪些证据仍不能排除另一种解释？" /></label></div>
    <label>下一步怎样区分这些原因<textarea v-model="draft.next_check" rows="2" maxlength="3000" required /></label>
    <details><summary>排查优先级与观察范围</summary><label>影响程度<select v-model="draft.severity"><option value="UNKNOWN">证据不足，待排查</option><option value="CRITICAL">少见也需优先的严重错误</option><option value="CORE_TASK">影响核心任务</option><option value="MINOR">轻微问题</option></select></label><div class="two-column"><label>观察到同类数量<input v-model="draft.observed_count" type="number" min="1" /></label><label>对应采样分母<input v-model="draft.observed_denominator" type="number" min="1" /></label></div><label>采样来源与范围<input v-model="draft.sampling_source" maxlength="1000" /></label><label>修复成本<input v-model="draft.repair_cost" maxlength="1000" /></label><p class="muted">不合成任意权重总分；构造题频次不能当作真实线上发生率。</p></details>
    <h3>修改前声明验收条件</h3><label>怎样才算本轮修复成功<textarea v-model="draft.plan.success_criteria" rows="2" maxlength="3000" required /></label><label>需要消除的具体错误<textarea v-model="draft.plan.target_error" rows="2" maxlength="2000" required /></label><label>潜在退化与可接受范围<textarea v-model="draft.plan.potential_regressions" rows="2" maxlength="2000" required /></label><label>验证范围与限制<textarea v-model="draft.plan.validation_scope" rows="2" maxlength="2000" required placeholder="原题复现、同类回归、新题分别需要哪些证据？未做的部分明确说明" /></label><div class="two-column"><label>本轮必须覆盖的题目 ID · 每行一个<textarea v-model="draft.sampleIds" rows="2" required /></label><label>目标评分结果<select v-model="draft.plan.expected_verdict"><option :value="null">不预设 PASS / FAIL，由目标错误判断</option><option value="PASS">PASS</option><option value="FAIL">FAIL（纠正错误放行也算修复）</option></select></label></div>
    <p class="muted">复测完成只说明过程发生。关闭时分别记录已修复、误报或暂不修复；未见题未完成时不宣称迁移有效。</p><button class="primary" :disabled="!ready||disabled">保存问题、假设与验收条件</button>
  </form>
</template>
