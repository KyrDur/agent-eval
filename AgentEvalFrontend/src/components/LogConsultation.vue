<script setup>
import {computed,ref} from 'vue'
import WorkspaceDrawer from './WorkspaceDrawer.vue'
import WorkspaceIcon from './WorkspaceIcon.vue'
import {copyCompleteText} from '../clipboard-copy.js'
import {completeLog,consultationText} from '../consultation-material.js'
const props=defineProps({kind:{type:String,default:'case'},label:String,view:Object,comparison:Object,baselineView:Object,retestView:Object,change:Object,flow:Object,trial:Object,caseId:String,context:Object,scoreReport:Object,compact:Boolean,cards:Boolean,logsOnly:Boolean,consultOnly:Boolean,logLabel:{type:String,default:'完整运行日志'}})
const open=ref(false),tab=ref(props.logsOnly?'logs':'consult'),notice=ref(''),previewOpen=ref(false),copying=ref(false)
const options=computed(()=>({view:props.view,comparison:props.comparison,baselineView:props.baselineView,retestView:props.retestView,change:props.change,flow:props.flow,trial:props.trial,scoreReport:props.scoreReport,caseId:props.cards?'':props.caseId}))
const raw=computed(()=>JSON.stringify(completeLog(options.value),null,2))
const consult=computed(()=>consultationText({kind:props.kind,context:props.context,logOptions:options.value}))
const content=computed(()=>tab.value==='logs'?raw.value:consult.value)
const buttonLabel=computed(()=>props.label||({case:'复制本题日志问 AI',plan:'复制方案问 AI',comparison:'复制对比问 AI',resume:'复制项目材料问 AI',interview:'复制项目材料问 AI',retrospective:'复制项目材料问 AI'})[props.kind]||'复制日志问 AI')
async function copy(){
 if(copying.value)return
 copying.value=true;notice.value='正在复制完整内容…'
 try{
  await copyCompleteText(content.value)
  notice.value=tab.value==='logs'?'已复制完整日志。':'已复制全部内容，可直接粘贴给 AI。'
 }catch{notice.value='复制未成功，请下载完整文件，或展开预览手动复制。';previewOpen.value=false;open.value=true}
 finally{copying.value=false}
}
function download(){const url=URL.createObjectURL(new Blob([content.value],{type:'text/plain;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=`agent-eval-${tab.value}-${props.caseId||props.comparison?.comparison_id||props.view?.run?.run_id||'project'}.txt`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice.value='已下载完整文件。'}
function show(which='logs'){tab.value=props.logsOnly?'logs':which;previewOpen.value=false;notice.value='';open.value=true}
async function copyKind(which){tab.value=which;await copy()}
defineExpose({show})
</script>
<template>
 <div :class="['log-consultation',{compact,'consultation-cards':cards}]" :aria-label="logsOnly?'完整运行日志':'运行日志'">
  <button v-if="logsOnly" type="button" class="secondary" @click="show('logs')"><WorkspaceIcon name="log" :size="18" />{{logLabel}}</button>
  <template v-else>
   <button type="button" class="secondary" :disabled="copying" @click="copyKind('consult')">{{copying?'正在复制…':buttonLabel}}</button>
   <button v-if="!consultOnly" type="button" class="text-button" :disabled="copying" @click="show('logs')">{{logLabel}}</button>
  </template>
  <p v-if="notice&&!open" class="copy-notice" role="status">{{notice}}</p>
  <WorkspaceDrawer :open="open" :title="tab==='logs'?logLabel:'复制给 AI 的内容'" @close="open=false">
   <p class="muted">密钥已自动隐藏，日志完整保留。</p>
   <div class="button-row log-copy-actions"><button type="button" class="primary" :disabled="copying" @click="copy()">{{copying?'正在复制…':tab==='logs'?'一键复制完整日志':'一键复制全部内容'}}</button><button type="button" class="secondary" @click="download">下载完整文件</button></div>
   <p v-if="notice" class="copy-notice" role="status">{{notice}}</p>
   <details class="log-preview-panel" :open="previewOpen" @toggle="previewOpen=$event.target.open"><summary>预览内容</summary><textarea v-if="previewOpen" :value="content" aria-label="完整内容预览" readonly rows="14" class="log-preview" /></details>
  </WorkspaceDrawer>
 </div>
</template>
<style scoped>
.log-consultation{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:16px 0}.log-consultation.compact{margin:8px 0}.log-consultation button{font-size:14px;min-height:40px}.log-consultation.consultation-cards{margin:0;padding:20px;border:1px solid var(--border);border-radius:10px;background:var(--color-surface)}.copy-notice{width:100%;margin:0;font-size:14px;line-height:1.7;color:var(--color-success)}.log-preview{font:13px/1.7 var(--font-mono);white-space:pre;overflow:auto;margin:0}.log-copy-actions{margin:20px 0}.log-preview-panel{margin-top:20px}@media(max-width:500px){.log-consultation>button{justify-content:center}.log-copy-actions>button{width:100%;justify-content:center}}
</style>
