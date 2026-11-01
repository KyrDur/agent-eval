<script setup>
import {computed,inject,ref,watch} from 'vue'
import {api} from '../api.js'
import {cloneArtifact} from '../practice-data.js'
import {referenceDraft,passageValid} from '../source-passages.js'
import SourcePassagePicker from './SourcePassagePicker.vue'
const rag=inject('retrieval'),work=inject('workspace')
const target=computed(()=>rag.state.coverageReviewTarget),ev=computed(()=>target.value?.evalSet||rag.state.evalSet)
const selected=ref(''),facts=ref([]),reviewer=ref(''),completeness=ref('UNKNOWN'),reviewReason=ref(''),message=ref(''),busy=ref(false),editing=ref(''),sourceIndex=ref(null),sourceDataset=ref(null),sourceDocs=ref([]),actions=ref({})
const behavior=ref('ANSWER'),information=ref('UNKNOWN'),scope=ref('IN_SCOPE')
const cases=computed(()=>(ev.value?.cases||[]).filter(c=>c.partition!=='HOLDOUT')),selectedCase=computed(()=>cases.value.find(c=>c.case_id===selected.value))
try{reviewer.value=localStorage.getItem('agenteval.reviewer.v1')||''}catch{}
watch(reviewer,value=>{try{localStorage.setItem('agenteval.reviewer.v1',value)}catch{}})
watch([()=>ev.value?.index_id,()=>target.value?.runId],async([id],_,cleanup)=>{
 let active=true;cleanup(()=>active=false);sourceDocs.value=[];sourceIndex.value=null;sourceDataset.value=null;if(!id)return
 if(target.value){sourceIndex.value=target.value.index;sourceDataset.value=target.value.knowledge;sourceDocs.value=target.value.knowledge.documents;return}
 try{const index=await api.get('/knowledge-indices/'+id),data=await api.get(`/knowledge-datasets/${index.knowledge_dataset_id}?version=${index.knowledge_version}`);if(active){sourceIndex.value=index;sourceDataset.value=data;sourceDocs.value=data.documents}}catch(e){if(active)message.value=e.message}
},{immediate:true})
watch([()=>ev.value?.retrieval_eval_set_id,()=>ev.value?.version,()=>target.value?.caseId],()=>{selected.value=target.value?.caseId&&cases.value.some(c=>c.case_id===target.value.caseId)?target.value.caseId:cases.value.some(c=>c.case_id===selected.value)?selected.value:cases.value[0]?.case_id||''},{immediate:true})
watch([selected,()=>ev.value?.version],()=>{
 const c=selectedCase.value,req=c?.knowledge_requirements;facts.value=cloneArtifact(req?.facts||[]);actions.value={};editing.value='';message.value=''
 behavior.value=req?.expected_behavior||'ANSWER';information.value=req?.user_information||'UNKNOWN';scope.value=req?.scope||'IN_SCOPE'
 completeness.value=c?.reference_complete===true?'COMPLETE':c?.reference_complete===false?'PARTIAL':'UNKNOWN';reviewReason.value=c?.reference_completeness?.reason||''
},{immediate:true})
const allSourcesPresent=computed(()=>facts.value.length>0&&facts.value.every(f=>f.alternatives?.some(a=>a.length&&a.every(q=>passageValid(q,sourceDocs.value)))))
const allReviewed=computed(()=>facts.value.length>0&&facts.value.every(f=>['MATCH','EDIT'].includes(actions.value[f.fact_id])))
const canConfirm=computed(()=>allReviewed.value&&reviewer.value.trim()&&facts.value.every(f=>f.description.trim())&&(completeness.value!=='COMPLETE'||allSourcesPresent.value))
function add(){const f={fact_id:'fact_'+crypto.randomUUID(),description:'',alternatives:[]};facts.value.push(f);editing.value=f.fact_id;actions.value[f.fact_id]='EDIT'}
function draft(){const rows=referenceDraft(selectedCase.value,sourceDocs.value);if(!rows.length){message.value='没有找到参考答案与原文的逐字依据。请补充或核实政策，系统不会编造。';return}facts.value=rows;actions.value={};message.value='已按参考答案与原文的逐字匹配整理待核对草稿，尚未人工确认；可能遗漏必要条件。'}
function choose(f,action){actions.value[f.fact_id]=action;if(action==='EDIT')editing.value=f.fact_id}
function sourceEdited(f,value){f.alternatives=value;actions.value[f.fact_id]='EDIT'}
async function save(confirmed){
 if(confirmed&&!canConfirm.value)return
 busy.value=true;message.value=''
 try{
  const old=selectedCase.value,answerHash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(old.expected_answer||'')))).map(x=>x.toString(16).padStart(2,'0')).join('')
  const requirements={...(old.knowledge_requirements||{}),facts:facts.value.map(f=>({fact_id:f.fact_id,description:f.description,alternatives:(f.alternatives||[]).filter(a=>a.length),review_action:actions.value[f.fact_id]||'UNCERTAIN',draft_origin:f.draft_origin||null})),origin_source:old.knowledge_requirements?.origin_source||old.knowledge_requirements?.source||'USER',reviewed_answer_hash:confirmed?answerHash:null,review_status:confirmed?'CONFIRMED':'DRAFT',source:'USER',reviewer:confirmed?reviewer.value:'',reviewed_at:confirmed?new Date().toISOString():null,expected_behavior:behavior.value,user_information:information.value,scope:scope.value}
  const updated={...old,knowledge_requirements:requirements,reference_complete:confirmed?(completeness.value==='COMPLETE'?true:completeness.value==='PARTIAL'?false:null):null,reference_completeness:{reason:confirmed?reviewReason.value||'用户逐项核对本题要点及原文后声明。':'待核对草稿，不表示参考完整。',reviewer:confirmed?reviewer.value:'',source:confirmed?'USER_DECLARATION':'DRAFT'}}
  await rag.saveCoverageReview({name:ev.value.name+' · 政策核对版',split_reviewed:ev.value.split_reviewed,cases:ev.value.cases.map(c=>c.case_id===selected.value?updated:c),...(!target.value?{retrieval_eval_set_id:ev.value.retrieval_eval_set_id}:{})},target.value||{index:sourceIndex.value,knowledge:sourceDataset.value})
 }catch(e){message.value=e.message}finally{busy.value=false}
}
</script>
<template>
 <details class="panel coverage" :open="!!target"><summary>核对本题政策与参考要点</summary>
  <div class="section-heading"><h2>要点与原文，对得上吗？</h2><button v-if="target" type="button" class="text-button" @click="rag.state.coverageReviewTarget=null;work.go('evaluate')">返回原运行</button></div>
  <p>逐项核对条件与例外。不确定就保存草稿；确认仅适用于本题，原运行保留。</p>
  <p v-if="!cases.length">先准备资料和测试题。</p>
  <template v-else><label>要核对的题目<select v-model="selected"><option v-for="c in cases" :key="c.case_id" :value="c.case_id">{{c.query}}</option></select></label><details><summary>查看本题参考答案</summary><p>{{selectedCase?.expected_answer||'未提供参考答案'}}</p></details>
   <div v-if="!facts.length" class="empty-facts"><p>本题还没有政策要点。可以先按参考答案与原文的逐字匹配整理草稿，不调用模型。</p><button type="button" class="secondary" @click="draft">整理待核对草稿</button></div>
   <article v-for="(fact,i) in facts" :key="fact.fact_id" class="fact-review"><span class="eyebrow">要点 {{i+1}} · {{actions[fact.fact_id]?({MATCH:'你已选择符合',EDIT:'修改中，仍待保存',UNCERTAIN:'尚不确定'})[actions[fact.fact_id]]:'待本次核对'}}</span><h3>{{fact.description||'请补充必要要点'}}</h3><div v-for="(group,j) in fact.alternatives" :key="j"><small>{{j?'或者由以下原文支持':'对应原文（同组共同支持）'}}</small><blockquote v-for="(q,k) in group" :key="k"><p>{{q.quote}}</p><small>{{q.document_id}} · v{{sourceDataset?.version}} · {{passageValid(q,sourceDocs)?'来源文本匹配，适用性仍由你核对':'原文缺失或版本不一致'}}</small></blockquote></div><p v-if="!fact.alternatives?.length" class="note warning">没有定位到支持原文，请选择依据或标记不确定。</p>
    <div class="review-actions"><button v-for="[id,label] in [['MATCH','符合'],['EDIT','需修改'],['UNCERTAIN','不确定']]" :key="id" type="button" class="secondary" :aria-pressed="actions[fact.fact_id]===id" @click="choose(fact,id)">{{label}}</button></div>
    <details :open="editing===fact.fact_id"><summary>编辑要点与原文引用</summary><label>必要要点<input v-model="fact.description" maxlength="2000" @input="actions[fact.fact_id]='EDIT'" /></label><SourcePassagePicker :documents="sourceDocs" :version="sourceDataset?.version" :model-value="fact.alternatives" @update:model-value="sourceEdited(fact,$event)" /><button type="button" class="text-button" @click="facts.splice(i,1)">移除此要点</button></details>
   </article><button type="button" class="text-button" @click="add">补上遗漏的要点</button>
   <label>参考政策是否足以判断本题？<select v-model="completeness"><option value="UNKNOWN">还不确定</option><option value="PARTIAL">仍缺政策或必要条件</option><option value="COMPLETE">已核对，足以判断</option></select></label><p v-if="completeness==='COMPLETE'&&!allSourcesPresent" class="note warning">有要点缺少有效原文，不能确认参考完整。</p>
   <label>核对人（在工作区复用）<input v-model="reviewer" maxlength="100" placeholder="填写昵称" /></label>
   <details><summary>本题适用条件与补充说明</summary><div class="form-row"><label>预期行为<select v-model="behavior"><option value="ANSWER">回答</option><option value="CLARIFY">澄清</option><option value="UNSUPPORTED">说明不支持</option><option value="HANDOFF">转交</option></select></label><label>用户信息<select v-model="information"><option value="UNKNOWN">未知</option><option value="SUFFICIENT">足够</option><option value="NEEDS_CLARIFICATION">需要澄清</option></select></label><label>范围<select v-model="scope"><option value="IN_SCOPE">范围内</option><option value="OUT_OF_SCOPE">范围外</option><option value="CONFLICT">有冲突</option></select></label></div><label>核对依据（选填）<textarea v-model="reviewReason" rows="2" /></label></details>
   <div class="button-row"><button type="button" class="primary" :disabled="busy||!!work.state.busy||!sourceIndex||!canConfirm" @click="save(true)">确认本题核对并保存</button><button type="button" class="secondary" :disabled="busy||!!work.state.busy||!sourceIndex||!facts.length||facts.some(f=>!f.description.trim())" @click="save(false)">保存待核对草稿</button></div><p>保存为新题集后重新初测；不会把旧运行或其他题改为已审核。</p>
  </template><p role="status">{{message}}</p>
 </details>
</template>
<style scoped>.coverage h2{font-size:22px;margin:20px 0}.coverage h3{font-size:18px;line-height:1.8;margin:12px 0}.coverage p{font-size:14px;line-height:1.8;white-space:pre-wrap}.coverage label{font-size:14px;margin:18px 0}.coverage select,.coverage textarea{width:100%;max-width:100%}.coverage small{font-size:14px;color:var(--muted)}.fact-review{border-block-start:1px solid var(--border);padding:24px 0;margin:20px 0}.fact-review blockquote{margin:12px 0;padding:16px 20px;background:var(--color-canvas);border-left:3px solid var(--color-line-strong)}.fact-review blockquote p{margin-bottom:10px}.review-actions{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}.review-actions [aria-pressed=true]{border:2px solid var(--color-primary);background:var(--color-success-surface)}.coverage details{margin:16px 0}.coverage .section-heading{flex-wrap:wrap}</style>
