<script setup>
import {computed,defineAsyncComponent,inject,onBeforeUnmount,ref} from 'vue'
import {api} from '../api.js'
import {visualRows} from '../visual-results.js'
import WorkspaceIcon from '../components/WorkspaceIcon.vue'
import ScoreCheckPanel from '../components/ScoreCheckPanel.vue'
const BatchPage=defineAsyncComponent(()=>import('./OperationsPage.vue'))
const work=inject('workspace'),rag=inject('retrieval'),mode=inject('experimentMode')
const screen=ref('home'),batch=ref(null),historyOpen=ref(false),history=ref([]),chosenRun=ref(''),view=ref(null),caseId=ref(''),busy=ref(false),error=ref('')
const behavior=computed(()=>mode.value==='AGENT_BEHAVIOR')
const current=computed(()=>{
 const options=behavior.value?[work.state.retest,work.state.baseline]:[rag.state.retest,rag.state.baseline]
 return options.find(v=>v?.run.run_id===rag.state.scoreCheckSelection?.runId)||options.find(Boolean)
})
const questions=computed(()=>behavior.value?(view.value?.effective_results||[]).map((r,i)=>({case_id:r.case_id,query:r.case?.title||r.turn_evidence?.[0]?.question||r.case_id,number:i+1})):visualRows(view.value))
const behaviorResult=computed(()=>behavior.value?view.value?.effective_results?.find(r=>r.case_id===caseId.value):null)
let generation=0
function useView(value){view.value=value;const remembered=rag.state.scoreCheckSelection;caseId.value=value.run.run_id===remembered?.runId&&questions.value.some(r=>r.case_id===remembered.caseId)?remembered.caseId:questions.value[0]?.case_id||'';screen.value='case';historyOpen.value=false}
function useCurrent(){if(current.value)useView(current.value);else loadHistory()}
async function loadHistory(){
 const token=++generation;busy.value=true;error.value='';historyOpen.value=true
 try{const rows=behavior.value?await api.list('runs',{timeoutMs:12000}):await api.get('/retrieval-history',{timeoutMs:12000});if(token===generation)history.value=rows.filter(r=>r.status!=='RUNNING').sort((a,b)=>b.created_at.localeCompare(a.created_at))}
 catch(e){if(token===generation)error.value=e.message}finally{if(token===generation)busy.value=false}
}
async function loadSelected(){
 if(!chosenRun.value||busy.value)return
 const token=++generation,id=chosenRun.value;busy.value=true;error.value=''
 try{const saved=await api.get((behavior.value?'/runs/':'/retrieval-runs/')+encodeURIComponent(id),{timeoutMs:15000});if(token===generation)useView(saved)}
 catch(e){if(token===generation)error.value=e.message}finally{if(token===generation)busy.value=false}
}
function home(){generation++;busy.value=false;error.value='';historyOpen.value=false;screen.value='home'}
onBeforeUnmount(()=>generation++)
defineExpose({sync:async()=>{if(screen.value==='batch')await batch.value?.sync()}})
</script>
<template>
 <div class="scoring-tools">
  <template v-if="screen==='home'">
   <div class="page-heading"><div><span class="eyebrow">进阶工具 · 按需使用</span><h1>检查 AI 打分</h1><p>对评分有疑问时再来。完成实验和整理项目后，可以直接结束。</p></div></div>
   <div class="scoring-purpose-cards">
    <article class="panel"><span class="purpose-art"><WorkspaceIcon name="search" :size="30"/></span><h2>这道题可能判错了</h2><p>直接带上本题的回答、资料和原评分，复制提问让 AI 帮你检查。</p><button type="button" class="primary" :disabled="busy||!!work.state.busy" @click="useCurrent">{{current?'检查当前这道题':'选择已完成的评测'}}</button><button v-if="current" type="button" class="text-button" :disabled="busy" @click="loadHistory">选择其他评测 →</button></article>
    <article class="panel"><span class="purpose-art"><WorkspaceIcon name="scale" :size="30"/></span><h2>想检查打分是否可靠</h2><p>选一组回答，先由人判断，再和 AI 评分对照，找出分歧。</p><div class="purpose-flow"><span>人先判断</span><WorkspaceIcon name="arrow" :size="15"/><span>AI 打分</span><WorkspaceIcon name="arrow" :size="15"/><span>核对分歧</span></div><button type="button" class="secondary" :disabled="!!work.state.busy" @click="work.go('calibration')">人工与 AI 对照</button></article>
   </div>
   <div class="scoring-extra"><p>需要一次检查很多条回答，或设置定期检查？</p><button type="button" class="text-button" :disabled="!!work.state.busy" @click="screen='batch'">批量重评与定期检查 →</button></div>
  </template>
  <template v-else-if="screen==='case'"><div class="section-heading"><h1>检查这次评分</h1><button type="button" class="text-button" @click="home">返回检查入口</button></div><label v-if="questions.length>1" class="score-question-select">当前题目<select v-model="caseId"><option v-for="q in questions" :key="q.case_id" :value="q.case_id">第 {{q.number}} 题 · {{q.query}}</option></select></label><ScoreCheckPanel :key="view.run.run_id+caseId" :view="behavior?undefined:view" :case-id="caseId" :behavior-result="behaviorResult" :run-id="view.run.run_id" :thresholds="view.run.evaluation_protocol?.quality_thresholds" /></template>
  <template v-else><button type="button" class="text-button scoring-back" @click="home">← 返回检查入口</button><BatchPage ref="batch" /></template>
  <section v-if="historyOpen" class="panel scoring-history"><div class="section-heading"><h2>选择已保存的评测</h2><button type="button" class="text-button" @click="home">收起</button></div><p v-if="busy" role="status">正在读取你选择的记录…</p><label>选择评测<select v-model="chosenRun" aria-label="选择评测" :disabled="busy"><option value="">请选择一次评测</option><option v-for="r in history" :key="r.run_id" :value="r.run_id">{{r.run_type==='BASELINE'?'初测':'复测'}} · {{r.name||r.run_id.slice(0,8)}} · {{new Date(r.created_at).toLocaleString('zh-CN')}}</option></select></label><button type="button" class="primary" :disabled="busy||!chosenRun" @click="loadSelected">使用这次评测</button><p v-if="!busy&&!history.length" class="muted">还没有可选择的记录。先完成一次评测，再回来检查。</p></section>
  <p v-if="error" role="alert" class="note danger">{{error}}</p>
 </div>
