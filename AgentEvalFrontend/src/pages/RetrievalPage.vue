<script setup>
import { embeddingLabel, semanticModel, lexicalModel } from '../embedding-models.js'
import { computed, inject, ref, watch, onMounted, nextTick } from 'vue'
import TraceAssistant from '../components/TraceAssistant.vue'
import RunBriefing from '../components/RunBriefing.vue'
import QuestionNavigator from '../components/QuestionNavigator.vue'
import VisualResults from '../components/VisualResults.vue'
import ChangePlanEditor from '../components/ChangePlanEditor.vue'
import {proposedChange,changePlanRecord} from '../change-analysis-prompt.js'
import WorkspaceIcon from '../components/WorkspaceIcon.vue'
import {selectedQuestion,questionStatus,answerExplanation} from '../question-navigation.js'
import EvaluationLogExport from '../components/EvaluationLogExport.vue'
import RerankHelp from '../components/RerankHelp.vue'
import RunDiagnostics from '../components/RunDiagnostics.vue'
import ScoringEvidence from '../components/ScoringEvidence.vue'
import ScoreRecovery from '../components/ScoreRecovery.vue'
import ScoreReportComparison from '../components/ScoreReportComparison.vue'
import TrustedResults from '../components/TrustedResults.vue'
import RetrievalIssuePanel from '../components/RetrievalIssuePanel.vue'
import AgentHoldout from '../components/AgentHoldout.vue'
import EvidenceDetails from '../components/EvidenceDetails.vue'
import ExperimentHealth from '../components/ExperimentHealth.vue'
import MetricHelp from '../components/MetricHelp.vue'
import { retrievalMetrics } from '../retrieval-metric-help.js'
import { demoDocuments, demoCases } from '../rag-demo.js'
import {analytics} from '../analytics.js'
import { api } from '../api.js'
import { records } from '../case-import.js'
import {requiresPolicyReference} from '../ai-assistance.js'
const props=defineProps({step:String})
const work=inject('workspace'), rag=inject('retrieval'), practice=inject('practice'), {state}=rag
const calibration=inject('calibration')
const logExport=ref(null),resultWorkbench=ref(null)
async function copyCaseLog(id){if(props.step==='evaluate')resultWorkbench.value?.open('records');else compareTab.value='records';await nextTick();logExport.value?.copyCase(id)}
const name=ref('我的知识检索实验'), documents=ref([{document_id:'doc_1',title:'',text:'',metadata:{}}]), cases=ref('')
const embeddingModel=ref(semanticModel)
const scoringProfile=ref('initial-evidence-v1'),profiles=ref([]),splitReviewed=ref(false)
const policyGaps=computed(()=>(state.evalSet?.cases||[]).filter(c=>c.partition!=='HOLDOUT'&&requiresPolicyReference(c)&&c.reference_complete!==true))
async function loadProfiles(){try{profiles.value=await api.get('/retrieval-scoring-profiles')}catch{error.value='评分方案暂时无法读取。'}}
onMounted(loadProfiles)
watch(()=>props.step,step=>{if(step==='evaluate')loadProfiles()})
const size=ref(200), overlap=ref(20), topK=ref(3), rewriting=ref(false), reranking=ref(false), answers=ref(true)
const error=ref(''), selected=ref(''), type=ref('QUERY_REWRITE_TOGGLE'), nextK=ref(5), changeNote=ref(''), confirmed=ref(false)
const csvBusy=ref(false),csvNotice=ref(''),csvError=ref(false)
async function downloadCsv(kind){
  const id=kind==='run'?run.value?.run.run_id:state.comparison?.comparison_id
  if(!id||csvBusy.value)return
  csvBusy.value=true;csvNotice.value='';csvError.value=false
  try{
    const file=await api.download(`/retrieval-${kind==='run'?'runs':'comparisons'}/${encodeURIComponent(id)}/export?format=csv`)
    const url=URL.createObjectURL(file.blob),link=document.createElement('a');link.href=url;link.download=file.filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
    csvNotice.value=`已开始下载${file.rowCount==null?'':`，共 ${file.rowCount} 道题`}。`
  }catch(e){csvError.value=true;csvNotice.value=e.message||'下载未完成，请重试。'}finally{csvBusy.value=false}
}
watch(()=>[props.step,state.baseline?.run.run_id,state.retest?.run.run_id,state.comparison?.comparison_id],()=>{csvNotice.value='';csvError.value=false})
const connectionBlocker=computed(()=>{
  const session=work.state.session
  if(!session)return '尚未配置模型。请先到 Setup 输入自己的 API Key，保存模型会话并测试连接。'
  if(session.credential_status!=='PRESENT')return '当前模型凭据不可用。请到 Setup 重新输入 API Key 并保存，再测试连接。'
  if(session.judge_connection?.available===false)return '独立 Judge 凭据已失效，请到 Setup 重新连接或恢复默认 Judge。'
  if(session.text_connection_status==='FAILED')return '模型连接测试失败。请检查 Setup 中的地址、模型名称和 API Key，然后重新测试连接。'
  if(session.text_connection_status!=='READY')return 'API Key 已保存，但尚未通过模型连接测试。测试成功后，即可开始 Baseline。'
  return ''
})
const answerPrompt=ref(''),defaultAnswerPrompt=ref('')
onMounted(async()=>{try{defaultAnswerPrompt.value=(await api.get('/retrieval-answer-prompt')).prompt;if(type.value==='ANSWER_PROMPT_CHANGE'&&!answerPrompt.value)answerPrompt.value=state.baseline?.run.retrieval_config.answer_prompt||defaultAnswerPrompt.value}catch{}})
watch(type,value=>{if(value==='ANSWER_PROMPT_CHANGE')answerPrompt.value=state.baseline?.run.retrieval_config.answer_prompt||defaultAnswerPrompt.value})
const diagnosis=ref(''),risks=ref('')
const aiOrigin=ref('')
const editingChange=ref(false),changeChoices=ref({}),improvePanel=ref(null),compareTab=ref('questions')
const changeOptions=[
 {value:'RERANK_TOGGLE',label:'资料重排（Rerank）',hint:'重新排列已找到的候选资料，再取前几条供 Agent 回答。'},
 {value:'QUERY_REWRITE_TOGGLE',label:'查询改写（Query Rewrite）',hint:'先改写问题，再用改写后的问题查找资料。'},
 {value:'TOP_K_CHANGE',label:'调整返回资料数量（Top K）',hint:'调整每题提供给 Agent 的资料条数。'},
 {value:'ANSWER_PROMPT_CHANGE',label:'修改回答提示词',hint:'调整 Agent 怎样使用资料组织回答。'},
 {value:'KNOWLEDGE_UPDATE',label:'补充或修改知识库',hint:'准备新的知识版本，再用原来的题目复测。'},
]
const changeLabel=value=>changeOptions.find(option=>option.value===value)?.label || value
const changeStatus=computed(()=>state.change?.implemented_status==='PROPOSED'?'待应用':'已应用')
watch(()=>state.baseline?.run.run_id,()=>{changeChoices.value={};editingChange.value=false})
function useSuggestion(suggestion){
 if(suggestion.run_id!==state.baseline?.run.run_id)return
 if(suggestion.change_type==='HUMAN_REVIEW'){work.state.notice='请展开最终回答，使用人工复核入口核对判定。';return}
 if(suggestion.change_type==='CHECK_LABELS'){work.go('define');return}
 if(suggestion.change_type==='NEW_BASELINE'){work.go('setup');return}
 if(state.retest){editingChange.value=false;work.go('improve');return}
 if(suggestion.change_type==='KNOWLEDGE_UPDATE'){work.go('knowledge');work.state.notice='请先补充并保存知识，再回到修改页记录这次知识更新。';return}
 selected.value=suggestion.case_id;type.value=suggestion.change_type;editingChange.value=!!state.change
 diagnosis.value='AI 待核验假设：'+suggestion.reason+'\n验证建议：'+suggestion.verification
 risks.value=suggestion.side_effects;aiOrigin.value=suggestion.draft_id;changeNote.value='';confirmed.value=false
 work.go('improve')
}
if(state.preferredChange){type.value=state.preferredChange;state.preferredChange=null}
const reviewReason=ref(''),reviewStatus=ref('PASS'), override=ref(false)
const decisionScope=ref('FULL_SCOPE')
const conclusion=ref('KEEP'),conclusionReason=ref(''),conclusionConfirmed=ref(false)
const orderedPairs=computed(()=>state.comparison?.case_pairs || [])
watch(()=>state.comparison?.comparison_id,id=>{if(id)work.action('读取实验结论',()=>practice.loadConclusions(id))},{immediate:true})
const runSide=ref('RETEST')
watch(()=>state.knowledge,k=>{if(k){name.value=k.name;documents.value=k.documents.map(d=>({document_id:d.document_id,title:d.title,text:d.text,metadata:d.metadata}))}},{immediate:true})
watch(()=>state.evalSet,e=>{if(e){cases.value=JSON.stringify(e.cases,null,2);splitReviewed.value=!!e.split_reviewed}},{immediate:true})
watch(()=>state.baseline,v=>{if(v){selected.value=state.change?.selected_case_ids[0] || v.run.case_results.find(r=>r.metrics.relevant_rank!==1)?.case_id || v.run.execution_order[0];nextK.value=v.run.retrieval_config.top_k===20?19:Math.min(20,v.run.retrieval_config.top_k+2)}},{immediate:true})
watch(()=>state.retest,()=>{runSide.value='RETEST'})
watch([selected,type],()=>{state.preview=null})
const run=computed(()=>runSide.value==='BASELINE'?state.baseline:state.retest || state.baseline), currentCase=computed(()=>state.baseline?.run.case_results.find(c=>c.case_id===selected.value))
const activeCaseId=ref(''),activePairId=ref(''),caseView=ref('answer'),caseBrowser=ref(null)
const activeCase=computed(()=>selectedQuestion(run.value?.run.case_results||[],activeCaseId.value))
const visibleCases=computed(()=>activeCase.value?[activeCase.value]:[])
const caseChoice=computed({
 get:()=>changeChoices.value[activeCase.value?.case_id] ?? (state.change?.selected_case_ids.includes(activeCase.value?.case_id)?state.change.change_type:''),
 set:value=>{if(activeCase.value)changeChoices.value[activeCase.value.case_id]=value},
})
const caseChoiceHint=computed(()=>changeOptions.find(option=>option.value===caseChoice.value)?.hint)
const choiceMatchesSaved=computed(()=>!!state.change && state.change.selected_case_ids.length===1 && state.change.selected_case_ids[0]===activeCase.value?.case_id && state.change.change_type===caseChoice.value)
const caseChoiceAction=computed(()=>choiceMatchesSaved.value?(state.change.implemented_status==='PROPOSED'?'查看并应用方案':'查看方案并复测'):state.change?'填写新方案':'填写修改方案')
const questionItems=computed(()=>(run.value?.run.case_results||[]).map(c=>({...c,status:questionStatus(run.value,c)})))
const activePair=computed(()=>selectedQuestion(orderedPairs.value,activePairId.value))
const visiblePairs=computed(()=>activePair.value?[activePair.value]:[])
const pairItems=computed(()=>orderedPairs.value.map(p=>({...p,status:labels[p.transition]})))
const answerFor=id=>run.value?.effective_answer_results.find(a=>a.case_id===id)
const expectedFor=id=>run.value?.run.controls.eval_set_snapshot.cases.find(c=>c.case_id===id)?.expected_answer
watch(()=>run.value?.run.run_id,()=>{activeCaseId.value=run.value?.run.case_results[0]?.case_id||'';caseView.value='answer'})
function inspectCase(id,view='answer'){
 activeCaseId.value=id;caseView.value=view;resultWorkbench.value?.inspectCase(id);if(view==='logs')resultWorkbench.value?.open('logs')
 nextTick(()=>{caseBrowser.value?.focus({preventScroll:true});caseBrowser.value?.scrollIntoView({block:'start',behavior:'smooth'})})
}
function showLogs(){if(activeCase.value)inspectCase(activeCase.value.case_id,'logs')}
const targetIndex=ref(null),targetIndexError=ref(false)
watch(()=>state.change?.target_index_id,async id=>{
 targetIndex.value=null;targetIndexError.value=false
 if(!id)return
 try{const value=await api.get('/knowledge-indices/'+id);if(state.change?.target_index_id===id)targetIndex.value=value}
 catch{if(state.change?.target_index_id===id)targetIndexError.value=true}
},{immediate:true})
const retestIndex=computed(()=>state.change?.change_type==='KNOWLEDGE_UPDATE'
 ?(state.index?.index_id===state.change.target_index_id?state.index:targetIndex.value)
 :state.baseline?.run.controls.index_snapshot)
