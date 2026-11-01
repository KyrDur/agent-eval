<script setup>
import {computed,ref,watch} from 'vue'
import {candidateGuidance} from '../rag-guidance.js'
import {api} from '../api.js'
import RetrievalPapers from './RetrievalPapers.vue'
const props=defineProps({view:Object,caseId:String,type:String,nextK:Number,candidatePool:Number,index:Object,retrievalMode:String,contextStrategy:String,answerPrompt:String})
const emit=defineEmits(['candidates'])
const numbers=computed(()=>candidateGuidance(props.view,props.caseId,props.type,props.nextK,props.candidatePool))
const stages=computed(()=>[
 {label:'当前',pool:numbers.value.pool,k:numbers.value.k},
 {label:'修改后',pool:numbers.value.nextPool,k:numbers.value.nextK,changed:true},
])
const row=computed(()=>props.view?.run.case_results.find(c=>c.case_id===props.caseId))
const config=computed(()=>props.view?.run.retrieval_config||{})
const selected=computed(()=>row.value?.selected_results||row.value?.results||[])
const beforeCandidates=computed(()=>row.value?.pre_rerank_results||[])
const preview=ref(null),busy=ref(false),error=ref('')
let generation=0
async function previewChunks(){
 const current=++generation,original=props.view?.run.controls.index_snapshot
 if(!original)return
 const documentId=row.value?.relevant_document_ids?.[0]||row.value?.results?.[0]?.document_id
 const chunk=props.index?.chunk_config||{...original.chunk_config,algorithm:original.chunk_config.algorithm==='source-section-v1'?'normalized-character-window-v1':'source-section-v1'}
 busy.value=true;error.value=''
 try{const target=props.index||await api.post(`/knowledge-datasets/${original.knowledge_dataset_id}/chunk-preview`,{version:original.knowledge_version,chunk_config:chunk});if(current===generation)preview.value={documentId,before:(original.chunks||[]).filter(c=>c.document_id===documentId),after:(target.chunks||[]).filter(c=>c.document_id===documentId)}}catch(e){if(current===generation)error.value=e.message}finally{if(current===generation)busy.value=false}
}
watch(()=>[props.type,props.caseId,props.index?.index_id],()=>{generation++;preview.value=null;error.value='';if(props.type==='CHUNKING_CHANGE')previewChunks()},{immediate:true})
const query=computed(()=>row.value?.effective_query||row.value?.query||'未记录')
const adjacent=computed(()=>{
 const ids=new Set(selected.value.map(c=>c.chunk_id)),chunks=props.view?.run.controls.index_snapshot.chunks||[]
 return chunks.filter(c=>!ids.has(c.chunk_id)&&selected.value.some(s=>c.document_id===s.document_id&&(Math.abs(c.chunk_index-s.chunk_index)===1))).slice(0,4)
})
const missing=computed(()=>(row.value?.evidence_path?.knowledge?.facts||[]).filter(f=>!f.included))
const matchingModes={VECTOR:'语义查找',BM25:'关键词查找',HYBRID:'关键词 + 语义合并排序'}
</script>
<template>
 <section v-if="['CANDIDATE_POOL_CHANGE','TOP_K_CHANGE'].includes(type)" class="change-guide" aria-label="候选池与 Top K 的区别">
  <div class="retrieval-guide-heading"><h3>这次会改什么</h3><span>设置上限示意</span></div>
  <div class="retrieval-comparison">
   <div v-for="stage in stages" :key="stage.label" class="retrieval-stage" :class="{'proposed-stage':stage.changed}">
    <span class="stage-label">{{stage.label}}</span>
    <div class="retrieval-stage-group" :class="{'changed-number':stage.changed&&type==='CANDIDATE_POOL_CHANGE'}"><span>先找最多 <strong>{{stage.pool??'—'}}</strong> 条</span><RetrievalPapers :count="stage.pool" /></div>
    <div class="selection-arrow"><span>{{numbers.rerank?'重排后':'排序后'}}</span><span aria-hidden="true">→</span></div>
    <div class="retrieval-stage-group" :class="{'changed-number':stage.changed&&type==='TOP_K_CHANGE'}"><span>给模型最多 <strong>{{stage.k??'—'}}</strong> 条</span><RetrievalPapers :count="stage.k" selected /></div>
   </div>
  </div>
  <p class="diagram-key"><span><b>候选范围</b> · 先找多少条</span><span><b>Top K</b> · 最后给模型多少条</span></p>
  <div class="previous-run"><span>上次实际：找到 {{numbers.actual??'未记录'}} 条 · 提供 {{row?.results?.length??'未记录'}} 条</span><button type="button" class="text-button" @click="emit('candidates')">查看记录 →</button></div>
  <p v-if="numbers.limitedByCorpus" class="note warning">{{numbers.limitedByCorpus}}</p><p v-else-if="numbers.caution" class="note warning">{{numbers.caution}}</p>
  <p v-if="type==='TOP_K_CHANGE'" class="guide-caption">实际提供条数还受可用片段和上下文长度限制，可能少于设置上限。</p>
 </section>
 <section v-else-if="type==='CHUNKING_CHANGE'" class="change-guide" aria-label="切块方式操作引导">
  <p class="guide-caption">把长文档分成便于查找的小段。对照同一段原文的切线，检查条件与例外；当前仍是探索方案。</p>
  <p v-if="busy" role="status">正在读取同版本的切块预览…</p><p v-if="error" role="status">{{error}} <button type="button" class="text-button" @click="previewChunks">重新读取预览</button></p>
  <div v-if="preview" class="chunk-preview"><small>本题原文 · {{preview.documentId||'未找到对应文档'}} · 仅切块预览，尚未建索引</small><div class="chunk-preview-columns"><section v-for="[key,title] in [['before','初测切法'],['after','本次切法']]" :key="key"><strong>{{title}}</strong><div class="chunk-scroll"><article v-for="(c,i) in preview[key]" :key="c.chunk_id"><small>片段 {{i+1}} · 原文 {{c.source_start??'旧记录未提供'}}–{{c.source_end??'旧记录未提供'}}</small><p>{{c.text}}</p></article><p v-if="!preview[key].length">这份记录没有该文档的片段。</p></div></section></div></div>
  <details><summary>为什么条款切分仍需复测？</summary><p>它按标题与句子边界切分，不理解业务政策；过长条款仍会拆开，条件也可能跨章节。</p></details>
 </section>
 <section v-else-if="type==='RERANK_TOGGLE'" class="change-guide" aria-label="排序变化"><div class="method-flow"><div><small>初测候选顺序</small><ol><li v-for="(c,i) in beforeCandidates.slice(0,5)" :key="c.chunk_id">{{i+1}} · {{c.document_id}} <span>{{c.chunk_id}}</span></li></ol><p v-if="!beforeCandidates.length">旧记录未提供</p></div><span aria-hidden="true">→</span><div><small>本次{{config.rerank?'关闭':'开启'}}重排</small><p>对同一批候选{{config.rerank?'沿用查找顺序':'重新评分排序'}}</p><strong>再选前 {{config.top_k}} 条</strong><p>新顺序需运行后才能知道。</p></div></div></section>
 <section v-else-if="type==='CONTEXT_STRATEGY_CHANGE'" class="change-guide" aria-label="上下文补全变化"><div class="method-flow"><div><small>初测命中</small><p v-for="c in selected.slice(0,2)" :key="c.chunk_id" class="passage">{{c.text}}</p></div><span aria-hidden="true">+</span><div><small>同版本相邻原文 · {{contextStrategy==='SELECTED'?'本次不补全':'候选补充'}} </small><p v-for="c in adjacent" :key="c.chunk_id" class="passage added">{{c.text}}</p><p v-if="!adjacent.length">未定位到相邻原文，不能声称能补回条件。</p></div></div><p class="guide-caption">实际补入范围以{{contextStrategy==='PARENT'?'父章节':'所选策略'}}、去重及长度裁剪记录为准。</p></section>
 <section v-else-if="type==='QUERY_REWRITE_TOGGLE'" class="change-guide" aria-label="检索问法变化"><div class="method-flow"><div><small>用户原问题 · 不变</small><p>{{row?.query}}</p></div><span aria-hidden="true">→</span><div><small>检索用问法</small><p>{{config.query_rewrite?'本次使用用户原问题':'本次由模型换一种问法查资料'}}</p><details><summary>初测实际查找问句</summary><p>{{query}}</p></details></div></div></section>
 <section v-else-if="type==='RETRIEVAL_MODE_CHANGE'" class="change-guide" aria-label="查找方式变化"><div class="method-flow"><div><small>初测</small><strong>{{matchingModes[config.retrieval_mode||'VECTOR']}}</strong><p>{{row?.query}}</p></div><span aria-hidden="true">→</span><div><small>本次</small><strong>{{matchingModes[retrievalMode]||'待选择'}}</strong><p>{{retrievalMode==='HYBRID'?'两路结果 → 合并排序 → 选取资料':'重新查找 → 排序 → 选取资料'}}</p></div></div></section>
 <section v-else-if="type==='EMBEDDING_CHANGE'" class="change-guide" aria-label="资料匹配模型变化"><div class="method-flow"><div><small>同一句问题</small><p>{{row?.query}}</p><strong>{{view.run.controls.index_snapshot.embedding_snapshot.model}}</strong></div><span aria-hidden="true">→</span><div><small>另一匹配模型</small><strong>{{index?.embedding_snapshot?.model||(view.run.controls.index_snapshot.embedding_snapshot.model==='BAAI/bge-small-zh-v1.5'?'all-MiniLM-L6-v2':'BAAI/bge-small-zh-v1.5')}}</strong><p>同版原文与切法；重新编码后再比较召回。</p></div></div></section>
 <section v-else-if="type==='KNOWLEDGE_UPDATE'" class="change-guide" aria-label="资料缺口"><div class="method-flow"><div><small>待核实的缺口</small><p v-for="f in missing" :key="f.fact_id">{{f.description}}</p><p v-if="!missing.length">未记录具体缺失要点，请先核对政策。</p></div><span aria-hidden="true">→</span><div><small>经你核实的新原文</small><strong>v{{view.run.controls.knowledge_snapshot.version}} → {{index?'v'+index.knowledge_version:'待补充'}}</strong><p>切法、匹配模型和原题保持一致。</p></div></div></section>
 <section v-else-if="type==='ANSWER_PROMPT_CHANGE'" class="change-guide" aria-label="回答规则变化"><div class="method-flow"><div><small>原规则与资料</small><strong>沿用原规则</strong><p>初测提供 {{row?.results?.length??'未记录'}} 条资料</p></div><span aria-hidden="true">→</span><div><small>选意图 / 局部修改</small><strong>生成可查看的新提示词</strong><p>原题与评分保持不变。</p></div></div></section>
