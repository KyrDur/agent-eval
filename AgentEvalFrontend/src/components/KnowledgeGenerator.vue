<script setup>
import {inject,computed} from 'vue'
import {api} from '../api.js'
import {copy} from '../ai-assistance.js'
import AssistModel from './AssistModel.vue'
const props=defineProps({editing:Boolean,hasContent:Boolean})
const emit=defineEmits(['preview']),work=inject('workspace'),ai=inject('ai'),s=ai.knowledge
const sid=computed(()=>ai.modelSession||work.state.session?.provider_session_id)
const ready=computed(()=>!!sid.value && s.scenario.trim().length>=5)
function preview(category=null){emit('preview',{name:s.name,documents:s.documents,category});s.confirmed=false}
async function generate(category=null){await work.action(category?'重新生成一类知识':'AI 生成并填写知识资料',async()=>{
 const draft=await api.post('/ai/knowledge',{request_id:crypto.randomUUID(),provider_session_id:sid.value,scenario:s.scenario,facts:s.facts},{regenerate:!!category})
 if(category){const d=draft.content.documents.find(d=>d.metadata.category===category),at=s.documents.findIndex(d=>d.metadata.category===category),old=s.documents[at].document_id;s.documents[at]=copy(d);s.selected=s.selected.map(id=>id===old?d.document_id:id)}
 else {s.draft=draft;s.documents=copy(draft.content.documents);s.name=draft.content.name;s.selected=s.documents.map(d=>d.document_id)}
 preview(category)
})}
defineExpose({generate,ready})
</script>
<template>
 <section class="panel ai-panel" aria-label="AI 生成知识库">
  <h2>让 AI 帮你准备资料</h2><p>描述你的店铺，AI 会生成 8 类模拟资料，供这次实验使用。</p>
  <fieldset :disabled="!!work.state.busy">
   <label>电商场景<textarea v-track="{action:'knowledgegenerator.edit_start',placement:'KnowledgeGenerator.editor',kind:'edit'}" v-model="s.scenario" rows="2" maxlength="1500" placeholder="例如：一家销售耳机和音箱的电商，面向国内消费者。" /></label>
   <label>已有规则（可选）<textarea v-track="{action:'knowledgegenerator.edit_start',placement:'KnowledgeGenerator.editor',kind:'edit'}" v-model="s.facts" rows="2" maxlength="12000" placeholder="例如：品牌名、商品特点、已有售后政策；没有提供的规则将作为模拟设定。" /></label>
   <AssistModel/><p class="call-estimate">生成一次约调用模型 1 次。</p>
   <p v-if="hasContent" class="muted">生成的资料会填入下方编辑区。要沿用的规则，请填在上方。</p>
   <button v-track="{action:'knowledge.generate',placement:'KnowledgeGenerator.control_01',core:true,reason:(!sid ? 'connection' : 'missing_input')}" class="primary" :disabled="!ready" @click="generate()">{{hasContent?'重新生成资料':'生成资料'}}</button>
   <button v-track="{action:'knowledge.setup',placement:'KnowledgeGenerator.control_02'}" class="text-button" v-if="!sid" @click="work.go('setup')">先连接模型 →</button>
  </fieldset>
  <p v-if="s.draft && editing" class="note positive" role="status">资料已生成。到下方查看内容，确认后保存。</p>

 </section>
</template>