const savedChangeCases=computed(()=>(state.baseline?.run.case_results || []).filter(c=>state.change?.selected_case_ids.includes(c.case_id)))
const savedChangeSummary=computed(()=>{
 const change=state.change
 if(!change)return ''
 const before=change.before_config,after=change.after_config,onOff=value=>value?'开启':'关闭'
 if(change.change_type==='TOP_K_CHANGE')return `返回资料数量：${before.top_k} → ${after.top_k}`
 if(change.change_type==='QUERY_REWRITE_TOGGLE')return `查询改写：${onOff(before.query_rewrite)} → ${onOff(after.query_rewrite)}`
 if(change.change_type==='RERANK_TOGGLE')return `资料重排：${onOff(before.rerank)} → ${onOff(after.rerank)}`
 if(change.change_type==='ANSWER_PROMPT_CHANGE')return '回答提示：使用本次记录的新版本'
 const oldVersion=state.baseline?.run.controls.knowledge_snapshot.version,newVersion=retestIndex.value?.knowledge_version
 return oldVersion!=null&&newVersion!=null?`知识版本：v${oldVersion} → v${newVersion}`:'知识库：使用本次选择的新版本'
})
const metrics=retrievalMetrics
const format=(n)=>n==null?'unavailable':n.toFixed(3)
const rank=(n)=>n==null?'未找到':n
const labels={RETRIEVAL_IMPROVED:'检索改善',RETRIEVAL_REGRESSED:'检索退化',RETRIEVAL_UNCHANGED:'检索未变化',NOT_COMPARABLE:'无法比较'}
const parse=async(fn)=>{error.value='';try{await fn()}catch(e){error.value=e.message || '请检查输入'}}
function addDocument(){documents.value.push({document_id:'doc_'+crypto.randomUUID().replaceAll('-',''),title:'',text:'',metadata:{}})}
function demo(){documents.value=structuredClone(demoDocuments);cases.value=JSON.stringify(demoCases,null,2);name.value='Demo · 电商知识检索';error.value=''}
function newBaseline(){const knowledge=state.knowledge;rag.reset();state.knowledge=knowledge;rag.persist();work.go('define')}
async function files(event){await parse(async()=>{const added=[];for(const f of event.target.files){if(!/\.(txt|md)$/i.test(f.name)||f.size>200000)throw new Error('仅支持不超过 200 KB 的 .txt / .md 文件。');added.push({document_id:'doc_'+crypto.randomUUID().replaceAll('-',''),title:f.name,text:await f.text(),metadata:{filename:f.name}})}if(documents.value.length===1 && !documents.value[0].text.trim() && !documents.value[0].title.trim())documents.value=added;else documents.value.push(...added)});event.target.value=''}
async function saveKnowledge(){await parse(()=>rag.saveKnowledge({name:name.value,documents:documents.value,
  ...(state.knowledge?{knowledge_dataset_id:state.knowledge.knowledge_dataset_id}:{})}))}