</template>
<style scoped>
.scoring-purpose-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}.scoring-purpose-cards article{display:flex;flex-direction:column;align-items:flex-start;padding:28px}.purpose-art{background:#edf0e7;color:#748360;width:62px;height:62px;border-radius:15px;display:grid;place-items:center;margin-bottom:16px}.scoring-purpose-cards h2{font-size:21px;margin:4px 0}.scoring-purpose-cards p{font-size:14px;color:var(--muted);line-height:1.9;max-width:370px;flex:1;margin:10px 0 24px}.scoring-purpose-cards .text-button{margin-top:15px}.purpose-flow{display:flex;align-items:center;gap:10px;font-size:12px;color:var(--muted);margin-bottom:20px}.purpose-flow span{padding:7px;background:var(--color-canvas);border-radius:6px}.scoring-extra{display:flex;align-items:center;justify-content:space-between;gap:15px;margin:24px 0;color:var(--muted);font-size:13px}.scoring-history{margin-top:24px}.scoring-history select,.score-question-select select{max-width:100%}.scoring-back{margin-bottom:20px}.score-question-select{margin-bottom:24px}.scoring-tools>.section-heading h1{font-size:26px}@media(max-width:750px){.scoring-purpose-cards{grid-template-columns:1fr}.scoring-extra{display:block}.scoring-purpose-cards article{padding:23px}.scoring-purpose-cards h2{font-size:20px}}
</style>
