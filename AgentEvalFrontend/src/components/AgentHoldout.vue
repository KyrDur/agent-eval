<script setup>
import {computed,inject,ref,watch} from 'vue'
import {api} from '../api.js'
import RunDiagnostics from './RunDiagnostics.vue'
import ScoringEvidence from './ScoringEvidence.vue'
import TrustedResults from './TrustedResults.vue'
const props=defineProps({comparison:Object})
const work=inject('workspace'),rag=inject('retrieval')
const validation=ref(null),reason=ref(''),budget=ref(20),notice=ref('')
const count=computed(()=>rag.state.baseline?.run.controls.eval_set_snapshot.cases.filter(c=>c.partition==='HOLDOUT').length||0)
const expected=computed(()=>[rag.state.baseline?.run,rag.state.retest?.run].reduce((n,r)=>n+(r?count.value*(Number(r.retrieval_config.query_rewrite)+Number(r.retrieval_config.rerank)+(r.verify_answers?2:0)):0),0))
watch(()=>props.comparison?.comparison_id,async id=>{
 validation.value=null;notice.value='';if(!id)return
 try{const rows=await api.get('/retrieval-validations?comparison_id='+encodeURIComponent(id));validation.value=rows.at(-1)||null;budget.value=Math.max(1,expected.value)}catch{notice.value='保留验证状态暂时无法读取，请同步后重试。'}
},{immediate:true})
async function lock(){await work.action('锁定 Agent 两版配置与保留题',async()=>{validation.value=await api.post('/retrieval-validations/lock',{comparison_id:props.comparison.comparison_id,reason:reason.value,request_budget:budget.value})})}
async function execute(){await work.action('运行两版保留验证并解封',async()=>{validation.value=await api.post(`/retrieval-validations/${validation.value.validation_id}/execute`,{provider_session_id:work.state.session.provider_session_id})})}
</script>
<template>
 <section class="panel" aria-label="Agent 保留题验证">
  <h2>用未参与调试的题目，验证这次修改</h2>
  <p>调试题用于选择修改；保留题只在两版配置锁定后运行。两边采集结束才展示结果，解封后不能继续当作新的独立保留集。此处是工作流隔离，开发者仍可访问本地文件。</p>
  <p v-if="!count" class="note">这套题还没有保留题。请在新 Baseline 的测试题中设置 group_id 和 HOLDOUT 用途，确认分组后再开展独立验证。</p>
  <p v-if="notice" class="note warning">{{notice}}</p>
  <template v-if="count && !validation">
   <p>{{count}} 道保留题 · 两版共预计 {{expected}} 次模型请求。使用当前模型配置；费用依提供商计费。</p>
   <label>为什么选择这个候选，以及要验证什么<textarea v-model="reason" rows="3" /></label>
   <label>总请求上限<input v-model.number="budget" type="number" min="1" max="500" /></label>
   <button class="primary" :disabled="!!work.state.busy||!comparison.comparable||!reason.trim()||budget<expected" @click="lock">锁定修改前、修改后配置与保留题</button>
  </template>
  <template v-if="validation">
   <p class="note">{{{LOCKED:'已锁定',RUNNING:'正在运行',COMPLETE:'已采集并解封',FAILED:'采集失败'}[validation.status]}} · {{validation.heldout_count}} 道题 · 请求上限 {{validation.request_budget}}</p>
   <p>{{validation.reason}}</p>
   <button v-if="validation.status==='LOCKED'" class="primary" :disabled="!!work.state.busy||!work.state.session" @click="execute">运行两版保留验证并解封结果</button>
   <p v-if="validation.error" class="note danger">{{validation.error}} · 本次不能形成完整的改进结论。</p>
   <template v-if="validation.report?.case_pairs">
    <TrustedResults :comparison="{trust_summary:validation.report.trust_summary}" />
    <p class="note warning">已解封；单轮差异不证明因果。Judge 初始未校准时，仍需人工核对评分。</p>
    <article v-for="pair in validation.report.case_pairs" :key="pair.case_id" class="holdout-case">
     <h3>{{pair.query}}</h3><p>检索：{{{RETRIEVAL_IMPROVED:'改善',RETRIEVAL_REGRESSED:'退化',RETRIEVAL_UNCHANGED:'未变化',NOT_COMPARABLE:'无法比较'}[pair.transition]}} · 回答：{{pair.answer_transition}}</p>
     <div class="two-column"><div v-for="side in ['baseline','retest']" :key="side"><h4>{{side==='baseline'?'修改前':'修改后'}}</h4><p>{{pair[side+'_answer']?.turn_evidence?.[0]?.response || '未形成回答'}}</p><RunDiagnostics :retrieval="pair[side]" :answer="pair[side+'_answer']" :verify-answers="!!pair[side+'_answer']" /><ScoringEvidence :result="pair[side+'_answer']" /></div></div>
    </article>
   </template>
  </template>
 </section>
</template>
<style scoped>.holdout-case{margin:18px 0;padding:16px;border:1px solid var(--border,#ddd);border-radius:12px;overflow-wrap:anywhere}label{display:block;margin:12px 0}</style>