async function saveCases(){try{const rows=records(cases.value);await rag.saveEvalset({name:name.value,cases:rows,split_reviewed:splitReviewed.value})}catch(e){analytics.blocked('tests.save','invalid_input');error.value=e.message}}
const changeAnalysisOptions=computed(()=>({view:state.baseline,caseId:selected.value,type:type.value,nextK:nextK.value,answerPrompt:answerPrompt.value,defaultAnswerPrompt:defaultAnswerPrompt.value,index:state.index,knowledge:state.knowledge}))
async function propose(){
  if(work.state.busy)return
  if(state.retest){error.value='本轮已复测，请先查看前后比较。';return}
  const plan=proposedChange(changeAnalysisOptions.value)
  if(!plan.valid||!confirmed.value){error.value=plan.problem||'请核对本次方案并勾选确认。';return}
  const previousChange=state.change?.change_id
  const record=changePlanRecord(changeAnalysisOptions.value,changeNote.value,aiOrigin.value?{id:aiOrigin.value,text:diagnosis.value+'\n'+risks.value}:null)
  await rag.propose({change_type:type.value,after_config:plan.afterConfig,reason:record,selected_case_ids:[selected.value],user_confirmed:confirmed.value,...(type.value==='KNOWLEDGE_UPDATE'?{target_index_id:state.index.index_id}:{})})
  if(state.change?.change_id && state.change.change_id!==previousChange)editingChange.value=false
}
function openChangePlan(){
 editingChange.value=false;work.go('improve')
 nextTick(()=>{improvePanel.value?.focus({preventScroll:true});improvePanel.value?.scrollIntoView({block:'start',behavior:'smooth'})})
}
function chooseCaseChange(){
 if(work.state.busy || !activeCase.value || !caseChoice.value)return
 if(state.retest || choiceMatchesSaved.value){openChangePlan();return}
 if(selected.value!==activeCase.value.case_id || type.value!==caseChoice.value){
  diagnosis.value='';changeNote.value='';risks.value='';aiOrigin.value='';confirmed.value=false
 }
 selected.value=activeCase.value.case_id;type.value=caseChoice.value;editingChange.value=!!state.change;state.preview=null
 work.go('improve')
 nextTick(()=>{improvePanel.value?.focus({preventScroll:true});improvePanel.value?.scrollIntoView({block:'start',behavior:'smooth'})})
}
function returnToCase(){
 activeCaseId.value=selected.value;caseView.value='answer';work.go('evaluate')
 nextTick(()=>{caseBrowser.value?.focus({preventScroll:true});caseBrowser.value?.scrollIntoView({block:'start',behavior:'smooth'})})
}
const selectedAnswer=ref(null)
async function saveReview(){if(!selectedAnswer.value || !reviewReason.value.trim()){analytics.blocked('review.save','missing_input');return}
  if(selectedAnswer.value.result.hard_rule_violations.length && reviewStatus.value==='PASS'&&!override.value){analytics.blocked('review.save','unconfirmed');return}
  await rag.review(selectedAnswer.value.runId,{case_id:selectedAnswer.value.result.case_id,human_final_status:reviewStatus.value,human_reason:reviewReason.value})
  selectedAnswer.value=null;reviewReason.value='';override.value=false}
