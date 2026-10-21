<script setup>
import {analytics} from '../analytics.js'
import { embeddingLabel, semanticModel, lexicalModel } from '../embedding-models.js'
import { cloneArtifact } from '../practice-data.js'
import { inject, ref, watch, computed, nextTick } from 'vue'
import WorkspaceIcon from '../components/WorkspaceIcon.vue'
import WorkspaceDrawer from '../components/WorkspaceDrawer.vue'
import { demoDocuments } from '../rag-demo.js'
import KnowledgeGenerator from '../components/KnowledgeGenerator.vue'
import KnowledgeDocumentEditor from '../components/KnowledgeDocumentEditor.vue'
import RetrievalWhy from '../components/RetrievalWhy.vue'
import {knowledgeSections,knowledgeSource} from '../knowledge-document.js'
const work=inject('workspace'),rag=inject('retrieval'),practice=inject('practice'),ai=inject('ai')
const generator=ref(null),draftEditing=ref(false),panel=ref(''),docIndex=ref(0)
const activeDocument=computed(()=>documents.value[docIndex.value])
function openDocument(i){docIndex.value=i;panel.value='document'}
async function regenerate(category){panel.value='generate';await nextTick();generator.value?.generate(category)}
const embeddingModel=ref(semanticModel),chunkSize=ref(200),chunkOverlap=ref(20)
watch([embeddingModel,()=>rag.state.baseline],()=>{
 const currentIndex=rag.state.index
 const baselineIndex=rag.state.baseline?.run.controls.index_snapshot
 const config=currentIndex?.embedding_snapshot.model===embeddingModel.value ? currentIndex.chunk_config : baselineIndex?.embedding_snapshot.model===embeddingModel.value ? baselineIndex.chunk_config : {chunk_size:200,chunk_overlap:20}
 chunkSize.value=config.chunk_size;chunkOverlap.value=config.chunk_overlap
})
watch(()=>rag.state.index,index=>{if(index){embeddingModel.value=index.embedding_snapshot.model;chunkSize.value=index.chunk_config.chunk_size;chunkOverlap.value=index.chunk_config.chunk_overlap}},{immediate:true})
const name=ref('我的电商知识库'),documents=ref([]),error=ref(''),ack=ref(false),dirty=ref(false)
const editorDoc=(doc,expanded=false)=>({...doc,_editorKey:crypto.randomUUID(),_expanded:expanded})
const blank=(expanded=true)=>editorDoc({document_id:'doc_'+crypto.randomUUID().replaceAll('-',''),title:'',text:'',metadata:{source:'USER_PROVIDED',applicability:''}},expanded)
watch(()=>rag.state.knowledge,k=>{name.value=k?.name || '我的电商知识库';documents.value=k?cloneArtifact(k.documents).map(({document_id,title,text,metadata})=>editorDoc({document_id,title,text,metadata},k.documents.length===1)): [blank(false)];dirty.value=false;draftEditing.value=false;ai.knowledge.confirmed=false},{immediate:true})
const selectedDocuments=computed(()=>draftEditing.value?documents.value.filter(d=>ai.knowledge.selected.includes(d.document_id)):documents.value)
const reviewRequired=computed(()=>dirty.value && selectedDocuments.value.some(d=>d.metadata.source==='AI_GENERATED_SIMULATION'))
const commonSource=computed(()=>{const sources=[...new Set(documents.value.map(knowledgeSource))];return sources.length===1?sources[0]:''})
const hasContent=computed(()=>documents.value.some(d=>d.title.trim() || d.text.trim()))
watch(name,value=>{if(draftEditing.value)ai.knowledge.name=value})
function edited(){dirty.value=true;ack.value=false;ai.knowledge.confirmed=false}
function previewGenerated(draft){name.value=draft.name;documents.value=draft.documents.map((d,i)=>Object.assign(d,{_editorKey:d._editorKey||crypto.randomUUID(),_expanded:draft.category?d.metadata.category===draft.category:i===0}));ai.knowledge.documents=documents.value;draftEditing.value=true;edited();panel.value=''}
const mixed=computed(()=>documents.value.some(d=>d.metadata.purpose==='DEMO_POLICY_NOT_BUSINESS_COMMITMENT') && documents.value.some(d=>d.metadata.purpose!=='DEMO_POLICY_NOT_BUSINESS_COMMITMENT'))
const validChunks=computed(()=>Number.isInteger(chunkSize.value) && chunkSize.value>=50 && chunkSize.value<=2000 && Number.isInteger(chunkOverlap.value) && chunkOverlap.value>=0 && chunkOverlap.value<chunkSize.value)
const validDocuments=computed(()=>!!name.value.trim() && selectedDocuments.value.length>0 && selectedDocuments.value.every(d=>!!knowledgeSections(d).body.trim() && /^[A-Za-z0-9_-]+$/.test(d.document_id)))
const indexReady=computed(()=>!dirty.value && rag.state.index?.knowledge_version===rag.state.knowledge?.version && !!rag.state.index && rag.state.index.embedding_snapshot.model===embeddingModel.value && rag.state.index.chunk_config.chunk_size===chunkSize.value && rag.state.index.chunk_config.chunk_overlap===chunkOverlap.value)
const defaultPreparation=computed(()=>embeddingModel.value===semanticModel && chunkSize.value===200 && chunkOverlap.value===20)
const indices=computed(()=>practice.state.library.indices.filter(i=>i.knowledge_dataset_id===rag.state.knowledge?.knowledge_dataset_id).sort((a,b)=>b.knowledge_version-a.knowledge_version))
function demo(){draftEditing.value=false;ai.knowledge.confirmed=false;documents.value=cloneArtifact(demoDocuments).map(d=>editorDoc(d));name.value='Demo · 电商知识库';dirty.value=true;ack.value=false}
function empty(){draftEditing.value=false;ai.knowledge.confirmed=false;documents.value=[blank()];name.value='我的电商知识库';dirty.value=true;ack.value=false;docIndex.value=0;panel.value='document'}
async function importFiles(event){error.value='';const incoming=[]
 try{for(const file of event.target.files){if(!/\.(txt|md)$/i.test(file.name) || file.size>200000)throw new Error('仅支持不超过 200 KB 的 .txt / .md 文件。');const text=await file.text();if(!text.trim())throw new Error('文件内容为空，请检查。');incoming.push({...blank(),title:file.name,text,metadata:{filename:file.name,source:'USER_UPLOADED',applicability:''}})}
  if(documents.value.length===1 && !documents.value[0].text.trim())documents.value=incoming;else documents.value.push(...incoming)
  if(draftEditing.value)ai.knowledge.selected.push(...incoming.map(d=>d.document_id));edited()
 }catch(e){error.value=e.message}event.target.value=''
}
async function prepare(){error.value='';const docs=selectedDocuments.value,ids=docs.map(d=>d.document_id)
 if(reviewRequired.value&&!ai.knowledge.confirmed){analytics.blocked('knowledge.save','unconfirmed');error.value='请先核对并确认 AI 生成的模拟资料。';return}
 if(!validDocuments.value || !validChunks.value){analytics.blocked('knowledge.save','invalid_input');error.value='请检查资料内容与高级设置；首次可使用示例资料和默认参数。';return}
 if(new Set(ids).size!==ids.length){analytics.blocked('knowledge.save','invalid_input');error.value='文档 ID 重复，请合并或使用不同 ID。';return}
 if(mixed.value&&!ack.value){analytics.blocked('knowledge.save','unconfirmed');error.value='请先确认 Demo 与自有知识的适用范围。';return}
 const body=dirty.value || !rag.state.knowledge ? {name:name.value,documents:docs.map(({document_id,title,text,metadata})=>({document_id,title,text,metadata})),...(rag.state.knowledge?{knowledge_dataset_id:rag.state.knowledge.knowledge_dataset_id}:{}),metadata:{generation_ids:[...new Set(docs.map(d=>d.metadata.generation_id).filter(Boolean))],source:docs.every(d=>d.metadata.source==='AI_GENERATED_SIMULATION')?'AI_GENERATED_SIMULATION':mixed.value?'MIXED':docs.every(d=>d.metadata.purpose==='DEMO_POLICY_NOT_BUSINESS_COMMITMENT')?'DEMO':'USER_PROVIDED'}} : undefined
 await rag.prepareKnowledge(body,{chunk_size:chunkSize.value,chunk_overlap:chunkOverlap.value},embeddingModel.value)
 if(!work.state.error){dirty.value=false;await work.action('刷新知识版本与索引',practice.library)}
}
async function build(){
 await rag.buildIndex({chunk_size:chunkSize.value,chunk_overlap:chunkOverlap.value},embeddingModel.value);if(!work.state.error)await work.action('读取知识索引',practice.library)
}
async function choose(index){await practice.useIndex(index)}
function add(){const doc=blank();documents.value.push(doc);docIndex.value=documents.value.length-1;panel.value='document';if(draftEditing.value)ai.knowledge.selected.push(doc.document_id);edited()}