</template>
<style scoped>
.retrieval-guide-heading{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:0 0 18px}.retrieval-guide-heading h3{font-size:20px;line-height:1.5;margin:0}.retrieval-guide-heading>span{font-size:12px;color:var(--muted)}.retrieval-comparison{display:grid;gap:8px}.retrieval-stage{display:grid;grid-template-columns:64px minmax(0,1fr) 46px minmax(0,1fr);gap:14px;align-items:center;border:1px solid #e6e8e1;border-radius:8px;padding:12px 16px;background:#fafbf9}.retrieval-stage.proposed-stage{background:#edf2e8;border-color:#edf2e8}.stage-label{white-space:nowrap;font-size:14px;font-weight:600;background:#eef0eb;padding:8px 9px;border-radius:5px;text-align:center}.proposed-stage .stage-label{background:#dce5d4}.retrieval-stage-group{min-width:0;display:grid;gap:4px}.retrieval-stage-group>span{line-height:1.3;font-size:14px;white-space:nowrap}.retrieval-stage-group strong{font-size:28px;font-weight:600;margin-inline:2px}.changed-number strong{color:#425a3d}.selection-arrow{display:grid;justify-items:center;color:var(--muted);font-size:12px;gap:8px}.selection-arrow>span:last-child{font-size:26px}.diagram-key{display:flex;justify-content:center;gap:18px;margin:16px 0!important;color:var(--muted);font-size:13px!important}.diagram-key b{font-weight:500}.previous-run{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:13px;color:var(--muted)}.previous-run button{font-size:13px;white-space:nowrap}
@media(max-width:1150px){.retrieval-stage{grid-template-columns:46px minmax(0,1fr) 24px minmax(0,1fr);gap:8px;padding:14px 10px}.retrieval-stage-group>span{font-size:13px}.retrieval-stage-group strong{font-size:24px}.selection-arrow>span:first-child{display:none}.stage-label{padding:7px 4px}}
@media(max-width:560px){.retrieval-stage{grid-template-columns:minmax(0,1fr) 18px minmax(0,1fr);padding:12px;gap:6px}.stage-label{grid-column:1/-1;justify-self:start;padding:4px 10px;margin-bottom:6px}.retrieval-stage-group>span{font-size:12px}.retrieval-stage-group strong{font-size:23px}.diagram-key{flex-direction:column;gap:4px!important;margin:12px 0!important}.previous-run{flex-wrap:wrap}.retrieval-guide-heading h3{font-size:18px}.retrieval-guide-heading>span{font-size:12px}}

.change-guide{padding:0;margin:16px 0 20px}.change-guide p{font-size:14px;line-height:1.8}.guide-caption{color:var(--muted);margin:10px 0}.retrieval-flow{list-style:none;display:grid;grid-template-columns:1fr 60px 1fr;gap:12px;padding:0;margin:24px 0}.retrieval-flow li:not(.flow-link){display:grid;gap:12px;padding:20px;background:var(--color-canvas);border:1px solid var(--border);border-radius:10px}.retrieval-flow small,.retrieval-flow li>span{font-size:14px;color:var(--muted)}.retrieval-flow strong{font-size:30px;font-weight:500;white-space:nowrap}.retrieval-flow strong span{color:var(--muted);font-size:20px}.retrieval-flow .changing{border-color:var(--color-primary);background:var(--color-success-surface)}.flow-link{display:flex;flex-direction:column;justify-content:center;align-items:center;gap:10px;font-size:14px;color:var(--muted)}.flow-link>span:last-child{font-size:26px}.chunk-preview-columns,.method-flow{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:16px 0}.chunk-preview-columns>section,.method-flow>div{min-width:0}.chunk-scroll{max-height:340px;overflow:auto;padding-right:6px}.chunk-preview-columns article{padding:14px 0;border-bottom:2px dashed var(--color-line-strong)}.chunk-preview-columns p{white-space:pre-wrap;margin:8px 0}.change-guide small{font-size:14px;line-height:1.8;color:var(--muted)}.method-flow{grid-template-columns:minmax(0,1fr) 22px minmax(0,1fr);align-items:center}.method-flow>div{background:var(--color-canvas);padding:16px;border-radius:8px;overflow-wrap:anywhere}.method-flow strong{display:block;font-size:16px;line-height:1.8;margin:8px 0}.method-flow>span{font-size:24px;color:var(--muted)}.method-flow ol{padding-left:18px;font-size:14px}.method-flow li{margin:10px 0}.method-flow li span{display:block;color:var(--muted);font-size:12px;overflow-wrap:anywhere}.passage{max-height:145px;overflow:auto;padding:10px;border-left:2px solid var(--border)}.passage.added{border-color:var(--color-primary);background:var(--color-success-surface)}
@media(max-width:560px){.retrieval-flow{grid-template-columns:1fr 26px 1fr;gap:6px}.retrieval-flow li:not(.flow-link){padding:12px 8px}.retrieval-flow strong{font-size:24px}.retrieval-flow small,.retrieval-flow li>span{font-size:14px}.flow-link span:first-child{display:none}.chunk-preview-columns,.method-flow{grid-template-columns:1fr}.method-flow>span{transform:rotate(90deg);text-align:center}}
</style>
