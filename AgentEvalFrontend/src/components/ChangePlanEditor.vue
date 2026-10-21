<script setup>
import {computed,ref,watch} from 'vue'
import WorkspaceIcon from './WorkspaceIcon.vue'
import WorkspaceDrawer from './WorkspaceDrawer.vue'
import RerankHelp from './RerankHelp.vue'
import {proposedChange,changeAnalysisPrompt} from '../change-analysis-prompt.js'
import {questionStatus,answerExplanation} from '../question-navigation.js'
import {excerpt} from '../visual-results.js'
const props=defineProps({view:Object,caseId:String,type:String,nextK:Number,answerPrompt:String,defaultAnswerPrompt:String,index:Object,knowledge:Object,options:Array,busy:Boolean,locked:Boolean,confirmed:Boolean,note:String,preview:Object,canPreview:Boolean})
const emit=defineEmits(['update:caseId','update:type','update:nextK','update:answerPrompt','update:confirmed','update:note','submit','return','knowledge','preview'])
const panel=ref(''),contextTab=ref('answer'),copyNotice=ref(''),copyFailed=ref(false)
const selected=computed(()=>props.view?.run.case_results.find(c=>c.case_id===props.caseId))
const answer=computed(()=>props.view?.effective_answer_results?.find(a=>a.case_id===props.caseId))
const expected=computed(()=>props.view?.run.controls.eval_set_snapshot.cases.find(c=>c.case_id===props.caseId))
const baselineConfig=computed(()=>props.view?.run.retrieval_config||{})
const analysisOptions=computed(()=>({view:props.view,caseId:props.caseId,type:props.type,nextK:props.nextK,answerPrompt:props.answerPrompt||'',defaultAnswerPrompt:props.defaultAnswerPrompt||'',index:props.index,knowledge:props.knowledge}))
const plan=computed(()=>proposedChange(analysisOptions.value))
const prompt=computed(()=>changeAnalysisPrompt(analysisOptions.value))
const references=computed(()=>(selected.value?.input_package?.evidence||[]).filter(e=>e.scope==='REFERENCE'))
const canSubmit=computed(()=>plan.value.valid&&props.confirmed&&!props.busy&&!props.locked)
watch(()=>[props.caseId,props.type,props.nextK,props.answerPrompt,props.index?.index_id,props.view?.run.run_id],()=>{copyNotice.value='';copyFailed.value=false;emit('update:confirmed',false)})
async function copyPrompt(){
 if(!prompt.value)return
 try{await navigator.clipboard.writeText(prompt.value);copyFailed.value=false;copyNotice.value='已复制，粘贴到你常用的 AI 即可。'}
 catch{copyFailed.value=true;copyNotice.value='未能自动复制，可以在下方手动复制。';panel.value='prompt'}
}
</script>
<template>
 <div class="change-plan-editor">
  <div class="change-plan-heading"><h2>看着原题，确认这次怎么试</h2><button type="button" class="text-button" @click="emit('return')">返回本题结果</button></div>
  <div class="change-plan-columns">
   <aside class="change-context" aria-label="本次修改对应的原题">
    <label>观察的题目<select :value="caseId" aria-label="观察的题目" :disabled="busy||locked" @change="emit('update:caseId',$event.target.value)"><option v-for="(c,i) in view.run.case_results" :key="c.case_id" :value="c.case_id">第 {{i+1}} 题 · {{c.query}}</option></select></label>
    <template v-if="selected"><span class="change-context-status">{{questionStatus(view,selected)}}</span><h3>{{selected.query}}</h3>
     <div class="change-answer-summary"><WorkspaceIcon name="chat" :size="21" /><div><small>原回答节选</small><p>{{excerpt(answer?.turn_evidence?.[0]?.response,110)||'本题未保存回答，请核对运行日志。'}}</p></div></div>
     <div class="change-context-reason"><small>判定理由节选</small><p>{{excerpt(answerExplanation(answer),100)}}</p></div>
     <div class="change-source-count"><WorkspaceIcon name="document" :size="17" /><span>当时提供 {{selected.results?.length||0}} 条资料</span></div>
     <button type="button" class="text-button" @click="panel='context';contextTab='answer'">查看完整回答与依据 →</button>
    </template>
   </aside>
   <section class="change-plan-controls" aria-label="确认本次实验方案">
    <fieldset :disabled="busy||locked"><label>这次选哪种改法<select :value="type" aria-label="这次选哪种改法" @change="emit('update:type',$event.target.value)"><option v-for="option in options" :key="option.value" :value="option.value">{{option.label.split('（')[0]}}</option></select></label>
     <p class="change-plan-summary">{{plan.summary}}</p>
     <label v-if="type==='TOP_K_CHANGE'">新的返回条数<input :value="nextK" type="number" min="1" max="20" @input="emit('update:nextK',$event.target.value===''?undefined:Number($event.target.value))" /></label>
     <label v-if="type==='ANSWER_PROMPT_CHANGE'">新的回答提示词<textarea :value="answerPrompt" rows="5" maxlength="16000" placeholder="填写让客服怎样使用资料回答；评分规则保持不变。" @input="emit('update:answerPrompt',$event.target.value)" /></label>
     <button v-if="type==='KNOWLEDGE_UPDATE'" type="button" class="text-button" @click="emit('knowledge')">去准备新的知识版本 →</button>
     <div class="change-test-aim"><small>这次想验证 · 系统整理，尚未验证</small><p>{{plan.aim}}</p></div>
     <p class="change-risk-hint"><WorkspaceIcon name="alert" :size="15" /><span>{{plan.risk}}</span></p>
     <button v-if="type==='RERANK_TOGGLE'" type="button" class="text-button" @click="panel='principle'">了解资料重排原理 →</button>
     <button v-if="type==='QUERY_REWRITE_TOGGLE'" type="button" class="text-button" :disabled="!canPreview" @click="emit('preview')">用模型预览改写（会调用模型）</button>
     <div v-if="preview&&type==='QUERY_REWRITE_TOGGLE'" class="note"><small>改写预览 · 尚未应用</small><p>{{preview.original_query}} → {{preview.rewritten_query}}</p></div>
     <div class="change-copy-card"><WorkspaceIcon name="log" :size="26" /><div><h4>让 AI 帮你分析为什么这样改</h4><p>已整理原题、回答、资料和拟改参数。</p><div class="button-row"><button type="button" class="secondary" :disabled="!prompt" @click="copyPrompt">复制提问给 AI</button><button type="button" class="text-button" :disabled="!prompt" @click="panel='prompt'">查看提问</button></div><small>自行粘贴给 AI，不会自动发送或调用模型。</small></div></div>
     <p v-if="copyNotice" role="status" class="change-copy-notice">{{copyNotice}}</p>
     <label class="change-optional-note">补充想法或 AI 建议（选填）<textarea :value="note" rows="2" maxlength="1200" placeholder="可以留空；如粘贴 AI 的解释，请先核对。" @input="emit('update:note',$event.target.value)" /></label>
     <p v-if="plan.problem" role="status" class="change-problem">{{plan.problem}}</p>
     <label class="check change-confirm"><input :checked="confirmed" type="checkbox" @change="emit('update:confirmed',$event.target.checked)" />确认按此方案试一次，效果以复测为准</label>
     <button type="button" class="primary" :disabled="!canSubmit" @click="emit('submit')">确认方案，准备复测 <WorkspaceIcon name="arrow" :size="17" /></button>
     <p class="change-save-note">先保存方案，不会立即应用修改或调用模型。</p>
    </fieldset>
   </section>
  </div>
  <WorkspaceDrawer :open="!!panel" :title="panel==='context'?'本题原文与依据':panel==='prompt'?'复制给 AI 的完整提问':'资料重排原理'" @close="panel=''">
   <template v-if="panel==='prompt'"><p>复制后粘贴到你常用的 AI。可以让它解释原理，也可以指出这个改法不合适。</p><button type="button" class="secondary" @click="copyPrompt">复制提问给 AI</button><p v-if="copyNotice" role="status">{{copyNotice}}</p><label>{{copyFailed?'手动复制以下内容':'完整提问内容'}}<textarea class="change-prompt-text" :value="prompt" readonly rows="22" @focus="$event.target.select()" /></label></template>
   <template v-else-if="panel==='context'&&selected"><h3>{{selected.query}}</h3><div class="drawer-tabs" role="tablist" aria-label="修改方案的参考材料"><button v-for="t in [{id:'answer',label:'原回答'},{id:'retrieval',label:'当时查到的资料'},{id:'reference',label:'参考标准'}]" :key="t.id" type="button" role="tab" :aria-selected="contextTab===t.id" @click="contextTab=t.id">{{t.label}}</button></div><template v-if="contextTab==='answer'"><p class="agent-response">{{answer?.turn_evidence?.[0]?.response||'本题未保存回答。'}}</p><h4>完整判定理由</h4><p>{{answerExplanation(answer)}}</p></template><template v-if="contextTab==='retrieval'"><p v-if="!selected.results?.length">没有保存返回片段。</p><article v-for="(r,i) in selected.results" :key="r.chunk_id" class="change-reference"><h4>{{i+1}} · {{r.document_id}}</h4><p>{{r.text}}</p></article></template><template v-if="contextTab==='reference'"><h4>预期回答</h4><p>{{expected?.expected_answer||'未记录'}}</p><article v-for="e in references" :key="e.evidence_id" class="change-reference"><h4>{{e.document_id||e.evidence_id}}</h4><p>{{e.text}}</p></article><p v-if="!references.length" class="muted">本题未附参考原文，请回到原记录核对。</p></template></template>
   <RerankHelp v-else-if="panel==='principle'" :pool="baselineConfig.candidate_pool_size" :top-k="baselineConfig.top_k" :rank="selected?.metrics.relevant_rank" />
  </WorkspaceDrawer>
 </div>