</script>
<template>
 <div class="page-heading"><div><h1>准备客服能查到的资料</h1><p>{{documents.length}} 份资料 · 查看后再用于出题与评测</p></div><button type="button" class="text-button" @click="panel='settings'"><WorkspaceIcon name="adjust" :size="17" />查找设置</button></div>
 <p v-if="error" class="note danger" role="alert">{{error}}</p>
 <div class="knowledge-source-actions" aria-label="准备资料的方式"><button type="button" :disabled="!!work.state.busy" @click="panel='generate'"><WorkspaceIcon name="chat" :size="24" /><span>让 AI 准备</span></button><button type="button" :disabled="!!work.state.busy" @click="demo"><WorkspaceIcon name="book" :size="24" /><span>使用示例资料</span></button><button type="button" :disabled="!!work.state.busy" @click="panel='import'"><WorkspaceIcon name="folder" :size="24" /><span>导入自己的资料</span></button></div>
 <section class="panel visual-knowledge-library"><div class="section-heading"><div><h2>{{name}}</h2><small v-if="commonSource" class="knowledge-common-source">{{commonSource}}</small></div><button type="button" class="text-button" @click="panel='import'">编辑名称</button></div>
  <div class="knowledge-document-grid"><button v-for="(doc,i) in documents" :key="doc._editorKey" type="button" @click="openDocument(i)"><span class="knowledge-document-art"><WorkspaceIcon name="document" :size="29" /></span><strong>{{doc.title||`知识文档 ${i+1}`}}</strong><small v-if="!commonSource">{{knowledgeSource(doc)}}</small><WorkspaceIcon class="knowledge-document-link" name="arrow" :size="15" /></button><button type="button" class="knowledge-add" :disabled="!!work.state.busy" @click="add"><WorkspaceIcon name="plus" :size="26" /><strong>添加资料</strong></button></div>
  <div v-if="draftEditing" class="button-row"><button type="button" class="text-button" @click="ai.knowledge.selected=documents.map(d=>d.document_id);edited()">全选</button><button type="button" class="text-button" @click="ai.knowledge.selected=[];edited()">取消全选</button><span class="muted">已选 {{selectedDocuments.length}} / {{documents.length}} 份</span></div>
  <label class="check note" v-if="reviewRequired"><input type="checkbox" v-model="ai.knowledge.confirmed" :disabled="!!work.state.busy" />我已核对选中的模拟规则，确认用作评测资料</label>
  <label class="check note warning" v-if="mixed"><input v-model="ack" type="checkbox" />我已检查示例与自有规则的适用范围和冲突。</label>
  <p v-if="rag.state.knowledge" class="visual-saved-note">已保存 v{{rag.state.knowledge.version}} · {{rag.state.knowledge.documents.length}} 份{{dirty?' · 有未保存编辑':''}}</p>
 </section>
 <section class="knowledge-next-step" aria-label="准备评测参考规则"><div class="knowledge-process"><span><WorkspaceIcon name="document" :size="19" />资料</span><WorkspaceIcon name="arrow" :size="17" /><span><WorkspaceIcon name="list" :size="19" />出题</span><WorkspaceIcon name="arrow" :size="17" /><span><WorkspaceIcon name="chart" :size="19" />评测</span></div>
  <div class="preparation-action"><h3>{{indexReady?'资料已就绪':'核对资料，准备出题'}}</h3>

   <p v-if="!validDocuments" class="muted">还没有可用规则。先使用上方的示例资料、AI 生成，或导入自己的资料。</p>
   <p v-else-if="reviewRequired&&!ai.knowledge.confirmed" class="muted">请先勾选上方「我已核对选中的模拟规则」，再继续。</p>
   <p v-else-if="mixed&&!ack" class="muted">请先确认上方示例与自有规则的适用范围。</p>
   <div class="button-row"><button v-if="draftEditing" v-track="{action:'knowledge.adopt',placement:'KnowledgeGenerator.control_09'}" class="primary" :disabled="!!work.state.busy || !validDocuments || !validChunks || !ai.knowledge.confirmed || (mixed&&!ack)" @click="prepare">确认 {{selectedDocuments.length}} 条规则，准备出题</button><button v-else-if="!indexReady" v-track="{action:'knowledge.save',placement:'KnowledgePage.control_08',core:true,reason:(mixed && !ack || reviewRequired && !ai.knowledge.confirmed ? 'unconfirmed' : !validDocuments ? 'missing_input' : indexReady ? 'already_complete' : 'invalid_input')}" class="primary" :disabled="!!work.state.busy || !validDocuments || !validChunks || (mixed&&!ack) || (reviewRequired&&!ai.knowledge.confirmed) || indexReady" @click="prepare">{{indexReady?'规则已准备好':rag.state.knowledge && !dirty?'继续准备已保存的规则':'保存这些规则，准备出题'}}</button><button v-if="indexReady" v-track="{action:'site.navigate.define',placement:'KnowledgePage.control_17'}" class="primary" :disabled="!!work.state.busy" @click="work.go('define')">下一步：准备题目 →</button></div>
   <p v-if="work.state.busy" class="muted" role="status">{{work.state.busy}}，请稍等…</p>

   <p v-else-if="!indexReady && rag.state.knowledge && !dirty" class="muted">规则已保存，准备尚未完成。可以继续准备，无需重新填写资料。</p>
   <p v-else class="muted">资料、题目和评分标准会随本次实验保存。</p>
  </div>
 </section>
 <WorkspaceDrawer :open="!!panel" :title="({generate:'让 AI 准备资料',document:'查看与编辑资料',import:'导入与命名',settings:'资料查找设置'})[panel]||'查看资料'" @close="panel=''">
  <KnowledgeGenerator v-if="panel==='generate'" ref="generator" :editing="draftEditing" :has-content="hasContent" @preview="previewGenerated" />
  <template v-if="panel==='document'&&activeDocument"><fieldset :disabled="!!work.state.busy" @input="edited"><template v-for="doc in [activeDocument]" :key="doc._editorKey"><div v-if="draftEditing" class="section-heading"><label class="check"><input type="checkbox" v-model="ai.knowledge.selected" :value="doc.document_id" />保存这份资料</label><button v-if="doc.metadata.category&&doc.metadata.source==='AI_GENERATED_SIMULATION'" type="button" class="text-button" @click="regenerate(doc.metadata.category)">重新生成此类</button></div><KnowledgeDocumentEditor :document="doc" @edit="edited" /><button type="button" class="text-button" @click="documents.splice(docIndex,1);edited();panel=''">从新版本中移除</button></template></fieldset></template>
  <template v-if="panel==='import'"><fieldset :disabled="!!work.state.busy" @input="edited"><label>知识库名称<input v-model="name" maxlength="200" /></label><label>导入文件（.txt / .md，每个最多 200 KB）<input type="file" accept=".txt,.md" multiple @change="importFiles" /></label><button type="button" class="secondary" @click="empty">新建空白资料</button></fieldset></template>
  <template v-if="panel==='settings'">  <details class="preparation-help"><summary v-track="{action:'knowledge.preparation_help',placement:'KnowledgePage.control_16'}">系统怎样整理资料？索引与 Embedding 说明（可选）</summary>
   <p class="muted">这些处理由系统完成，了解原理后也可以在下方比较不同方案。</p><dl class="preparation-glossary"><div><dt>索引是什么？</dt><dd>像为资料制作一份“查找目录”。评测时，系统借助它定位相关内容；更新资料后，也要更新这份目录。</dd></div><div><dt>Embedding 是什么？</dt><dd>把文字转换成代表其含义的一组数字，方便比较问题和资料是否相关。它负责找资料，回答模型负责组织答案。</dd></div></dl>
   <p class="muted">默认选项的技术名称是“语义检索”：系统用 Embedding 比较问题与资料的含义，使用的模型是后端本地 MiniLM（all-MiniLM-L6-v2）。这些由系统处理，无需额外填写 API Key 或支付这一步的模型调用费；首次准备需要下载模型，可能稍等片刻。</p>
   <p class="muted">MiniLM 每个片段最多读取 256 Token（模型计算文字长度的单位）。如果提示片段过长，缩短每段字符数后重试；已保存资料仍保留。另一个选项使用词语和字符组合进行匹配，可用作评测对照。</p>
  </details>
  <details class="preparation-options"><summary v-track="{action:'knowledge.settings',placement:'KnowledgePage.control_14'}">调整资料查找方式（可选，首次保持默认）</summary><p class="muted">想评测不同的资料查找方案时，再调整这里的参数。</p><RetrievalWhy/>
   <div class="retrieval-choice"><label>资料查找方式<select v-track="{action:'knowledge.retrieval',placement:'KnowledgePage.control_10'}" v-model="embeddingModel" :disabled="!!work.state.busy" aria-describedby="knowledge-search-example"><option :value="semanticModel">按含义找资料（Embedding，默认）</option><option :value="lexicalModel">按词语找资料（用于对照）</option></select></label>
    <div id="knowledge-search-example" class="note retrieval-method-help"><template v-if="embeddingModel===semanticModel">
     <h3>Embedding 是什么？</h3><p>把文字转换成一组数字，方便电脑比较问题和资料的含义是否相关。这一步叫“文本向量化”。</p>
     <ol class="embedding-steps"><li><strong>准备资料</strong><p>把每段规则转换成数字，保存这些数字和规则原文。</p></li><li><strong>查找资料</strong><p>把用户的问题也转换成数字，再比较。比如“钱什么时候退回来？”和“退款到账时间”，说法不同，也可以尝试按含义找到对应规则。</p></li><li><strong>生成客服回答</strong><p>把找到的规则原文交给回答模型，由它组织回复。</p></li></ol>
     <p><strong>这里用哪两个模型？</strong>后端本地 MiniLM 负责做 Embedding、帮助找资料；你连接的模型负责根据资料生成回答。</p>
     <p class="muted">首次保持默认即可，系统会自动处理，无需再配置一个模型。是否找对资料、答对问题，由后面的评测验证。</p>
    </template><template v-else><h3>按词语找资料是什么？</h3><p>根据问题和资料中的词语、字符组合的匹配程度查找。比如“退款多久到账？”，会尝试找到含有“退款”“到账”等相关表达的资料。</p><p>可与默认的 Embedding 方案做对照，检查不同问法下哪个更容易找到正确规则。找到资料后，仍由你连接的回答模型组织回复。</p></template></div>
   </div><div class="form-row"><label>每段最大字符数<input v-track="{action:'knowledgepage.edit_start',placement:'KnowledgePage.editor',kind:'edit'}" type="number" v-model.number="chunkSize" min="50" max="2000" :disabled="!!work.state.busy" /></label><label>相邻段落重复的字符数<input v-track="{action:'knowledgepage.edit_start',placement:'KnowledgePage.editor',kind:'edit'}" type="number" v-model.number="chunkOverlap" min="0" :max="chunkSize-1" :disabled="!!work.state.busy" /></label></div><p class="muted">资料切分：把长文分成便于查找的小段；相邻段落保留少量重复文字，帮助保留上下文。默认每段最多 200 字符，重复 20 字符。</p><p class="muted">比较两种查找方式时，请使用同一批测试题并分别建立初测，方便判断哪种更适合你的资料。</p><button v-track="{action:'knowledge.index',placement:'KnowledgePage.control_11',core:true,reason:(!rag.state.knowledge ? 'knowledge' : dirty ? 'unsaved' : work.state.busy ? 'busy' : 'invalid_input')}" class="secondary" :disabled="!rag.state.knowledge || dirty || !validChunks || !!work.state.busy" @click="build">按当前设置重新准备资料</button>
   <p v-if="rag.state.index" class="muted">{{indexReady?'当前准备记录':'已保存的准备记录'}} · {{embeddingLabel(rag.state.index)}} · 知识 v{{rag.state.index.knowledge_version}} · {{rag.state.index.chunks.length}} 个片段</p><div class="button-row"><button v-track="{action:'knowledge.version',placement:'KnowledgePage.control_12'}" class="secondary" v-for="index in indices" :key="index.index_id" :disabled="!!work.state.busy" @click="choose(index)">选用 v{{index.knowledge_version}} · {{index.embedding_snapshot.model===semanticModel?'语义':'词汇'}}{{rag.state.index?.index_id===index.index_id?' · 当前':''}}</button></div>
  </details> <section class="panel" v-if="rag.state.baseline"><h2>验证这次知识补充</h2><p>初测使用知识 v{{rag.state.baseline.run.controls.knowledge_snapshot.version}}。知识补充实验保留原题与检索配置，比较这次资料更新的影响。</p><p v-if="rag.state.index && rag.state.index.embedding_snapshot.model!==rag.state.baseline.run.controls.embedding_snapshot.model" class="note warning">检索模型已变化。请到「测试集」另存测试并建立新初测，不能作为这轮仅知识更新的复测。</p><p class="muted">若政策变化使正确答案也变了，请另建测试和初测，并注明原因。</p><button v-track="{action:'knowledge.change',placement:'KnowledgePage.control_13'}" class="primary" :disabled="!rag.state.index || rag.state.index.index_id===rag.state.baseline.run.controls.index_snapshot.index_id || rag.state.index.embedding_snapshot.model!==rag.state.baseline.run.controls.embedding_snapshot.model || !!work.state.busy" @click="rag.state.preferredChange='KNOWLEDGE_UPDATE';work.go('improve')">记录知识补充判断 →</button></section>
