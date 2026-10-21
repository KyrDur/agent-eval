<script setup>
import {computed} from 'vue'
import {knowledgeSections,editKnowledgeSection,knowledgeSource} from '../knowledge-document.js'
const props=defineProps({document:{type:Object,required:true}})
const emit=defineEmits(['edit'])
const sections=computed(()=>knowledgeSections(props.document))
function edit(section,event){editKnowledgeSection(props.document,section,event.target.value);emit('edit')}
</script>
<template>
 <div class="knowledge-document-preview">
  <p class="eyebrow">{{knowledgeSource(document)}}{{document.metadata.category ? ` · ${document.metadata.category}` : ''}}</p>
  <h3>{{document.title || '待填写标题'}}</h3>
  <div class="knowledge-document-section"><h4>正文</h4><p class="preserve-lines">{{sections.body || '点击「AI 生成并填好资料」，系统会生成标题、正文和适用范围。'}}</p></div>
  <div class="knowledge-document-scope" v-if="sections.applicability || sections.exceptions"><div v-if="sections.applicability"><h4>适用条件</h4><p class="preserve-lines">{{sections.applicability}}</p></div><div v-if="sections.exceptions"><h4>例外情况</h4><p class="preserve-lines">{{sections.exceptions}}</p></div></div>
 </div>
 <details class="knowledge-document-edit" :open="!document.text.trim()">
  <summary v-track="{action:'knowledge.edit_document',placement:'KnowledgeDocumentEditor.control_01'}">按需修改内容（可选）</summary>
  <label>标题<input v-track="{action:'knowledgedocumenteditor.edit_start',placement:'KnowledgeDocumentEditor.editor',kind:'edit'}" v-model="document.title" maxlength="200" @input="emit('edit')" /></label>
  <label>正文<textarea v-track="{action:'knowledgedocumenteditor.edit_start',placement:'KnowledgeDocumentEditor.editor',kind:'edit'}" :value="sections.body" @input="edit('body',$event)" rows="5" maxlength="200000" /></label>
  <div class="form-row"><label>适用条件<textarea v-track="{action:'knowledgedocumenteditor.edit_start',placement:'KnowledgeDocumentEditor.editor',kind:'edit'}" :value="sections.applicability" @input="edit('applicability',$event)" rows="2" maxlength="2000" placeholder="如：模拟店铺的普通商品" /></label><label>例外情况<textarea v-track="{action:'knowledgedocumenteditor.edit_start',placement:'KnowledgeDocumentEditor.editor',kind:'edit'}" :value="sections.exceptions" @input="edit('exceptions',$event)" rows="2" maxlength="2000" placeholder="如：定制商品需另外核验" /></label></div>
 </details>
 <details class="knowledge-document-system"><summary v-track="{action:'knowledge.source',placement:'KnowledgeDocumentEditor.control_02'}">系统记录：来源与文档编号</summary><p>资料来源：{{knowledgeSource(document)}}</p><p>文档 ID：<code>{{document.document_id}}</code></p><p v-if="document.metadata.generation_id">生成记录：<code>{{document.metadata.generation_id}}</code></p><p class="muted">编号和来源由系统管理，用于追溯评测依据。</p></details>
</template>