</script>
<template>
  <div class="page-heading" v-if="!(step==='evaluate'&&run)"><div><p class="eyebrow">我的实验</p><h1>{{step==='define'?'准备几道测试题':step==='evaluate'?'看看这个客服 Agent 答得怎么样':step==='improve'?'选一个问题，试着改改':'改完之后，有没有变好？'}}</h1><p>{{step==='improve'?'先对照原文确认问题，再选这次要改什么。':step==='compare'?'别只看总分，也看看有没有题答得更差了。':'系统会保存这次用的资料、题目和模型设置，方便之后比较。'}}</p></div><div v-if="step==='evaluate'&&run||step==='compare'&&state.comparison" class="csv-download"><button v-if="step==='evaluate'" type="button" class="secondary" @click="showLogs">查看运行日志</button><button v-if="step==='evaluate'" class="secondary" :disabled="csvBusy||!!work.state.busy||run.run.status==='RUNNING'" @click="downloadCsv('run')">{{csvBusy?'正在导出…':'导出本次结果 CSV'}}</button><button v-else class="secondary" :disabled="csvBusy||!!work.state.busy" @click="downloadCsv('comparison')">{{csvBusy?'正在导出…':'导出前后对比 CSV'}}</button><small>包含本次全部题目，不受页面筛选影响</small><small v-if="step==='evaluate'&&run.run.status==='RUNNING'" role="status">运行结束后可以导出</small></div><span v-else class="pill">客服知识问答</span></div>
  <p v-if="csvNotice" :class="['note',csvError?'danger':'positive']" :role="csvError?'alert':'status'">{{csvNotice}}</p>
  <p v-if="error" role="alert" class="note danger">{{error}}</p>
  <template v-if="step==='define'">
    <p class="note">先保存知识，再建立索引，最后标注每题应找到哪份知识。修改知识会生成新版本，需要重新建立 Baseline。</p>
    <section class="panel"><div class="section-heading"><h2>1. Knowledge · 知识</h2><button v-track="{action:'knowledge.demo',placement:'RetrievalPage.control_01'}" class="secondary" :disabled="!!work.state.busy || !!state.baseline" @click="demo">载入 Demo 知识与 8 道题</button></div>
      <p class="muted">Demo 政策仅用于流程演示，请用自己的业务知识替换。</p>
      <fieldset :disabled="!!work.state.busy || !!state.baseline">
        <label>检索实验名称<input v-track="{action:'retrievalpage.edit_start',placement:'RetrievalPage.editor',kind:'edit'}" v-model="name" required /></label>
        <label>上传知识文档（.txt / .md）<input v-track="{action:'knowledge.import',placement:'RetrievalPage.control_02'}" type="file" accept=".txt,.md" multiple @change="files" /></label>
        <details v-for="(doc,i) in documents" :key="i" class="builder-card" :open="documents.length===1"><summary v-track="{action:'knowledge.document',placement:'RetrievalPage.control_03'}">{{doc.title || `知识文档 ${i+1}`}} · {{doc.document_id}}</summary>
          <div class="form-row"><label>文档 ID<input v-track="{action:'retrievalpage.edit_start',placement:'RetrievalPage.editor',kind:'edit'}" v-model="doc.document_id" required pattern="[A-Za-z0-9_-]+" /></label><label>知识标题<input v-track="{action:'retrievalpage.edit_start',placement:'RetrievalPage.editor',kind:'edit'}" v-model="doc.title" /></label></div>
          <label>知识正文<textarea v-track="{action:'retrievalpage.edit_start',placement:'RetrievalPage.editor',kind:'edit'}" v-model="doc.text" rows="5" required /></label><button v-track="{action:'knowledge.remove_document',placement:'RetrievalPage.control_04'}" class="text-button" @click="documents.splice(i,1)">移除文档</button>
        </details>
        <div class="button-row"><button v-track="{action:'knowledge.add_document',placement:'RetrievalPage.control_05'}" class="secondary" @click="addDocument">＋ 添加知识</button><button v-track="{action:'knowledge.save',placement:'RetrievalPage.control_06',core:true,reason:('precondition')}" class="primary" :disabled="!documents.length || documents.some(d=>!d.text.trim() || !d.document_id.trim())" @click="saveKnowledge">{{state.knowledge?'保存为新知识版本':'保存知识版本'}}</button></div>
      </fieldset>
      <div v-if="state.knowledge" class="note positive">已保存 {{state.knowledge.documents.length}} 份文档 · Version {{state.knowledge.version}}。历史版本保留。</div>
    </section>
    <section class="panel"><h2>2. 建立固定索引</h2><label>检索方式<select v-track="{action:'knowledge.retrieval',placement:'RetrievalPage.control_07'}" v-model="embeddingModel" :disabled="!!work.state.busy || !!state.baseline"><option :value="semanticModel">语义检索 · 原有 MiniLM 模型（默认）</option><option :value="lexicalModel">词汇检索 · 保留对照</option></select></label><p class="muted">默认使用原有 MiniLM 本地语义模型（384 维），无需额外 API Key。首次使用需下载；中文检索效果以实际测试为准。</p>
      <details class="advanced"><summary v-track="{action:'knowledge.chunk_settings',placement:'RetrievalPage.control_08'}">切分设置</summary><div class="form-row"><label>Chunk 大小<input v-track="{action:'retrievalpage.edit_start',placement:'RetrievalPage.editor',kind:'edit'}" v-model.number="size" type="number" min="50" max="2000" :disabled="!!state.baseline" /></label><label>Chunk 重叠<input v-track="{action:'retrievalpage.edit_start',placement:'RetrievalPage.editor',kind:'edit'}" v-model.number="overlap" type="number" min="0" :disabled="!!state.baseline" /></label></div></details>
      <button v-track="{action:'knowledge.index',placement:'RetrievalPage.control_09',core:true,reason:('precondition')}" class="primary" :disabled="!state.knowledge || !!work.state.busy || !!state.baseline" @click="rag.buildIndex({chunk_size:size,chunk_overlap:overlap},embeddingModel)">建立冻结索引</button>
      <p v-if="state.index" class="note positive">{{embeddingLabel(state.index)}} · 索引 READY · {{state.index.chunks.length}} 个 Chunk · 知识 Version {{state.index.knowledge_version}}</p><EvidenceDetails data-analytics-location="RetrievalPage.EvidenceDetails.1" v-if="state.index" :data="state.index" title="Chunk / Embedding / Index 证据" />
    </section>
    <section class="panel"><h2>3. Retrieval EvalSet · 测试题</h2><p class="muted">每道题填写 query 和 relevant_document_ids 或 relevant_chunk_ids。标签由你确认，不由模型猜测。文档标签会对重复 Chunk 去重计分。</p><p class="note">设置保留题时，每题填写 group_id（同题改写使用同一组），并设置 partition 为 DEBUG 或 HOLDOUT。普通初测和复测只运行 DEBUG 题；HOLDOUT 留到配置锁定后的独立验证。</p><label class="check"><input v-model="splitReviewed" type="checkbox" />我已核对分组，调试题和保留题没有同源改写或模板泄漏</label>
      <label>检索测试题 JSON<textarea v-track="{action:'retrievalpage.edit_start',placement:'RetrievalPage.editor',kind:'edit'}" v-model="cases" rows="12" spellcheck="false" :disabled="!!state.baseline || !!work.state.busy" placeholder='[{"case_id":"01","query":"退款多久到账？","relevant_document_ids":["refund"]}]' /></label>
      <button v-track="{action:'tests.save',placement:'RetrievalPage.control_10',core:true,reason:('precondition')}" class="primary" :disabled="!state.index || !cases.trim() || !!state.baseline || !!work.state.busy" @click="saveCases">保存检索测试，准备 Baseline →</button>
    </section>
    <p v-if="state.baseline" class="note warning">本实验知识和题目已冻结。要更新知识，请建立新 Baseline。</p><button v-track="{action:'run.new_baseline',placement:'RetrievalPage.control_11'}" v-if="state.baseline" class="secondary" :disabled="!!work.state.busy" @click="newBaseline">基于这份知识建立新 Baseline</button>
  </template>
  <template v-else-if="step==='evaluate'">
    <p v-if="!state.evalSet" class="empty">还没有测试题。先到“测试题”准备几道题，再来运行。</p>
    <section v-else-if="!state.baseline" class="panel">
      <h2>开始第一次评测</h2>
      <label>评测内容<select v-model="answers"><option :value="true">评测 Agent 的回答</option><option :value="false">只检查资料查找</option></select></label>
      <p class="muted">{{answers?'让 Agent 根据资料回答，再由评分模型检查回答。':'对照每题标注，检查有没有找到正确资料。'}}</p>
      <div v-if="answers&&policyGaps.length" class="note warning" role="status"><strong>{{policyGaps.length}} 道题需要先核对参考资料</strong><p>确认原文足够判断每道题，评测时才能给出通过或不通过。</p><button type="button" class="secondary" @click="work.go('define')">去核对题目 →</button></div>
      <details class="evaluation-settings"><summary>调整评测设置</summary>
       <label>每题查找几条资料（Top K）<input v-track="{action:'retrievalpage.edit_start',placement:'RetrievalPage.editor',kind:'edit'}" v-model.number="topK" type="number" min="1" max="20" /></label>
       <div class="button-row"><label class="check"><input v-track="{action:'run.rewrite',placement:'RetrievalPage.control_12'}" v-model="rewriting" type="checkbox" />先改写问题，帮助查找</label><label class="check"><input v-track="{action:'run.rerank',placement:'RetrievalPage.control_13'}" v-model="reranking" type="checkbox" />重新排列找到的资料</label></div>
       <RerankHelp v-if="reranking" :top-k="topK" />
       <section v-if="answers" class="scoring-choice"><label>本次回答评分标准<select v-model="scoringProfile"><option value="">旧版四维评分 · 0～1</option><option v-for="p in profiles" :key="p.profile_id" :value="p.profile_id">{{p.name}}</option></select></label><p class="muted">评分模型会引用原文说明理由。当前初始规则尚待人工校准；前后比较将使用同一套规则。</p></section>
      </details>
      <RunBriefing :session="work.state.session" :index="state.index" :cases="state.evalSet.cases.filter(c=>c.partition!=='HOLDOUT')" :config="{top_k:topK,query_rewrite:rewriting,rerank:reranking}" :verify-answers="answers" />
      <button v-track="{action:'run.baseline',placement:'RetrievalPage.control_15',core:true,reason:(work.state.busy ? 'busy' : !work.state.session ? 'connection' : work.state.session.credential_status !== 'PRESENT' ? 'credentials' : 'connection')}" class="primary" :disabled="!!work.state.busy || !!connectionBlocker" @click="rag.run('BASELINE',{top_k:topK,query_rewrite:rewriting,rerank:reranking},answers,scoringProfile)">开始评测</button>
      <div v-if="connectionBlocker" class="note warning" role="status"><p>{{connectionBlocker}}</p><div class="button-row"><button v-if="work.state.session?.credential_status==='PRESENT'" class="secondary" :disabled="!!work.state.busy" @click="work.testConnection">测试模型连接</button><button class="text-button" :disabled="!!work.state.busy" @click="work.go('setup')">去连接模型 →</button></div></div>
    </section>
    <template v-if="run">
      <div class="visual-run-toolbar"><span>{{run.run.run_type==='BASELINE'?'首次评测':'修改后复测'}} · {{({COMPLETE:'已完成',RUNNING:'运行中',PARTIAL:'部分完成',FAILED:'运行失败'})[run.run.status]||run.run.status}}</span><div class="button-row"><select v-if="state.retest" aria-label="查看哪次评测" v-model="runSide"><option value="BASELINE">修改前</option><option value="RETEST">修改后</option></select><button v-if="state.retest" type="button" class="text-button" :disabled="!!work.state.busy" @click="rag.compare">查看前后比较 →</button><button type="button" class="text-button" :disabled="csvBusy||!!work.state.busy||run.run.status==='RUNNING'" @click="downloadCsv('run')"><WorkspaceIcon name="download" :size="16" />{{csvBusy?'正在导出…':'导出结果'}}</button></div></div>
      <p v-if="run.run.status==='RUNNING'" class="note" role="status">已完成 {{run.run.case_results.filter(c=>c.case_latency_ms!=null).length}}/{{run.run.execution_order.length}} 题。后台继续运行，结果会自动更新。</p>
      <p v-if="run.run.controls.evaluation_scope?.holdout_count" class="visual-holdout-note">本次只评调试题；{{run.run.controls.evaluation_scope.holdout_count}} 道保留题留待独立验证。</p>
      <VisualResults ref="resultWorkbench" :view="run" v-model="activeCaseId" :can-modify="run.run.run_type==='BASELINE'&&['COMPLETE','PARTIAL'].includes(run.run.status)">
       <template #answer="{row:c}"><h3>{{c.query}}</h3><h4>Agent 的完整回答</h4><p class="agent-response">{{answerFor(c.case_id)?.turn_evidence?.[0]?.response || '本题没有保存回答，请查看运行日志。'}}</p><template v-if="expectedFor(c.case_id)"><h4>预期回答</h4><p class="agent-response">{{expectedFor(c.case_id)}}</p></template></template>
       <template #source="{row:c}"><h3>当时查到的资料 · {{c.results?.length||0}} 条</h3><p class="muted">目标资料：{{[...(c.relevant_document_ids||[]),...(c.relevant_chunk_ids||[])].join('、')||'未标注'}} · {{c.metrics?.returned_relevant_rank?'已找到':'未找到'}}</p><ol class="rag-results"><li v-for="r in c.results" :key="r.chunk_id"><strong>{{r.document_id}}</strong><p>{{r.text}}</p></li></ol><TrustedResults :view="run" :case-id="c.case_id" /></template>
       <template #reason="{row:c}"><h3>完整判定理由</h3><p>{{answerExplanation(answerFor(c.case_id))}}</p><ScoringEvidence v-if="answerFor(c.case_id)" :result="answerFor(c.case_id)" /><TrustedResults :view="run" :case-id="c.case_id" /><ScoreRecovery :key="run.run.run_id+c.case_id" :view="run" :case-id="c.case_id" /></template>
       <template #logs="{row:c}"><RunDiagnostics :retrieval="c" :answer="answerFor(c.case_id)" :verify-answers="run.run.verify_answers" expanded title="运行日志" /><ScoreRecovery :key="run.run.run_id+c.case_id" :view="run" :case-id="c.case_id" /><EvidenceDetails :data="c" title="本题原始记录" copyable /><button type="button" class="secondary" @click="copyCaseLog(c.case_id)">复制本题日志</button></template>
       <template #modify="{row:c}"><p class="muted">选一个改法，再记录依据。复测会检查原来的整批题。</p><template v-if="!state.retest"><p v-if="state.change?.selected_case_ids.includes(c.case_id)" class="note">已记录：{{changeLabel(state.change.change_type)}} · {{changeStatus}}</p><div class="visual-change-options" aria-label="选择本题修改方式"><button v-for="(option,i) in changeOptions" :key="option.value" type="button" :aria-pressed="caseChoice===option.value" :disabled="!!work.state.busy" @click="caseChoice=option.value"><WorkspaceIcon :name="['adjust','search','list','chat','document'][i]" :size="23" /><span><strong>{{option.label.split('（')[0]}}</strong><small>{{option.hint}}</small></span><WorkspaceIcon v-if="caseChoice===option.value" name="check" :size="18" /></button></div><button type="button" class="primary" :disabled="!!work.state.busy||!caseChoice" @click="chooseCaseChange">{{caseChoiceAction}} →</button></template><template v-else><p class="note">本轮复测使用：{{changeLabel(state.change?.change_type)}}</p><button type="button" class="primary" @click="openChangePlan">查看本轮修改</button></template></template>
       <template #suggest="{row:c}"><TraceAssistant embedded :run-type="run.run.run_type" :run-id="run.run.run_id" :case-id="c.case_id" :can-suggest="run.run.run_type==='BASELINE'" @suggestion="useSuggestion" /></template>
       <template #review="{row:c}"><template v-for="a in run.effective_answer_results.filter(a=>a.case_id===c.case_id)" :key="a.case_id"><p>模型判定：{{({PASS:'通过',FAIL:'不通过',INVALID:'执行失败'})[a.original_status]||a.original_status}} · 人工复核：{{a.human_evaluation_state||a.human_final_status||'未复核'}}</p><div class="button-row"><button class="secondary" :disabled="a.execution_status!=='SUCCESS'||a.judge_status==='FAILED'||!!a.evaluation_error" @click="selectedAnswer={result:a,runId:run.run.run_id}">人工复核回答</button><button class="secondary" :disabled="!a.turn_evidence[0]?.response" @click="calibration.queue(run.run.run_id,c.case_id)">加入校准样本</button></div></template>
        <section v-if="selectedAnswer?.result.case_id===c.case_id" class="panel"><h3>回答人工复核</h3><label>人工最终判定<select v-model="reviewStatus"><option value="PASS">通过</option><option value="FAIL">不通过</option><option value="EVIDENCE_INSUFFICIENT">证据不足，无法评判</option><option value="NOT_APPLICABLE">不属于本次评测范围</option></select></label><label>回答复核理由<textarea v-model="reviewReason" rows="3" required /></label><label v-if="selectedAnswer.result.hard_rule_violations.length&&reviewStatus==='PASS'" class="check"><input v-model="override" type="checkbox" />确认覆盖规则检查的判定，保留原违规证据</label><button class="primary" :disabled="!!work.state.busy||!reviewReason.trim()||(selectedAnswer.result.hard_rule_violations.length&&reviewStatus==='PASS'&&!override)" @click="saveReview">保存回答复核</button></section>
        <RetrievalIssuePanel :run-id="run.run.run_id" :case-id="c.case_id" /></template>
       <template #checks><TrustedResults :view="run" @inspect-case="inspectCase" /></template>
       <template #metrics><p class="muted">本次运行：{{embeddingLabel(run.run.controls.index_snapshot)}}</p><div class="rag-metric-grid"><section v-for="metric in metrics" :key="metric.id" class="metric-card"><div class="metric-heading"><small>{{metric.label}}</small><MetricHelp :metric="metric" /></div><strong>{{format(run.run.metrics[metric.id])}}</strong><small>{{run.run.metrics.denominators?.[metric.id]||0}} 道有效标注题</small></section></div><h3>实际调用与用量</h3><p>调用 {{run.run.sample_flow?.cost?.actual_requests??'未记录'}} 次 · 已知用量 {{run.run.sample_flow?.cost?.known_total_tokens??'未记录'}} 个词元</p><p class="muted">未知用量的请求 {{run.run.sample_flow?.cost?.unknown_usage_requests??'未记录'}} 次；费用以服务账单为准。</p><ExperimentHealth :view="run" /></template>
       <template #records><p class="muted">导出包含本次全部题目，不受页面筛选影响。</p><button type="button" class="secondary" :disabled="csvBusy||!!work.state.busy||run.run.status==='RUNNING'" @click="downloadCsv('run')">导出本次结果 CSV</button><EvaluationLogExport ref="logExport" :key="run.run.run_id" :view="run" /><EvidenceDetails :data="run" title="本次运行的完整记录" /></template>
      </VisualResults>
    </template>
  </template>
  <template v-else-if="step==='improve'">
    <p v-if="!state.baseline" class="empty">先运行 Retrieval Baseline，再从结果选择问题。</p>
    <section v-else ref="improvePanel" class="panel" tabindex="-1"><template v-if="!state.change || editingChange">
      <p v-if="editingChange" class="note">保存后使用新方案，原记录保留。<button type="button" class="text-button" @click="editingChange=false">取消修改</button></p>
      <p v-if="aiOrigin" class="note">已有 AI 草稿供参考，原因和效果尚未验证。保存方案不代表已确认根因。</p>
      <ChangePlanEditor :view="state.baseline" v-model:case-id="selected" v-model:type="type" v-model:next-k="nextK" v-model:answer-prompt="answerPrompt" v-model:confirmed="confirmed" v-model:note="changeNote" :default-answer-prompt="defaultAnswerPrompt" :index="state.index" :knowledge="state.knowledge" :options="changeOptions" :busy="!!work.state.busy" :locked="!!state.retest" :preview="state.preview" :can-preview="work.state.session?.credential_status==='PRESENT'" @submit="propose" @return="returnToCase" @knowledge="work.go('knowledge')" @preview="rag.preview(currentCase.query)" />
     </template>
      <template v-else>
        <div class="section-heading"><h2>本次修改</h2><span class="pill">{{state.change.implemented_status==='PROPOSED'?'待应用':'已应用'}}</span></div>
        <p v-for="c in savedChangeCases" :key="c.case_id" class="change-question">{{c.query}}</p>
        <p class="change-summary"><strong>{{savedChangeSummary}}</strong></p>
        <p v-if="state.change.change_type!=='TOP_K_CHANGE'" class="muted">返回资料数量：{{state.change.after_config.top_k}}</p>
        <details class="case-detail"><summary>查看我的判断记录</summary><p class="saved-change-reason">{{state.change.reason}}</p></details>
        <p v-if="state.change.implemented_status==='APPLIED' && !state.retest && !retestIndex" class="note warning">{{targetIndexError?'复测索引暂时无法读取，请同步状态后检查目标知识版本。':'正在读取已确认的复测索引…'}}</p>
        <RunBriefing v-if="state.change.implemented_status==='APPLIED' && !state.retest && retestIndex" :session="{configuration:state.baseline.run.provider_configuration_snapshot}" :index="retestIndex" :cases="state.baseline.run.controls.eval_set_snapshot.cases.filter(c=>c.partition!=='HOLDOUT')" :config="state.change.after_config" :verify-answers="state.baseline.run.verify_answers" />
        <button v-track="{action:'change.apply',placement:'RetrievalPage.control_35',core:true,reason:('busy')}" v-if="state.change.implemented_status==='PROPOSED'" class="primary" :disabled="!!work.state.busy" @click="rag.apply">应用修改</button>
        <button v-track="{action:'run.retest',placement:'RetrievalPage.control_36',core:true,reason:(work.state.busy ? 'busy' : state.retest ? 'already_complete' : 'credentials')}" v-else class="primary" :disabled="!!work.state.busy || !!state.retest || work.state.session?.credential_status!=='PRESENT'" @click="rag.run('RETEST',null,state.baseline.run.verify_answers)">开始复测</button>
        <EvidenceDetails data-analytics-location="RetrievalPage.EvidenceDetails.7" :data="state.change" title="完整修改记录" />
      </template>
    </section>
  </template>
  <template v-else-if="step==='compare'">
    <section v-if="!state.comparison" class="panel visual-comparison-empty"><div class="visual-improve-stages"><span><WorkspaceIcon name="chart" :size="27" />首次评测</span><WorkspaceIcon name="arrow" /><span><WorkspaceIcon name="adjust" :size="27" />一次修改</span><WorkspaceIcon name="arrow" /><span><WorkspaceIcon name="compare" :size="27" />同题复测</span></div><h2>有复测，再看变化</h2><p>比较哪些题变好、哪些题变差。</p><button v-if="!state.baseline" type="button" class="primary" @click="work.go('evaluate')">先完成首次评测 →</button><button v-else-if="!state.retest" type="button" class="primary" @click="work.go('improve')">去修改并复测 →</button><button v-else type="button" class="primary" :disabled="!!work.state.busy" @click="rag.compare">生成前后比较 →</button></section>
    <template v-else><p v-if="!state.comparison.comparable||!state.comparison.trust_summary?.overall_improvement_allowed" class="note warning">比较范围或条件受限，暂不能判断整体改善。<button type="button" class="text-button" @click="compareTab='overview'">查看范围与依据 →</button></p><nav class="visual-report-tabs" aria-label="前后比较内容"><button v-for="t in [{id:'questions',label:'逐题变化',icon:'compare'},{id:'overview',label:'本次概览',icon:'chart'},{id:'decision',label:'记录结论',icon:'check'},{id:'records',label:'评分与原始记录',icon:'database'}]" :key="t.id" type="button" :aria-pressed="compareTab===t.id" @click="compareTab=t.id"><WorkspaceIcon :name="t.icon" :size="17" />{{t.label}}</button></nav><section v-if="compareTab==='overview'" class="panel"><h2>{{state.comparison.comparable?'控制条件可比较':'控制条件不可比较'}} · {{state.comparison.comparison_completeness}}</h2><p class="note warning">本次为单次对照，可重复运行检查变化是否稳定。</p><p v-if="state.comparison.comparison_completeness==='PARTIAL'">本次只比较已完成且有效的题目。</p><p v-if="state.comparison.comparability_reasons.length">{{state.comparison.comparability_reasons.join(' · ')}}</p></section>
      <TrustedResults v-if="compareTab==='overview'" :comparison="state.comparison" /><EvaluationLogExport v-if="compareTab==='records'" ref="logExport" :key="state.comparison.comparison_id" :comparison="state.comparison" :baseline-view="state.baseline" :retest-view="state.retest" /><div v-if="compareTab==='overview'" class="rag-metric-grid"><section v-for="metric in metrics" :key="metric.id" class="metric-card"><div class="metric-heading"><small>{{metric.label}} · 有效匹配题</small><MetricHelp data-analytics-location="RetrievalPage.MetricHelp.8" :metric="metric" /></div><strong>{{format(state.comparison.paired_metrics.baseline[metric.id])}} → {{format(state.comparison.paired_metrics.retest[metric.id])}}</strong><small>分母 {{state.comparison.paired_metrics.baseline.denominators[metric.id]}}</small></section></div>
      <ScoreReportComparison v-if="compareTab==='records'" :key="state.comparison.comparison_id" :comparison="state.comparison" />
      <section v-if="compareTab==='questions'" class="panel"><h2>逐题比较</h2><QuestionNavigator :items="pairItems" :model-value="activePair?.case_id" @update:model-value="activePairId=$event" label="比较题目导航" /><div class="case-view-tabs" role="group" aria-label="比较视图"><button type="button" :aria-pressed="caseView==='answer'" @click="caseView='answer'">前后回答</button><button type="button" :aria-pressed="caseView==='logs'" @click="caseView='logs'">运行日志</button></div></section>
      <template v-if="compareTab==='questions'"><section v-for="p in visiblePairs" :key="p.case_id" class="panel rag-case"><div class="section-heading"><h3>{{p.query}}</h3><strong>{{labels[p.transition]}}</strong></div><p>正确知识 Rank：{{rank(p.baseline?.metrics.relevant_rank)}} → {{rank(p.retest?.metrics.relevant_rank)}}</p><p>Top K：{{p.baseline?.top_k || '缺失'}} → {{p.retest?.top_k || '缺失'}}</p><p v-if="p.reason">{{p.reason}}</p>
        <div v-if="caseView==='logs'" class="two-column"><RunDiagnostics expanded :retrieval="p.baseline" :answer="p.baseline_answer" :verify-answers="state.baseline?.run.verify_answers" title="初测运行诊断" /><RunDiagnostics expanded :retrieval="p.retest" :answer="p.retest_answer" :verify-answers="state.retest?.run.verify_answers" title="复测运行诊断" /></div>
        <details v-if="caseView==='answer'" class="case-detail"><summary>两次查到的资料</summary><div class="two-column"><div><h4>修改前的资料</h4><ol class="rag-results"><li v-for="r in p.baseline?.results" :key="r.chunk_id">{{r.document_id}}<p>{{r.text}}</p></li></ol></div><div><h4>修改后的资料</h4><ol class="rag-results"><li v-for="r in p.retest?.results" :key="r.chunk_id">{{r.document_id}}<p>{{r.text}}</p></li></ol></div></div></details>
        <details open v-if="caseView==='answer' && (p.baseline_answer || p.retest_answer)" class="evidence"><summary v-track="{action:'comparison.answer_change',placement:'RetrievalPage.control_37'}">回答变化 · {{p.answer_transition}}</summary><div class="two-column"><div><h4>修改前 · {{p.baseline_answer?.final_status}}</h4><p>{{p.baseline_answer?.turn_evidence[0]?.response}}</p><p>{{p.baseline_answer?.original_reason}}</p></div><div><h4>修改后 · {{p.retest_answer?.final_status}}</h4><p>{{p.retest_answer?.turn_evidence[0]?.response}}</p><p>{{p.retest_answer?.original_reason}}</p></div></div><p class="note">对照两次回答和判定理由，查看哪些地方变好了，哪些还需要调整。</p></details>
      <RetrievalIssuePanel :run-id="state.comparison.baseline_run_id" :case-id="p.case_id" :comparison-id="state.comparison.comparison_id" /><button type="button" class="secondary" @click="copyCaseLog(p.case_id)">复制本题对比日志</button></section></template><section v-if="compareTab==='decision'" class="panel"><h2>下一步，怎样处理这次修改？</h2><label>我的决定<select v-track="{action:'conclusion.choice',placement:'RetrievalPage.control_38'}" v-model="conclusion" aria-label="我的决定"><option value="KEEP">保留修改</option><option value="REVISE">继续调整</option><option value="REVERT">采用初测版本</option></select></label><label>结论范围<select v-model="decisionScope"><option value="FULL_SCOPE">本轮全部应评范围</option><option value="LIMITED_OBSERVATION">仅限已观察的可比子集，不主张整体提升</option></select></label><p v-if="state.comparison.trust_summary&&!state.comparison.trust_summary.adoption_allowed" class="note warning">存在范围或覆盖限制。保留修改需明确限定为观察结论；也可以继续调整或采用初测版本。</p><label>结果解释与取舍<textarea v-track="{action:'retrievalpage.edit_start',placement:'RetrievalPage.editor',kind:'edit'}" v-model="conclusionReason" rows="3" placeholder="解释改善、退化和证据局限，说明为什么作出这个决定。" /></label><label class="check"><input v-track="{action:'conclusion.confirm',placement:'RetrievalPage.control_39'}" type="checkbox" v-model="conclusionConfirmed" />我确认这是本人判断，当前结果的局限仍然保留</label><button v-track="{action:'conclusion.save',placement:'RetrievalPage.control_40',core:true,reason:(work.state.busy ? 'busy' : !conclusionConfirmed ? 'unconfirmed' : 'missing_input')}" class="primary" :disabled="!conclusionReason.trim() || !conclusionConfirmed || !!work.state.busy" @click="practice.conclude(state.comparison.comparison_id,{decision:conclusion,reason:conclusionReason,user_confirmed:true,decision_scope:decisionScope})">保存实验结论</button><p v-for="c in practice.state.conclusions" :key="c.conclusion_id">{{c.decision}}：{{c.reason}}（{{c.decision_scope==='LIMITED_OBSERVATION'?'仅限已观察子集':'记录范围内的本人决定'}}）</p><div class="button-row"><button v-track="{action:'comparison.chat',placement:'RetrievalPage.control_41'}" class="secondary" @click="practice.newChat();practice.state.chatSource=conclusion==='REVERT'?'baseline':'retest';work.go('chat')">回到聊天验证体验 →</button><button v-track="{action:'comparison.career',placement:'RetrievalPage.control_42'}" class="secondary" @click="work.go('career')">整理项目与求职材料 →</button></div></section><AgentHoldout v-if="compareTab==='decision'" :comparison="state.comparison" /><EvidenceDetails v-if="compareTab==='records'" data-analytics-location="RetrievalPage.EvidenceDetails.10" :data="state.comparison" title="完整检索比较证据" />
    </template>
  </template>
