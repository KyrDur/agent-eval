<script setup>
import {computed,ref,watch} from 'vue'
import WorkspaceIcon from './WorkspaceIcon.vue'
import WorkspaceDrawer from './WorkspaceDrawer.vue'
import {careerProjectContext,careerProjectPrompt} from '../career-project-prompt.js'
const props=defineProps({kind:String,experiment:Object,evidence:Object,careerView:Object,conclusions:Array,busy:Boolean})
const emit=defineEmits(['history','evaluate'])
const options=computed(()=>({kind:props.kind,experiment:props.experiment,evidence:props.evidence,careerView:props.careerView,conclusions:props.conclusions||[]}))
const context=computed(()=>careerProjectContext(options.value))
const prompt=computed(()=>careerProjectPrompt(options.value))
const viewer=ref(false),notice=ref(''),copyFailed=ref(false)
const summary=computed(()=>{
 const data=context.value
 if(!data)return []
 return [{icon:'chart',label:'首次评测',value:`${data.原始初测.已保存题目数} 道题`,detail:`${data.原始初测.有效判定题数} 题有有效判定`},
 {icon:'adjust',label:'修改方案',value:data.已保存的修改?.改法||'尚未记录',detail:data.已保存的修改?.已回退?'已回退':data.已保存的修改?.应用状态||'按实际进度整理'},
 {icon:'compare',label:'复测与比较',value:typeof data.前后比较==='object'?'已有比较':typeof data.复测==='object'?(data.复测.状态==='正在运行'?'正在复测':data.复测.状态==='运行失败'?'复测失败':data.复测.状态==='尚未开始'?'复测尚未开始':'已有复测'):'尚未复测',detail:typeof data.前后比较==='object'?'带上结果与适用范围':'不会写成已经提升'}]
})
watch(prompt,()=>{notice.value='';copyFailed.value=false})
async function copy(){
 if(!prompt.value)return
 try{await navigator.clipboard.writeText(prompt.value);copyFailed.value=false;notice.value='已复制，粘贴给支持联网的 AI 即可。'}
 catch{copyFailed.value=true;notice.value='未能自动复制，请在查看区手动复制。';viewer.value=true}
}
</script>
<template>
 <div class="career-prompt-page">
  <div class="page-heading"><div><h1>把做过的事，交给 AI 帮你讲清楚。</h1><p>已整理本次实验记录，并写好去牛客等网站查资料的要求。</p></div></div>
  <section v-if="context" class="panel career-prompt-main" aria-label="项目整理提问">
   <div class="career-record-heading"><div class="career-record-title"><span class="career-record-icon"><WorkspaceIcon name="folder" :size="25" /></span><div><small>当前实验记录</small><h2>不用从空白页开始写</h2></div></div><span class="career-record-tag">{{context.原始初测.状态==='正在运行'?'记录仍在更新':'按已保存的操作整理'}}</span></div>
   <div class="career-record-grid"><article v-for="item in summary" :key="item.label"><WorkspaceIcon :name="item.icon" :size="22" /><div><small>{{item.label}}</small><strong>{{item.value}}</strong><span>{{item.detail}}</span></div></article></div>
   <div class="career-prompt-path" aria-label="整理步骤"><span><b>1</b>带上我的记录</span><WorkspaceIcon name="arrow" :size="18" /><span><b>2</b>让 AI 查参考</span><WorkspaceIcon name="arrow" :size="18" /><span><b>3</b>写成求职表达</span></div>
   <div class="career-copy-area"><div><h3>一份提问，带走整个项目过程</h3><p>请 AI 参考牛客面经与项目复盘，结合你做过的事，写简历要点、面试讲述和追问回答。</p><div class="button-row"><button type="button" class="primary" :disabled="busy||!prompt" @click="copy"><WorkspaceIcon name="document" :size="18" />复制提问给 AI</button><button type="button" class="text-button" @click="viewer=true">查看完整提问 →</button></div><p v-if="notice" role="status" class="career-copy-notice">{{notice}}</p><small>复制后粘贴给你常用的 AI；支持联网时，可按要求查找参考。</small></div><div class="career-output-note" aria-label="AI 整理的内容"><WorkspaceIcon name="chat" :size="25" /><span>简历项目经历</span><span>面试讲述</span><span>项目复盘与追问</span></div></div>
  </section>
  <section v-else class="panel career-prompt-empty"><WorkspaceIcon name="folder" :size="38" /><h2>先留下你做过的记录</h2><p>完成一次评测后，这里会自动准备好提问和项目上下文。</p><button type="button" class="primary" @click="emit('evaluate')">去做一次评测 <WorkspaceIcon name="arrow" :size="17" /></button></section>
  <div class="career-prompt-footer"><p>背景和角色已带入；未做完的部分会保留真实进度。</p><button type="button" class="text-button" @click="emit('history')">查看历史材料</button></div>
  <WorkspaceDrawer :open="viewer" title="复制给 AI 的项目整理提问" @close="viewer=false"><p>已带上当前实验记录。让 AI 先查参考，再基于实际进度写作。</p><button type="button" class="primary" @click="copy">复制提问给 AI</button><p v-if="notice" role="status">{{notice}}</p><label>{{copyFailed?'手动复制以下内容':'完整提问内容'}}<textarea class="career-prompt-text" :value="prompt" readonly rows="24" @focus="$event.target.select()" /></label></WorkspaceDrawer>
 </div>
