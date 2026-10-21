<script setup>
import {computed,nextTick,ref,watch} from 'vue'
import {reviewText} from '../evaluation-export.js'
import {questionLabel} from '../question-navigation.js'
const props=defineProps({view:Object,comparison:Object,baselineView:Object,retestView:Object,scoreReport:Object})
const caseId=ref(''),notice=ref(''),manual=ref(false),panel=ref(null)
const cases=computed(()=>props.comparison?props.comparison.case_pairs:(props.view?.run.case_results||[]).filter(c=>!props.scoreReport||props.scoreReport.case_ids.includes(c.case_id)))
const text=computed(()=>reviewText({...props,caseId:caseId.value}))
watch(caseId,()=>{notice.value='';manual.value=false})
async function copy(){
 try{await navigator.clipboard.writeText(text.value);manual.value=false;notice.value='日志和解读提示已复制，请粘贴到 Claude 或 ChatGPT。'}
 catch{manual.value=true;notice.value='浏览器未能自动复制，请手动复制下方内容，或下载日志。'}
}
async function copyCase(id){caseId.value=id;await nextTick();await copy();panel.value?.scrollIntoView({block:'center',behavior:'smooth'})}
defineExpose({copyCase})
function download(){
 const url=URL.createObjectURL(new Blob([text.value],{type:'text/markdown;charset=utf-8'})),a=document.createElement('a')
 a.href=url;a.download=`agent-eval-${caseId.value||props.comparison?.comparison_id||props.view?.run.run_id||'log'}.md`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
 notice.value='已下载日志和解读提示，可以上传到 Claude 或 ChatGPT。'
}
</script>
<template>
 <section ref="panel" class="panel evaluation-log-export" aria-label="复制日志解读">
  <h2>复制日志给 Claude / ChatGPT 解读</h2>
  <p class="muted">包含题目、参考资料、模型输入输出与评分记录，并附好解读提示。复制后自行粘贴，不会自动发送或调用模型。</p>
  <label>日志范围<select v-model="caseId" aria-label="日志范围"><option value="">{{scoreReport?'本评分修订的题目':comparison?'整份前后比较':'本次全部题目'}}</option><option v-for="(c,i) in cases" :key="c.case_id" :value="c.case_id">{{questionLabel(i+1)}} · {{(c.query||c.case_id).slice(0,42)}}</option></select></label>
  <div class="button-row"><button type="button" class="primary" @click="copy">复制日志和解读提示</button><button type="button" class="secondary" @click="download">下载日志</button></div>
  <p v-if="notice" role="status">{{notice}}</p>
  <label v-if="manual">手动复制<textarea :value="text" readonly rows="8" @focus="$event.target.select()" /></label>
 </section>
</template>
<style scoped>
.evaluation-log-export{scroll-margin-top:24px;overflow-wrap:anywhere}.evaluation-log-export>label{max-width:640px;margin:20px 0}.evaluation-log-export .muted{line-height:1.8}.evaluation-log-export textarea{font-size:12px}
</style>
