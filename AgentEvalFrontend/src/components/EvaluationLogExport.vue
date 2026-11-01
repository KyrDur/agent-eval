<script setup>
import {computed,nextTick,ref,watch} from 'vue'
import LogConsultation from './LogConsultation.vue'
import {reviewText,logScopeCases} from '../evaluation-export.js'
import {questionLabel} from '../question-navigation.js'
const props=defineProps({view:Object,comparison:Object,baselineView:Object,retestView:Object,scoreReport:Object})
const consultation=ref(null)
const selectedCaseId=ref(''),notice=ref(''),manual=ref(false),panel=ref(null)
const cases=computed(()=>logScopeCases(props))
const singleCase=computed(()=>cases.value.length===1?cases.value[0]:null)
const caseId=computed({get:()=>singleCase.value?.case_id||selectedCaseId.value,set:value=>{selectedCaseId.value=value}})
const caseLabel=row=>(row.source_number?questionLabel(row.source_number):'题目')+' · '+(row.query||'题目内容未记录')
const text=computed(()=>reviewText({...props,caseId:caseId.value}))
watch(cases,()=>{if(selectedCaseId.value&&!cases.value.some(c=>c.case_id===selectedCaseId.value))selectedCaseId.value=''})
watch(caseId,()=>{notice.value='';manual.value=false})
async function copy(){
 try{await navigator.clipboard.writeText(text.value);manual.value=false;notice.value='日志和解读提示已复制，请粘贴到 Claude 或 ChatGPT。'}
 catch{manual.value=true;notice.value='浏览器未能自动复制，请手动复制下方内容，或下载整理摘要。'}
}
async function copyCase(id){if(!cases.value.some(c=>c.case_id===id)){notice.value='这道题不在当前日志范围中。';return}caseId.value=id;await nextTick();consultation.value?.show('consult')}
defineExpose({copyCase})
function download(){
 const url=URL.createObjectURL(new Blob([text.value],{type:'text/markdown;charset=utf-8'})),a=document.createElement('a')
 a.href=url;a.download=`agent-eval-${caseId.value||props.comparison?.comparison_id||props.view?.run.run_id||'log'}.md`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
 notice.value='已下载整理摘要和解读提示，可以上传到 Claude 或 ChatGPT。'
}
</script>
<template>
 <section ref="panel" class="panel evaluation-log-export" aria-label="复制日志解读">
  <h2>运行记录与外部咨询</h2><LogConsultation ref="consultation" :score-report="scoreReport" :kind="comparison?'comparison':'case'" :view="view" :comparison="comparison" :baseline-view="baselineView" :retest-view="retestView" :case-id="caseId" :log-label="caseId?'本题完整运行日志':'完整运行日志'" />
  <p class="muted">包含题目、参考资料、模型输入输出与评分记录，并附好解读提示。复制后自行粘贴，不会自动发送或调用模型。</p>
  <div v-if="singleCase" class="fixed-log-scope" aria-label="日志范围"><small>日志范围</small><strong>{{caseLabel(singleCase)}}</strong></div>
  <label v-else>日志范围<select v-model="caseId" aria-label="日志范围"><option value="">{{scoreReport?'本次评分的全部题目':comparison?'整份前后比较':'本次全部题目'}}</option><option v-for="c in cases" :key="c.case_id" :value="c.case_id">{{caseLabel(c)}}</option></select></label>
  <div class="button-row"><button type="button" class="primary" @click="copy">复制整理摘要和解读提示</button><button type="button" class="secondary" @click="download">下载整理摘要</button></div>
  <p v-if="notice" role="status">{{notice}}</p>
  <label v-if="manual">手动复制<textarea :value="text" readonly rows="8" @focus="$event.target.select()" /></label>
 </section>
</template>
<style scoped>
.evaluation-log-export{scroll-margin-top:24px;overflow-wrap:anywhere}.evaluation-log-export>label{max-width:640px;margin:20px 0}.evaluation-log-export .muted{line-height:1.8}.evaluation-log-export textarea{font-size:12px}
.fixed-log-scope{display:grid;gap:7px;padding:14px 16px;margin:20px 0;border:1px solid var(--border);border-radius:8px;background:var(--color-canvas)}.fixed-log-scope small{font-size:12px;color:var(--muted)}.fixed-log-scope strong{font-size:14px;line-height:1.8;font-weight:500}
</style>