</template>
<style scoped>
.career-prompt-page{max-width:1100px;margin:0 auto}.career-prompt-page .page-heading{margin-bottom:24px}.career-prompt-page .page-heading h1{font-size:27px}.career-prompt-page .page-heading p{font-size:13px;color:var(--muted);margin-top:10px}.career-prompt-main{padding:26px}.career-record-heading{display:flex;align-items:center;justify-content:space-between;gap:14px}.career-record-title{display:flex;align-items:center;gap:13px}.career-record-icon{display:grid;place-items:center;background:#edf1e6;color:#758267;width:48px;height:48px;border-radius:12px}.career-record-title small{font-size:11px;color:var(--muted)}.career-record-title h2{font-size:19px;margin:5px 0 0}.career-record-tag{font-size:10px;color:#79856b;white-space:nowrap}.career-record-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:26px 0}.career-record-grid article{display:flex;align-items:flex-start;gap:12px;padding:17px;border:1px solid var(--border);border-radius:9px;min-width:0}.career-record-grid article>svg{color:#80906e;margin-top:2px}.career-record-grid small{display:block;font-size:11px;color:var(--muted)}.career-record-grid strong{display:block;font-size:16px;line-height:1.6;margin-top:6px}.career-record-grid article span{font-size:10px;line-height:1.8;color:var(--muted)}.career-prompt-path{display:flex;justify-content:center;align-items:center;gap:17px;padding:19px 0 26px;font-size:12px;color:var(--muted)}.career-prompt-path>span{display:flex;align-items:center;gap:8px}.career-prompt-path b{display:grid;place-items:center;border-radius:50%;width:24px;height:24px;background:#ecf1e6;color:#748366;font-size:11px;font-weight:500}.career-prompt-path>svg{color:#a0aa96}.career-copy-area{display:flex;justify-content:space-between;gap:28px;background:var(--color-canvas);border:1px solid var(--border);border-radius:10px;padding:25px}.career-copy-area>div:first-child{max-width:560px}.career-copy-area h3{font-size:21px;margin:0 0 12px}.career-copy-area p{font-size:12px;line-height:1.9;color:var(--muted);margin:0}.career-copy-area .button-row{margin:22px 0 14px;gap:18px}.career-copy-area .primary{font-size:14px;gap:8px;padding:12px 19px}.career-copy-area .text-button{font-size:12px}.career-copy-area small{font-size:10px;line-height:1.8;color:var(--muted)}.career-output-note{flex-shrink:0;display:flex;flex-direction:column;justify-content:center;gap:11px;font-size:11px;color:#7c896b;border-left:1px solid var(--border);padding-left:25px;min-width:140px}.career-copy-notice{color:var(--color-success)!important;margin:10px 0!important}.career-prompt-footer{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-top:17px}.career-prompt-footer p{font-size:11px;color:var(--muted)}.career-prompt-footer .text-button{font-size:11px;white-space:nowrap}.career-prompt-empty{text-align:center;padding:45px}.career-prompt-empty>svg{color:#80906e;margin-bottom:20px}.career-prompt-empty h2{font-size:21px}.career-prompt-empty p{font-size:13px;color:var(--muted);margin:12px 0 24px}.career-prompt-empty .primary{margin:0 auto}.career-prompt-text{font-size:12px;line-height:1.85;white-space:pre-wrap}
@media(max-width:1050px){.career-output-note{display:none}.career-copy-area>div:first-child{max-width:none}.career-record-grid{gap:9px}.career-record-grid article{padding:13px;gap:8px}.career-prompt-page .page-heading h1{font-size:24px}}
@media(max-width:650px){.career-prompt-main{padding:18px}.career-prompt-page .page-heading h1{font-size:23px;line-height:1.65}.career-record-heading{align-items:flex-start;flex-direction:column}.career-record-tag{padding-left:60px}.career-record-grid{grid-template-columns:1fr;margin:20px 0;gap:8px}.career-record-grid article{padding:11px 13px;align-items:center}.career-record-grid article>div{display:flex;align-items:center;justify-content:space-between;flex:1;gap:8px}.career-record-grid strong{font-size:13px;margin:0}.career-record-grid article span{display:none}.career-prompt-path{gap:7px;font-size:10px;padding:8px 0 20px}.career-prompt-path>span{gap:5px}.career-prompt-path b{width:20px;height:20px;font-size:10px}.career-prompt-path>svg{width:13px}.career-copy-area{padding:18px}.career-copy-area h3{font-size:19px;line-height:1.65}.career-copy-area .button-row{flex-direction:column;align-items:stretch;gap:10px}.career-copy-area .primary{justify-content:center;font-size:13px}.career-prompt-footer{align-items:flex-start}.career-prompt-footer p{font-size:10px;line-height:1.8}}
</style>