</template>
 </WorkspaceDrawer>
</template>
<style scoped>
.knowledge-source-actions{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:0 0 22px}.knowledge-source-actions button{border:1px solid var(--border);border-radius:9px;background:var(--color-surface);padding:20px 16px;display:flex;align-items:center;gap:12px;font-size:13px;color:var(--color-text)}.knowledge-source-actions svg{color:#748260}.visual-knowledge-library{padding:22px}.visual-knowledge-library>.section-heading{margin:0 0 18px}.visual-knowledge-library h2{font-size:17px}.knowledge-document-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.knowledge-document-grid>button{min-width:0;position:relative;display:flex;flex-direction:column;align-items:flex-start;text-align:left;border:1px solid var(--border);border-radius:9px;background:var(--color-canvas);padding:16px;gap:8px;color:var(--color-text)}.knowledge-document-art{color:#7b896c;height:30px}.knowledge-document-grid strong{font-size:13px;line-height:1.7;font-weight:500;overflow-wrap:anywhere}.knowledge-document-grid small{font-size:10px;color:var(--muted)}.knowledge-document-link{position:absolute;bottom:13px;right:13px;color:#738267}.knowledge-document-grid>button{min-height:110px;padding-bottom:29px}.knowledge-common-source{display:block;font-size:10px;color:var(--muted);margin-top:5px}.knowledge-document-grid .knowledge-add{align-items:center;justify-content:center;min-height:110px;background:none;border-style:dashed;color:var(--muted)}.visual-saved-note{font-size:12px;color:var(--muted);margin:18px 0 0}.knowledge-next-step{display:flex;align-items:center;justify-content:space-between;gap:24px}.knowledge-process{display:flex;align-items:center;gap:12px;color:#9aa391}.knowledge-process>span{display:grid;justify-items:center;gap:8px;font-size:12px;color:var(--muted)}.knowledge-next-step .preparation-action{margin:0;background:none;border:0;padding:0;flex:1;max-width:480px}.knowledge-next-step .preparation-action h3{font-size:16px;color:var(--color-text)}.knowledge-next-step .preparation-action>.button-row{margin:12px 0}.knowledge-next-step .preparation-action p{font-size:11px}.page-heading .text-button{font-size:12px;gap:7px}
@media(max-width:850px){.knowledge-document-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.knowledge-source-actions{gap:8px}.knowledge-source-actions button{padding:14px 12px;gap:8px}.knowledge-next-step{align-items:flex-start}.knowledge-process{gap:7px}}
@media(max-width:550px){.knowledge-source-actions button{display:grid;gap:8px;justify-items:center;font-size:11px;text-align:center;padding:14px 8px}.visual-knowledge-library{padding:16px}.knowledge-document-grid>button{padding:13px;gap:6px}.knowledge-next-step{display:block}.knowledge-process{justify-content:center;margin:22px 0}.knowledge-document-grid strong{font-size:12px}.visual-knowledge-library>.section-heading{flex-wrap:wrap}.visual-knowledge-library h2{font-size:15px}}
</style>
