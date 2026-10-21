<script setup>
import {computed,inject,ref,watch} from 'vue'
import {api} from '../api.js'
import {copy,questionTypes,estimateTestCalls,confirmGeneratedEvidence} from '../ai-assistance.js'
import {selectedQuestion} from '../question-navigation.js'
import QuestionNavigator from './QuestionNavigator.vue'
import AssistModel from './AssistModel.vue'
const props=defineProps({directSave:Boolean})
const emit=defineEmits(['adopt']),work=inject('workspace'),rag=inject('retrieval'),ai=inject('ai'),s=ai.tests
const sid=computed(()=>ai.modelSession||work.state.session?.provider_session_id)
const session=computed(()=>ai.modelSession?ai.providerOptions.find(s=>s.provider_session_id===ai.modelSession):work.state.session)
const ready=computed(()=>session.value?.credential_status==='PRESENT' && session.value?.text_connection_status==='READY')
const stale=computed(()=>s.draft && s.draft.content.index_id!==rag.state.index?.index_id)
const selected=computed(()=>s.cases.filter(c=>s.selected.includes(c.case_id)))
const activeId=ref(''),current=computed(()=>selectedQuestion(s.cases,activeId.value))
watch(()=>s.draft?.draft_id,()=>{activeId.value=s.cases[0]?.case_id||''})
const relatedDocuments=c=>(rag.state.knowledge?.documents||[]).filter(d=>c.relevant_document_ids.includes(d.document_id))
async function generate(){await work.action('AI 根据资料出题',async()=>{
 const draft=await api.post('/ai/tests',{request_id:crypto.randomUUID(),provider_session_id:sid.value,index_id:rag.state.index.index_id,count:s.count,question_types:s.types})
 s.draft=draft;s.cases=copy(draft.content.cases);s.selected=s.cases.map(c=>c.case_id);s.confirmed=false
})}
function adopt(){try{emit('adopt',{cases:confirmGeneratedEvidence(selected.value,s.confirmed),index_id:s.draft.content.index_id,save:props.directSave});s.confirmed=false}catch(e){work.state.notice=e.message}}
</script>
<template>
 <section class="panel ai-panel" aria-label="AI 生成测试题">
  <h2>根据资料，让 AI 出题</h2><p>生成问题和预期回答，核对后就能开始评测。</p>
  <fieldset :disabled="!!work.state.busy">
   <details class="preparation-options"><summary v-track="{action:'tests.settings',placement:'TestGenerator.control_10'}">出题设置 · {{s.count}} 道题</summary><div class="form-row"><label>生成题数<select v-model.number="s.count"><option :value="4">4 道</option><option :value="8">8 道</option><option :value="12">12 道</option></select></label></div><div class="button-row"><label class="check" v-for="type in questionTypes" :key="type"><input type="checkbox" v-model="s.types" :value="type" />{{type}}</label></div><AssistModel/></details>
   <p class="call-estimate">预计调用模型 {{estimateTestCalls(s.count)}} 次，使用当前知识资料出题。</p>
   <p v-if="!ready" class="muted">先连接模型并测试连接，即可生成题目。</p>
   <button v-track="{action:'tests.generate',placement:'TestGenerator.control_03',core:true,reason:(!ready ? 'connection' : !rag.state.index ? 'index' : 'missing_input')}" class="primary" :disabled="!ready || !rag.state.index || !s.types.length" @click="generate">{{s.draft?'重新出题':'AI 生成测试题'}}</button>
  </fieldset>
  <div v-if="s.draft" class="ai-draft">
   <p class="note positive" role="status">已生成 {{s.cases.length}} 道题。点击题号，逐题查看预期回答和原文。</p>
   <details class="generation-record"><summary>出题记录</summary><p>知识 v{{s.draft.content.knowledge_version}} · {{s.draft.provider_call_count}} 次模型调用 · AI 生成，用于调试</p><p class="muted">独立验证时，请另外准备未参与调整的题目。</p></details>
   <p v-if="stale" class="note warning">知识资料已更新，请重新出题。</p>
   <QuestionNavigator :items="s.cases" :model-value="current?.case_id" @update:model-value="activeId=$event" label="生成题目导航" />
   <fieldset :disabled="!!work.state.busy" @input="s.confirmed=false">
    <div class="button-row"><button type="button" class="text-button" @click="s.selected=s.cases.map(c=>c.case_id);s.confirmed=false">全选</button><button type="button" class="text-button" @click="s.selected=[];s.confirmed=false">取消全选</button><span class="muted">已选 {{selected.length}} / {{s.cases.length}} 题</span></div>
    <article v-if="current" :key="current.case_id" class="builder-card generated-question">
     <h3>{{current.query}}</h3><label class="check"><input type="checkbox" v-model="s.selected" :value="current.case_id" />保留这道题</label>
     <h4>预期回答</h4><p class="expected-answer">{{current.expected_answer}}</p>
     <details><summary>检查预期行为与原文依据</summary><p>需要说清：{{current.must_do.join('；')}}</p><p v-if="current.must_not_do.length">需要避免：{{current.must_not_do.join('；')}}</p><blockquote v-for="(q,i) in current.generation.source_quotes" :key="i">{{q.quote}}</blockquote><details v-if="current.relevant_document_ids.length"><summary>查看本题相关政策全文</summary><article v-for="d in relatedDocuments(current)" :key="d.document_id"><strong>{{d.title||d.document_id}}</strong><p class="policy-full-text">{{d.text}}</p></article></details><p v-if="!current.generation.source_quotes.length" class="muted">这题超出资料范围，预期回答应说明暂时无法确认。</p></details>
     <details><summary>编辑这道题</summary><label>问题<textarea v-model="current.query" rows="2" /></label><label>预期回答<textarea v-model="current.expected_answer" rows="3" /></label></details>
    </article>
   </fieldset>
   <label class="check"><input v-track="{action:'tests.confirm_draft',placement:'TestGenerator.control_08'}" type="checkbox" v-model="s.confirmed" />我已核对：各题资料足够判断，资料外的问题应如实说明</label>
   <button v-track="{action:'tests.adopt',placement:'TestGenerator.control_09'}" class="primary" :disabled="!s.confirmed || stale || !selected.length || !!work.state.busy" @click="adopt">{{props.directSave?`保存 ${selected.length} 道题，开始评测 →`:`添加这 ${selected.length} 道题`}}</button>
  </div>
 </section>
</template>
<style scoped>
.policy-full-text,.expected-answer{white-space:pre-wrap;line-height:1.8;overflow-wrap:anywhere}.generated-question h3{margin-top:0}.generated-question h4{margin-bottom:8px}.generated-question details{margin:14px 0}.generation-record{font-size:13px}.generation-record p{font-size:12px}.generated-question blockquote{margin:12px 0;padding:8px 12px;border-left:3px solid var(--color-line,#ddd);white-space:pre-wrap}
</style>