</template>
<style scoped>
.case-change-choice{padding:20px;margin:0 0 24px;background:var(--color-canvas,#f5f5f2);border:1px solid var(--color-line,#ddd);border-radius:8px}.case-change-choice h4{margin:0 0 14px;font-size:16px}.recorded-choice{font-size:13px;line-height:1.7;margin:0 0 12px}.case-change-controls{display:flex;align-items:flex-end;gap:14px;flex-wrap:wrap}.case-change-controls label{flex:1;min-width:200px;max-width:390px;margin:0}.case-change-controls button{flex-shrink:0}.case-change-choice>.muted{font-size:12px;line-height:1.7;margin:12px 0 0}@media(max-width:600px){.case-change-choice{padding:16px}.case-change-controls{display:grid;gap:12px}.case-change-controls label{min-width:0;max-width:none}.case-change-controls button{width:100%}}
.change-question{font-size:14px;color:var(--muted);line-height:1.7}.change-summary{font-size:18px;margin:22px 0 10px}.saved-change-reason{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8}
.question-browser{scroll-margin-top:24px}.question-browser:focus{outline:none}.case-view-tabs{display:flex;gap:4px;border-bottom:1px solid var(--color-line,#ddd);margin:22px 0}.case-view-tabs button{background:none;border:0;border-radius:0;padding:12px 18px;font-size:14px;color:var(--muted)}.case-view-tabs button[aria-pressed="true"]{color:var(--color-text,#282b26);border-bottom:2px solid currentColor;font-weight:700}.case-question{font-size:20px;line-height:1.65;margin:24px 0 18px}.case-outcome{display:flex;gap:12px;align-items:center;margin-bottom:24px}.case-outcome strong{padding:5px 10px;background:var(--color-canvas,#f5f5f2);border-radius:6px;font-size:14px}.case-outcome span{font-size:12px;color:var(--muted)}.agent-response{white-space:pre-wrap;line-height:1.85;padding:18px;background:var(--color-canvas,#f5f5f2);border-radius:8px}.answer-reason{font-size:14px;line-height:1.85}.case-detail{margin:18px 0;font-size:14px}.case-detail summary,.evaluation-settings summary,.result-more>summary{cursor:pointer;font-weight:600}.case-detail .button-row{margin:16px 0}.case-actions{margin-top:24px}.evaluation-settings{margin:20px 0;font-size:14px}.evaluation-settings>label{margin-top:16px}.csv-download{display:flex;flex-direction:column;align-items:flex-end;gap:8px;flex-shrink:0}.csv-download small{font-size:12px;color:var(--muted)}@media(max-width:700px){.csv-download{align-items:flex-start;flex-shrink:1}.page-heading{flex-wrap:wrap}}
</style>

<style scoped>
.visual-run-toolbar{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:0 0 22px;font-size:12px;color:var(--muted)}.visual-run-toolbar .button-row{margin:0;gap:16px}.visual-run-toolbar .text-button{font-size:12px;min-height:30px;gap:6px}.visual-run-toolbar select{padding:4px 8px;min-height:32px;font-size:12px;max-width:130px}.visual-holdout-note{font-size:12px;color:var(--muted);margin:0 0 14px}.visual-change-options{display:grid;gap:10px;margin:20px 0}.visual-change-options button{display:flex;align-items:center;gap:16px;background:var(--color-canvas);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:left;color:var(--color-text);width:100%}.visual-change-options button[aria-pressed=true]{border-color:#7d957b;background:#eff4ed}.visual-change-options button>span{flex:1}.visual-change-options strong{font-size:14px;display:block}.visual-change-options small{font-size:12px;color:var(--muted);display:block;line-height:1.7;margin-top:5px}@media(max-width:600px){.visual-run-toolbar{margin-bottom:18px;align-items:flex-start}.visual-run-toolbar>.button-row{gap:8px;flex-wrap:wrap;justify-content:flex-end}.visual-change-options button{padding:12px}}
</style>

<style scoped>
.visual-improve-stages{display:flex;align-items:center;gap:18px;margin:20px 0 24px;color:#a3aa9b}.visual-improve-stages button{display:flex;gap:10px;align-items:center;border:0;background:none;padding:8px 0;color:var(--muted);font-size:13px}.visual-improve-stages button>span{display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:#ecf0e6;color:#758668}.visual-improve-stages button[aria-current=step]{color:var(--color-text);font-weight:600}.visual-improve-stages button[aria-current=step]>span{background:var(--color-primary);color:#fff}.visual-improve-stages>span{display:grid;justify-items:center;gap:10px;font-size:13px;color:var(--muted)}.visual-comparison-empty{padding:36px}.visual-comparison-empty .visual-improve-stages{gap:30px;margin:0 0 30px}.visual-comparison-empty h2{font-size:23px;margin-bottom:12px}.visual-comparison-empty p{font-size:14px;color:var(--muted);margin-bottom:24px}.visual-report-tabs{display:flex;flex-wrap:wrap;gap:22px;border-bottom:1px solid var(--border);margin-bottom:24px}.visual-report-tabs button{display:flex;gap:8px;align-items:center;border:0;border-bottom:2px solid transparent;background:none;padding:10px 0 13px;color:var(--muted);font-size:13px}.visual-report-tabs button[aria-pressed=true]{color:var(--color-text);border-color:var(--color-primary)}@media(max-width:600px){.visual-improve-stages{gap:12px}.visual-improve-stages button{font-size:12px;gap:6px}.visual-comparison-empty{padding:22px}.visual-comparison-empty .visual-improve-stages{gap:14px}.visual-report-tabs{gap:16px}.visual-report-tabs button{font-size:12px}}
</style>