</template>
<style scoped>
.change-plan-heading{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:20px}.change-plan-heading h2{font-size:19px}.change-plan-heading>.text-button{font-size:12px;flex-shrink:0}.change-plan-columns{display:grid;grid-template-columns:minmax(0,.95fr) minmax(0,1.05fr);gap:22px;align-items:start}.change-context{position:sticky;top:20px;min-width:0;border:1px solid var(--border);border-radius:10px;background:var(--color-canvas);padding:18px}.change-context>label{font-size:11px;margin:0 0 18px}.change-context select{width:100%;min-width:0;min-height:36px;padding:8px;font-size:12px}.change-context-status{font-size:11px;color:var(--muted)}.change-context h3{font-size:18px;line-height:1.75;margin:8px 0 18px}.change-answer-summary{display:flex;align-items:flex-start;gap:11px;border-block:1px solid var(--border);padding:16px 0}.change-answer-summary>svg{color:#7c8d6b;flex-shrink:0;margin-top:3px}.change-answer-summary small,.change-context-reason small{font-size:10px;color:var(--muted)}.change-answer-summary p{font-size:13px;line-height:1.9;margin-top:6px}.change-context-reason{margin:16px 0}.change-context-reason p{font-size:12px;line-height:1.9;margin-top:6px;color:var(--muted)}.change-source-count{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--muted)}.change-context>.text-button{font-size:11px;margin-top:10px;min-height:28px}.change-plan-controls{min-width:0}.change-plan-controls fieldset{border:0;padding:0;margin:0;min-width:0}.change-plan-controls label{font-size:12px;margin:0 0 15px}.change-plan-controls input:not([type=checkbox]),.change-plan-controls select,.change-plan-controls textarea{font-size:13px}.change-plan-controls select{min-height:39px;padding:9px 11px}.change-plan-summary{font-size:14px;font-weight:500;margin:16px 0}.change-test-aim{padding:14px 15px;background:#f0f4e9;border:1px solid #dfe6d5;border-radius:8px;margin:16px 0 10px}.change-test-aim small{font-size:10px;color:#728061}.change-test-aim p{font-size:13px;line-height:1.85;margin-top:6px}.change-risk-hint{display:flex;gap:7px;align-items:flex-start;font-size:11px;line-height:1.85;color:var(--muted);margin:10px 0}.change-risk-hint svg{flex-shrink:0;margin-top:3px}.change-plan-controls .text-button{font-size:11px;min-height:30px}.change-copy-card{display:flex;align-items:flex-start;gap:12px;border:1px solid var(--border);border-radius:9px;background:var(--color-canvas);padding:16px;margin:20px 0}.change-copy-card>svg{color:#7f8f6d;flex-shrink:0;margin-top:2px}.change-copy-card>div{min-width:0}.change-copy-card h4{font-size:14px;margin:0 0 7px;line-height:1.6}.change-copy-card p{font-size:11px;color:var(--muted);line-height:1.85}.change-copy-card small{display:block;font-size:10px;color:var(--muted);line-height:1.8}.change-copy-card .button-row{margin:12px 0 9px;gap:12px}.change-copy-card .secondary{font-size:12px;min-height:37px;padding:8px 12px}.change-copy-notice{font-size:12px;color:var(--color-success);margin:12px 0}.change-optional-note{margin-top:20px!important}.change-optional-note textarea{font-size:12px;min-height:70px}.change-confirm{font-size:12px;align-items:flex-start;line-height:1.85;margin:18px 0!important}.change-confirm input{margin-top:3px}.change-plan-controls .primary{font-size:13px;gap:8px}.change-save-note{font-size:10px;color:var(--muted);margin:8px 0 0}.change-problem{font-size:12px;color:var(--color-warning);line-height:1.85;margin:15px 0}.change-reference{padding:12px 0;border-bottom:1px solid var(--border)}.change-reference h4{font-size:12px}.change-reference p{font-size:13px;line-height:1.9;white-space:pre-wrap}.change-prompt-text{font-size:12px;line-height:1.85;white-space:pre-wrap}
@media(max-width:850px){.change-plan-columns{gap:16px}.change-context{padding:15px}.change-context h3{font-size:16px}.change-copy-card{padding:13px;gap:9px}.change-copy-card>svg{width:21px}}
@media(max-width:650px){.change-plan-columns{grid-template-columns:1fr}.change-context{position:static}.change-context h3{font-size:17px}.change-answer-summary p{font-size:12px}.change-plan-heading{align-items:flex-start;gap:12px}.change-plan-heading h2{font-size:18px}.change-plan-heading>.text-button{font-size:11px;padding:0;min-height:28px}.change-plan-controls .primary{width:100%;justify-content:center}.change-context select{max-width:100%}.change-context-reason p{font-size:11px}}
</style>
