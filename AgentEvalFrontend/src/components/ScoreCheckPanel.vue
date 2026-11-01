<script setup>
import MarkdownContent from './MarkdownContent.vue'
import {computed,ref,watch} from 'vue'
import {scoreCheckContext,scoreCheckPrompt} from '../score-check-prompt.js'
import WorkspaceIcon from './WorkspaceIcon.vue'
import ScoreRecovery from './ScoreRecovery.vue'
const props=defineProps({view:Object,caseId:String,behaviorResult:Object,runId:String,thresholds:Object,canReview:Boolean})
const emit=defineEmits(['review'])
const context=computed(()=>scoreCheckContext(props)),prompt=computed(()=>scoreCheckPrompt(context.value))
const bounded=computed(()=>context.value?.本次提问的内容边界?.some(v=>/仅附前|未附完整|未取得完整/.test(v)))
const notice=ref(''),failed=ref(false),showPrompt=ref(false),showMaterials=ref(false),regrade=ref(false)
watch(()=>[props.view?.run.run_id,props.runId,props.caseId],()=>{notice.value='';failed.value=false;showPrompt.value=false;showMaterials.value=false;regrade.value=false})
async function copy(){
 if(!prompt.value)return
 try{await navigator.clipboard.writeText(prompt.value);failed.value=false;notice.value='已复制，直接粘贴到你常用的 AI 即可。'}
 catch{failed.value=true;showPrompt.value=true;notice.value='未能自动复制，请在下方选中提问后复制。'}
}
</script>
<template>
 <section class="score-check-panel" aria-label="检查本题评分">
  <template v-if="context">
   <div class="score-check-selected"><span>本题材料已自动带入</span><h3>{{context.用户问题}}</h3><p>原判：{{context.原评分.状态}}<span v-if="context.当前人工复核?.状态!=='尚无人评'&&context.当前人工复核"> · 当前人评：{{context.当前人工复核.状态}}</span></p></div>
   <div class="score-copy-card"><WorkspaceIcon name="chat" :size="30"/><div><h3>让 AI 帮你看看，原评分是否合理</h3><p>已整理本题的问题、回答、依据和原评分，不用自己拼材料。</p><button type="button" class="primary" @click="copy">复制提问给 AI</button><button type="button" class="text-button" @click="showPrompt=!showPrompt">{{showPrompt?'收起提问':'查看提问'}}</button><small>在本地整理，复制不会发送给 AI，也不会运行评测。</small></div></div>
   <p v-if="bounded" class="muted">部分材料较长或原记录不完整，提问中已注明范围，需要时请补充原文。</p>
   <p v-if="notice" role="status" :class="['note',failed?'warning':'positive']">{{notice}}</p>
   <label v-if="showPrompt">本题提问<textarea readonly :value="prompt" rows="9" @focus="$event.target.select()" /></label>
   <div class="score-local-actions"><p>也可以自行核对本题，原评分继续保留。</p><div class="button-row"><button v-if="canReview" type="button" class="secondary" @click="emit('review')">我来复核这题</button><button v-if="view?.run.verify_answers&&!view?.run.fixed_answer_review" type="button" class="secondary" @click="regrade=!regrade">{{regrade?'收起本站重评':'在本站重新打分'}}</button><button type="button" class="text-button" @click="showMaterials=!showMaterials">{{showMaterials?'收起本题材料':'查看本题材料'}}</button></div></div>
   <div v-if="showMaterials" class="score-materials"><h4>客服原回答</h4><MarkdownContent class="preserved-answer" :source="context.客服原回答||context.问答记录?.map(t=>t.客服回答).join('\n\n')" /><h4>原评分理由</h4><p>{{context.原评分.理由}}</p><template v-for="[title,items] in [['当时给客服的资料',context.当时给客服的资料],['完整参考规则',context.完整参考规则]]" :key="title"><h4>{{title}}</h4><p v-if="!items?.length" class="muted">原记录未附这部分资料。</p><blockquote v-for="(item,i) in items" :key="i"><small>{{item.编号}}</small><p>{{item.原文}}</p></blockquote></template></div>
   <ScoreRecovery v-if="regrade" :view="view" :case-id="caseId" />
  </template>
  <p v-else class="note">没有找到这道题的已保存记录，请从本题结果旁重新打开。不会改为读取另一道题。</p>
 </section>
</template>
<style scoped>
.score-check-selected{margin-bottom:22px}.score-check-selected>span{font-size:11px;color:var(--muted)}.score-check-selected h3{font-size:18px;line-height:1.7}.score-check-selected>p{font-size:13px;color:var(--muted)}.score-copy-card{display:flex;align-items:flex-start;gap:16px;background:#f0f3e9;padding:22px;border:1px solid #e2e7d7;border-radius:12px}.score-copy-card>svg{flex-shrink:0;color:#748360;margin-top:5px}.score-copy-card h3{margin:0 0 8px;font-size:17px}.score-copy-card p{font-size:13px;line-height:1.8;margin:0 0 16px}.score-copy-card small{display:block;color:var(--muted);font-size:11px;margin-top:14px}.score-copy-card .text-button{margin-left:12px}.score-local-actions{margin-top:24px}.score-local-actions>p{font-size:13px;color:var(--muted)}.score-local-actions .button-row{flex-wrap:wrap}.score-check-panel textarea{margin-top:8px;font-size:12px;max-width:100%;white-space:pre-wrap;overflow-wrap:anywhere}.score-materials{border-top:1px solid var(--border);margin-top:20px}.score-materials blockquote{margin:12px 0;border-left:3px solid #dbe0d0;padding:8px 14px}.score-materials blockquote p{white-space:pre-wrap;overflow-wrap:anywhere}.score-materials small{color:var(--muted)}@media(max-width:600px){.score-copy-card{padding:17px;gap:12px}.score-copy-card>svg{width:22px}.score-copy-card h3{font-size:16px}.score-copy-card .text-button{margin:12px 0 0;display:block}}
</style>
