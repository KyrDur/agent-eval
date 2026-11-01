<script setup>
import MarkdownContent from '../components/MarkdownContent.vue'
import PlanTrialResult from '../components/PlanTrialResult.vue'
import LogConsultation from '../components/LogConsultation.vue'
import RetestProgress from '../components/RetestProgress.vue'
import ComparisonDecision from '../components/ComparisonDecision.vue'
import ChangeMethodIllustration from '../components/ChangeMethodIllustration.vue'
import {verificationPlan} from '../change-checks.js'
import {flowTerminal} from '../retest-flow.js'
import {trialMatches,trialFinished,trialUsesHistoricalReference,savedTrialComparison} from '../plan-trial.js'
import {comparisonSummary} from '../comparison-summary.js'
import RagCoverageSummary from '../components/RagCoverageSummary.vue'
import { embeddingLabel, semanticModel, lexicalModel } from '../embedding-models.js'
import { computed, inject, ref, watch, onMounted, nextTick } from 'vue'
import RagEvidenceSummary from '../components/RagEvidenceSummary.vue'
import {changeOptions,groupedChangeOptions,recommendedNextStep} from '../retrieval-change-options.js'
import ChangeMethodHelp from '../components/ChangeMethodHelp.vue'
import {excerpt} from '../visual-results.js'
import TraceAssistant from '../components/TraceAssistant.vue'
import RunBriefing from '../components/RunBriefing.vue'
import QuestionNavigator from '../components/QuestionNavigator.vue'
import VisualResults from '../components/VisualResults.vue'
import ChangePlanEditor from '../components/ChangePlanEditor.vue'
import {proposedChange,changePlanRecord,compatibleChangeIndices,indexChangeTypes,chunkLabel} from '../change-analysis-prompt.js'
import WorkspaceIcon from '../components/WorkspaceIcon.vue'
import {selectedQuestion,questionStatus,answerExplanation,questionAnswerOutcome} from '../question-navigation.js'
import EvaluationLogExport from '../components/EvaluationLogExport.vue'
import RerankHelp from '../components/RerankHelp.vue'
import RunDiagnostics from '../components/RunDiagnostics.vue'
import ScoringEvidence from '../components/ScoringEvidence.vue'
import ScoreRecovery from '../components/ScoreRecovery.vue'
import ScoreCheckPanel from '../components/ScoreCheckPanel.vue'
import WorkspaceDrawer from '../components/WorkspaceDrawer.vue'
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
import {latestReferenceSupplement} from '../knowledge-supplement.js'
import {requiresPolicyReference} from '../ai-assistance.js'
const props=defineProps({step:String})
const work=inject('workspace'), rag=inject('retrieval'), practice=inject('practice'), {state}=rag
const calibration=inject('calibration')
const logExport=ref(null),caseConsultation=ref(null),resultWorkbench=ref(null),comparisonScoreCheck=ref(null)
async function copyCaseLog(id){if(props.step==='evaluate')resultWorkbench.value?.open('records');else compareTab.value='records';await nextTick();logExport.value?.copyCase(id)}
const name=ref('我的知识检索实验'), documents=ref([{document_id:'doc_1',title:'',text:'',metadata:{}}]), cases=ref('')
const embeddingModel=ref(semanticModel)
const scoringProfile=ref('initial-evidence-v1'),profiles=ref([]),splitReviewed=ref(false)
const policyGaps=computed(()=>(state.evalSet?.cases||[]).filter(c=>c.partition!=='HOLDOUT'&&requiresPolicyReference(c)&&c.reference_complete!==true))
async function loadProfiles(){try{profiles.value=await api.get('/retrieval-scoring-profiles',{timeoutMs:10000,retryReads:true});if(error.value==='评分方案暂时无法读取。')error.value=''}catch{error.value='评分方案暂时无法读取。'}}
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
  if(!session)return '还没有连接模型。先连接模型，再开始初测。'
  if(session.credential_status!=='PRESENT')return '当前模型密钥不可用，请重新连接模型。'
  if(session.judge_connection?.available===false)return '评分模型连接已失效，请到模型连接页恢复。'
  if(session.text_connection_status==='FAILED')return '模型连接失败。请检查服务地址、模型名称和密钥，再试一次。'
  if(session.text_connection_status!=='READY')return '密钥已保存，还需要检查连接。连接成功后就能开始初测。'
  return ''
})
const answerPrompt=ref(''),defaultAnswerPrompt=ref('')
onMounted(async()=>{try{defaultAnswerPrompt.value=(await api.get('/retrieval-answer-prompt')).prompt;if(type.value==='ANSWER_PROMPT_CHANGE'&&!answerPrompt.value)answerPrompt.value=state.baseline?.run.retrieval_config.answer_prompt||defaultAnswerPrompt.value}catch{}})
watch(type,value=>{if(value==='ANSWER_PROMPT_CHANGE')answerPrompt.value=state.baseline?.run.retrieval_config.answer_prompt||defaultAnswerPrompt.value})
const diagnosis=ref(''),risks=ref('')
const aiOrigin=ref('')
const editingChange=ref(false),changeChoices=ref({}),improvePanel=ref(null),compareTab=ref('questions')
const retrievalMode=ref('HYBRID'),contextStrategy=ref('NEIGHBORS'),candidatePool=ref(40),indexChoice=ref(''),prediction=ref(''),userRisk=ref(''),indexLoading=ref(false)
const changeIndices=computed(()=>compatibleChangeIndices(state.baseline,type.value,[...new Map([...(practice.state.library.indices||[]),...(state.index?[state.index]:[])].map(i=>[i.index_id,i])).values()]))
const changeIndex=computed(()=>changeIndices.value.find(i=>i.index_id===indexChoice.value)||null)
async function loadChangeIndices(){
 indexLoading.value=true
 try{await practice.library();if(!changeIndices.value.some(i=>i.index_id===indexChoice.value))indexChoice.value=changeIndices.value.find(i=>i.index_id===state.index?.index_id)?.index_id||changeIndices.value[0]?.index_id||''}
 catch{error.value='对照索引暂时未读到，可以重新读取。'}finally{indexLoading.value=false}
}
watch([()=>props.step,type,()=>state.baseline?.run.run_id],()=>{if(props.step==='improve'&&indexChangeTypes.includes(type.value))loadChangeIndices()})
watch(()=>state.indexJob?.status,status=>{if(status==='READY'&&props.step==='improve'&&indexChangeTypes.includes(type.value))loadChangeIndices()})
watch(()=>state.baseline?.run.run_id,()=>{
 const config=state.baseline?.run.retrieval_config||{}
 retrievalMode.value=config.retrieval_mode==='HYBRID'?'VECTOR':'HYBRID'
 contextStrategy.value=config.context_strategy==='NEIGHBORS'?'SELECTED':'NEIGHBORS'
 candidatePool.value=(config.candidate_pool_size||20)===100?80:Math.min(100,(config.candidate_pool_size||20)+20)
 indexChoice.value='';prediction.value='';userRisk.value=''
},{immediate:true})
async function prepareChangeIndex(){
 const base=state.baseline?.run.controls.index_snapshot;if(!base||!['EMBEDDING_CHANGE','CHUNKING_CHANGE'].includes(type.value))return
 const model=type.value==='EMBEDDING_CHANGE'?(base.embedding_snapshot.model==='BAAI/bge-small-zh-v1.5'?'all-MiniLM-L6-v2':'BAAI/bge-small-zh-v1.5'):base.embedding_snapshot.model
 const chunk={...base.chunk_config,...(type.value==='CHUNKING_CHANGE'?{algorithm:base.chunk_config.algorithm==='source-section-v1'?'normalized-character-window-v1':'source-section-v1'}:{})}
 await rag.buildIndexFor({knowledge_dataset_id:base.knowledge_dataset_id,version:base.knowledge_version},chunk,model)
}
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
else if(props.step==='improve'&&!state.change&&latestReferenceSupplement(state.knowledge,state.baseline?.run.run_id,state.supplementCaseId))type.value='KNOWLEDGE_UPDATE'
const reviewReason=ref(''),reviewStatus=ref('PASS'), override=ref(false)
const decisionScope=ref('FULL_SCOPE')
const conclusion=ref(''),conclusionReason=ref(''),conclusionConfirmed=ref(false)
const orderedPairs=computed(()=>comparisonSummary(state.comparison,state.baseline,state.retest,state.change).rows)
const singleTrialComparison=computed(()=>savedTrialComparison(state.trialResult,state.baseline))
watch(()=>state.comparison?.comparison_id,id=>{if(id)work.action('读取实验结论',()=>practice.loadConclusions(id))},{immediate:true})
const runSide=ref('RETEST')
watch(()=>state.knowledge,k=>{if(k){name.value=k.name;documents.value=k.documents.map(d=>({document_id:d.document_id,title:d.title,text:d.text,metadata:d.metadata}))}},{immediate:true})
watch(()=>state.evalSet,e=>{if(e){cases.value=JSON.stringify(e.cases,null,2);splitReviewed.value=!!e.split_reviewed}},{immediate:true})
watch(()=>state.baseline,v=>{if(v){selected.value=state.change?.selected_case_ids[0] || latestReferenceSupplement(state.knowledge,v.run.run_id,state.supplementCaseId)?.metadata.reference_supplement.source_case_id || v.run.case_results.find(r=>r.metrics.relevant_rank!==1)?.case_id || v.run.execution_order[0];nextK.value=v.run.retrieval_config.top_k===20?19:Math.min(20,v.run.retrieval_config.top_k+2)}},{immediate:true})
watch(()=>state.retest,()=>{runSide.value='RETEST'})
watch([selected,type],()=>{state.preview=null})
const run=computed(()=>runSide.value==='BASELINE'?state.baseline:state.retest || state.baseline), currentCase=computed(()=>state.baseline?.run.case_results.find(c=>c.case_id===selected.value))
const activeCaseId=ref(''),activePairId=ref(''),caseView=ref('answer'),caseBrowser=ref(null)
const activeCase=computed(()=>selectedQuestion(run.value?.run.case_results||[],activeCaseId.value))
watch(()=>[run.value?.run.run_id,activeCase.value?.case_id],([runId,caseId])=>{if(runId&&caseId)state.scoreCheckSelection={runId,caseId}},{immediate:true})
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
const retestIndex=computed(()=>!!state.change?.target_index_id
 ?(state.index?.index_id===state.change.target_index_id?state.index:targetIndex.value)
 :state.baseline?.run.controls.index_snapshot)
const savedChangeCases=computed(()=>(state.baseline?.run.case_results || []).filter(c=>state.change?.selected_case_ids.includes(c.case_id)))
const savedQuestionItems=computed(()=>savedChangeCases.value.map(({case_id,query})=>({case_id,query,...questionAnswerOutcome(state.retest||state.baseline,{case_id})})))
const savedCaseId=ref(''),savedCaseOpen=ref(false),savedCaseSide=ref('BASELINE')
const savedCase=computed(()=>selectedQuestion(savedChangeCases.value,savedCaseId.value))
const savedCaseView=computed(()=>savedCaseSide.value==='RETEST'&&state.retest?state.retest:state.baseline)
const savedCaseResult=computed(()=>savedCaseView.value?.run.case_results.find(c=>c.case_id===savedCase.value?.case_id))
const savedCaseAnswer=computed(()=>savedCaseView.value?.effective_answer_results?.find(a=>a.case_id===savedCase.value?.case_id))
const savedCaseExpected=computed(()=>state.baseline?.run.controls.eval_set_snapshot.cases.find(c=>c.case_id===savedCase.value?.case_id)?.expected_answer)
const savedCaseOutcome=view=>questionAnswerOutcome(view,savedCase.value||{})
function openSavedCase(){savedCaseSide.value=state.retest?'RETEST':'BASELINE';savedCaseOpen.value=true}
function savedDocumentName(id){const docs=savedCaseView.value?.run.controls.knowledge_snapshot?.documents||[];const d=docs.find(d=>d.document_id===id);return d?.title||d?.text?.match(/^#\s+(.+)/m)?.[1]||id}
watch(()=>state.change?.change_id,()=>{savedCaseId.value='';savedCaseOpen.value=false})

const savedChangeSummary=computed(()=>{
 const change=state.change
 if(!change)return ''
 const before=change.before_config,after=change.after_config,onOff=value=>value?'开启':'关闭'
 if(change.change_type==='RETRIEVAL_MODE_CHANGE'){const label={VECTOR:'向量',BM25:'BM25 关键词',HYBRID:'两路融合'};return `查找方式：${label[before.retrieval_mode||'VECTOR']} → ${label[after.retrieval_mode||'VECTOR']}`}
 if(change.change_type==='CONTEXT_STRATEGY_CHANGE'){const label={SELECTED:'仅选中片段',NEIGHBORS:'补全相邻片段',PARENT:'补全父章节'};return `实际上下文：${label[before.context_strategy||'SELECTED']} → ${label[after.context_strategy||'SELECTED']}`}
 if(change.change_type==='CANDIDATE_POOL_CHANGE')return `候选池：${before.candidate_pool_size} → ${after.candidate_pool_size}；最终返回 ${after.top_k} 条不变`
 if(change.change_type==='EMBEDDING_CHANGE')return `向量模型：${state.baseline.run.controls.index_snapshot.embedding_snapshot.model} → ${retestIndex.value?.embedding_snapshot.model||'正在读取…'}`
 if(change.change_type==='CHUNKING_CHANGE')return `切块方式：${chunkLabel(state.baseline.run.controls.index_snapshot.chunk_config)} → ${retestIndex.value?chunkLabel(retestIndex.value.chunk_config):'正在读取…'}`
 if(change.change_type==='TOP_K_CHANGE')return `返回资料数量：${before.top_k} → ${after.top_k}`
 if(change.change_type==='QUERY_REWRITE_TOGGLE')return `查询改写：${onOff(before.query_rewrite)} → ${onOff(after.query_rewrite)}`
 if(change.change_type==='RERANK_TOGGLE')return `资料重排：${onOff(before.rerank)} → ${onOff(after.rerank)}`
 if(change.change_type==='ANSWER_PROMPT_CHANGE')return '回答提示：使用本次记录的新版本'
 const oldVersion=state.baseline?.run.controls.knowledge_snapshot.version,newVersion=retestIndex.value?.knowledge_version
 return oldVersion!=null&&newVersion!=null?`知识版本：v${oldVersion} → v${newVersion}`:'知识库：使用本次选择的新版本'
})
const metrics=retrievalMetrics
const judgmentLabel=s=>({PASS:'通过',FAIL:'未通过',INVALID:'执行无效',EVIDENCE_INSUFFICIENT:'证据不足',NOT_CHECKED:'尚未检查',NOT_RUN:'尚未执行'})[s]||'旧记录未提供'
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
const changeAnalysisOptions=computed(()=>({view:state.baseline,caseId:selected.value,type:type.value,nextK:nextK.value,answerPrompt:answerPrompt.value,defaultAnswerPrompt:defaultAnswerPrompt.value,index:indexChangeTypes.includes(type.value)?changeIndex.value:state.index,knowledge:state.knowledge,retrievalMode:retrievalMode.value,contextStrategy:contextStrategy.value,candidatePool:candidatePool.value,prediction:prediction.value,userRisk:userRisk.value}))
async function propose(){
  if(work.state.busy)return
  if(state.retest){error.value='本轮已复测，请先查看前后比较。';return}
  const plan=proposedChange(changeAnalysisOptions.value)
  if(!plan.valid||!confirmed.value){error.value=plan.problem||'请核对本次方案并勾选确认。';return}
  const previousChange=state.change?.change_id
  const record=changePlanRecord(changeAnalysisOptions.value,changeNote.value,aiOrigin.value?{id:aiOrigin.value,text:diagnosis.value+'\n'+risks.value}:null)
  await rag.propose({change_type:type.value,after_config:plan.afterConfig,reason:record,selected_case_ids:[selected.value],user_confirmed:confirmed.value,verification_plan:verificationPlan(prediction.value,userRisk.value),...(plan.targetIndexId?{target_index_id:plan.targetIndexId}:{})})
  if(state.change?.change_id && state.change.change_id!==previousChange)editingChange.value=false
}
const flowActive=computed(()=>state.flow&&!flowTerminal.includes(state.flow.stage))
async function executePlan(executionMode='FULL'){
 if(work.state.busy||state.retest||flowActive.value)return
 if(state.pendingSubmission){error.value='先读取上次提交的回执，确认已有任务后再运行新方案。';return}
 const plan=proposedChange(changeAnalysisOptions.value),base=state.baseline?.run.controls.index_snapshot
 const auto=['CHUNKING_CHANGE','EMBEDDING_CHANGE'].includes(type.value)&&!changeIndex.value
 if(!plan.valid&&!auto){error.value=plan.problem;return}
 const prep=auto?{dataset_id:base.knowledge_dataset_id,version:base.knowledge_version,
  chunk_config:{...base.chunk_config,...(type.value==='CHUNKING_CHANGE'?{algorithm:base.chunk_config.algorithm==='source-section-v1'?'normalized-character-window-v1':'source-section-v1'}:{})},
  embedding_model:type.value==='EMBEDDING_CHANGE'?(base.embedding_snapshot.model==='BAAI/bge-small-zh-v1.5'?'all-MiniLM-L6-v2':'BAAI/bge-small-zh-v1.5'):base.embedding_snapshot.model}:null
 const body={baseline_run_id:state.baseline.run.run_id,provider_session_id:work.state.session.provider_session_id,
  change_type:type.value,after_config:plan.afterConfig,reason:changePlanRecord(changeAnalysisOptions.value,changeNote.value,aiOrigin.value?{id:aiOrigin.value,text:diagnosis.value+'\n'+risks.value}:null),selected_case_ids:[selected.value],user_confirmed:true,verification_plan:verificationPlan(prediction.value,userRisk.value),
  target_index_id:plan.targetIndexId,prepare_index:prep}
 if(executionMode==='TRIAL')await rag.executeTrial(body)
 else {
  if(!trialMatches(state.trialResult,{...changeAnalysisOptions.value,session:work.state.session,afterConfig:plan.afterConfig})||!trialFinished(state.trialResult)){error.value='先按当前方案试跑本题，再决定是否复测全部。';return}
  if(trialUsesHistoricalReference(state.trialResult,state.baseline)){error.value='本题可以试跑；正式整批比较前，需要先更新初测。';return}
  await rag.executePlan({...state.trialResult.flow.inputs,trial_flow_id:state.trialResult.flow.flow_id})
 }
}
async function refreshBaselineForPlan(){
 if(work.state.busy||flowActive.value)return
 const source=state.baseline?.run;if(!source)return
 rag.reset();Object.assign(state,{knowledge:source.controls.knowledge_snapshot,index:source.controls.index_snapshot,evalSet:source.controls.eval_set_snapshot,preferredChange:type.value})
 await rag.run('BASELINE',source.retrieval_config,source.verify_answers,source.controls.scoring_profile?.profile_id)
}
async function runSavedPlan(){
 const change=state.change;if(!change||flowActive.value||state.retest)return
 if(state.pendingSubmission){error.value='先读取已有提交的回执，再运行新的方案。';return}
 await rag.executeTrial({baseline_run_id:state.baseline.run.run_id,provider_session_id:work.state.session.provider_session_id,
  change_type:change.change_type,after_config:change.after_config,reason:change.reason,selected_case_ids:[selected.value||change.selected_case_ids[0]],user_confirmed:true,verification_plan:change.verification_plan||null,target_index_id:change.target_index_id||null,prepare_index:null})
}
async function showSavedResults(){if(state.comparison)work.go('compare');else await rag.compare()}
async function takeNext(next,id){
 if(next.action==='review')return reviewCaseCoverage(id)
 if(next.action==='answer-setup')return prepareAnswerEvaluation()
 if(next.action==='logs')return resultWorkbench.value?.open('logs')
 if(next.action==='source')return resultWorkbench.value?.open('evidence','source')
 if(next.method){activeCaseId.value=id;changeChoices.value[id]=next.method;chooseCaseChange()}
}
async function continueExperiment(){
 if(work.state.busy||flowActive.value||state.retest?.run.status==='RUNNING')return
 const verify=state.retest?.run.verify_answers??state.baseline?.run.verify_answers
 // A new local experiment selection preserves every prior server artifact.
 const controls=state.retest?.run.controls||state.baseline?.run.controls,config=state.retest?.run.retrieval_config
 if(!controls)return
 rag.reset();state.knowledge=controls.knowledge_snapshot;state.index=controls.index_snapshot;state.evalSet=controls.eval_set_snapshot
 if(config){topK.value=config.top_k;rewriting.value=config.query_rewrite;reranking.value=config.rerank}
 if(verify!==undefined)answers.value=verify
 rag.persist();work.go('evaluate');work.state.notice='已准备下一轮初测，之前的方案、结果与决定保留在历史记录中。核对本轮设置后开始。'
}
function openChangePlan(){
 editingChange.value=false;work.go('improve')
 nextTick(()=>{improvePanel.value?.focus({preventScroll:true});improvePanel.value?.scrollIntoView({block:'start',behavior:'smooth'})})
}
function chooseCaseChange(){
 if(work.state.busy || !activeCase.value || !caseChoice.value)return
 if(state.retest || choiceMatchesSaved.value){openChangePlan();return}
 if(selected.value!==activeCase.value.case_id || type.value!==caseChoice.value){
  diagnosis.value='';changeNote.value='';risks.value='';aiOrigin.value='';confirmed.value=false;prediction.value='';userRisk.value=''
 }
 selected.value=activeCase.value.case_id;type.value=caseChoice.value;editingChange.value=!!state.change;state.preview=null
 work.go('improve')
 nextTick(()=>{improvePanel.value?.focus({preventScroll:true});improvePanel.value?.scrollIntoView({block:'start',behavior:'smooth'})})
}
function returnToCase(){
 activeCaseId.value=selected.value;caseView.value='answer';work.go('evaluate')
 nextTick(()=>{caseBrowser.value?.focus({preventScroll:true});caseBrowser.value?.scrollIntoView({block:'start',behavior:'smooth'})})
}
function reviewCaseCoverage(caseId){
 const frozen=run.value?.run;if(!frozen)return
 state.coverageReviewTarget=JSON.parse(JSON.stringify({caseId,runId:frozen.run_id,evalSet:frozen.controls.eval_set_snapshot,index:frozen.controls.index_snapshot,knowledge:frozen.controls.knowledge_snapshot}))
 work.go('define')
}
function prepareAnswerEvaluation(){
 const frozen=run.value?.run;if(!frozen)return
 if(state.pendingSubmission){work.state.notice='先确认当前后台任务的进度，再准备新的评测，避免重复提交。';return}
 const copy=JSON.parse(JSON.stringify(frozen.controls))
 state.answerSetupSource={runId:frozen.run_id,config:JSON.parse(JSON.stringify(frozen.retrieval_config))}
 Object.assign(state,{evalSet:copy.eval_set_snapshot,index:copy.index_snapshot,knowledge:copy.knowledge_snapshot,baseline:null,retest:null,change:null,comparison:null})
 answers.value=true;topK.value=frozen.retrieval_config.top_k;rewriting.value=frozen.retrieval_config.query_rewrite;reranking.value=frozen.retrieval_config.rerank
 work.go('evaluate');rag.persist();work.state.notice='已准备包含回答的新初测；资料、题目和查找配置沿用原运行。核对模型连接和参考政策后，再点击开始。原检索记录保留。'
}
async function returnToSourceRun(){const id=state.answerSetupSource?.runId;if(!id)return;await rag.action('返回原检索运行',async()=>{await rag.open(id,{includeLatestRetest:false,useFrozenControls:true});state.answerSetupSource=null});work.go('evaluate')}
watch(()=>state.answerSetupSource?.runId,id=>{if(!id)return;const config=state.answerSetupSource.config;answers.value=true;topK.value=config.top_k;rewriting.value=config.query_rewrite;reranking.value=config.rerank},{immediate:true})
const selectedAnswer=ref(null)
async function saveReview(){if(!selectedAnswer.value || !reviewReason.value.trim()){analytics.blocked('review.save','missing_input');return}
  if(selectedAnswer.value.result.hard_rule_violations.length && reviewStatus.value==='PASS'&&!override.value){analytics.blocked('review.save','unconfirmed');return}
  await rag.review(selectedAnswer.value.runId,{case_id:selectedAnswer.value.result.case_id,human_final_status:reviewStatus.value,human_reason:reviewReason.value})
  selectedAnswer.value=null;reviewReason.value='';override.value=false}
</script>
<template>
  <details v-if="state.flow?.stage==='COMPLETE'&&step!=='compare'&&(!state.flow.inputs?.baseline_run_id||state.flow.inputs.baseline_run_id===state.baseline?.run.run_id)" class="completed-flow-record"><summary>执行记录 · {{state.flow.inputs?.execution_mode==='TRIAL'?'本题试跑已完成':'复测与比较已完成'}}</summary><RetestProgress :flow="state.flow" :baseline="state.baseline" :retest="state.flow?.inputs?.execution_mode==='TRIAL'?state.trialResult?.view:state.retest" :change="state.change" :busy="!!work.state.busy" @sync="rag.syncFlow" @resume="rag.resumeFlow" @cancel="rag.cancelFlow" @compare="work.go('compare')" /></details>
  <RetestProgress v-else-if="state.flow&&!(step==='compare'&&state.flow.stage==='COMPLETE')&&(!state.flow.inputs?.baseline_run_id||state.flow.inputs.baseline_run_id===state.baseline?.run.run_id)" :flow="state.flow" :baseline="state.baseline" :retest="state.flow?.inputs?.execution_mode==='TRIAL'?state.trialResult?.view:state.retest" :change="state.change" :busy="!!work.state.busy" @sync="rag.syncFlow" @resume="rag.resumeFlow" @cancel="rag.cancelFlow" @compare="work.go('compare')" />
  <div class="page-heading" v-if="!(step==='evaluate'&&run||step==='improve'&&state.baseline)"><div><p class="eyebrow">我的实验</p><h1>{{step==='define'?'准备几道测试题':step==='evaluate'?'看看这个客服 Agent 答得怎么样':step==='improve'?'选一个问题，试着改改':'改完之后，有没有变好？'}}</h1><p>{{step==='improve'?'先对照原文确认问题，再选这次要改什么。':step==='compare'?(singleTrialComparison&&!state.comparison?'本题试跑后就能查看，不需要先测完全部。':'别只看总分，也看看有没有题答得更差了。'):'系统会保存这次用的资料、题目和模型设置，方便之后比较。'}}</p></div><div v-if="step==='evaluate'&&run||step==='compare'&&state.comparison" class="csv-download"><button v-if="step==='evaluate'" type="button" class="secondary" @click="showLogs">查看运行日志</button><button v-if="step==='evaluate'" class="secondary" :disabled="csvBusy||!!work.state.busy||run.run.status==='RUNNING'" @click="downloadCsv('run')">{{csvBusy?'正在导出…':'导出本次结果 CSV'}}</button><button v-else class="secondary" :disabled="csvBusy||!!work.state.busy" @click="downloadCsv('comparison')">{{csvBusy?'正在导出…':'导出前后对比 CSV'}}</button><small>包含本次全部题目，不受页面筛选影响</small><small v-if="step==='evaluate'&&run.run.status==='RUNNING'" role="status">运行结束后可以导出</small></div><span v-else class="pill">客服知识问答</span></div>
  <p v-if="csvNotice" :class="['note',csvError?'danger':'positive']" :role="csvError?'alert':'status'">{{csvNotice}}</p>
  <p v-if="error" role="alert" class="note danger">{{error}}</p>
  <section v-if="state.pendingSubmission||state.progressIssue" class="note warning" aria-label="评测连接恢复"><strong>{{state.pendingSubmission?(state.pendingSubmission.run_id?'评测已提交':'正在确认提交结果'):'暂时无法读取最新进度'}}</strong><p>{{state.progressIssue||(state.pendingSubmission.run_id?'正在读取这次任务的进度，暂时不要再次开始评测。':'已保存本次请求编号，正在等待服务器回执。')}}</p><button type="button" class="secondary" :disabled="!!work.state.busy" @click="rag.syncProgress()">读取这次评测</button><small class="recovery-read-note">这里只读取原任务，不会重新调用模型。</small></section>
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
    <section v-else-if="!state.baseline&&(!state.pendingSubmission||state.canRetrySubmission)" class="panel">
      <h2>{{state.answerSetupSource?'准备包含回答的新初测':'开始第一次评测'}}</h2><p v-if="state.answerSetupSource" class="note">原来的检索运行保留。本次会用相同查找配置生成回答，并按所选标准评分。<button type="button" class="text-button" @click="returnToSourceRun">返回原检索运行（不开始评测）</button></p>
      <label>评测内容<select v-model="answers"><option :value="true">评测 Agent 的回答</option><option :value="false">只检查资料查找</option></select></label>
      <p class="muted">{{answers?'让 Agent 根据资料回答，再由评分模型检查回答。':'对照每题标注，检查有没有找到正确资料。'}}</p>
      <div v-if="answers&&policyGaps.length" class="note warning" role="status"><strong>{{policyGaps.length}} 道题需要先核对参考资料</strong><p>确认原文足够判断每道题，评测时才能给出通过或不通过。</p><button type="button" class="secondary" @click="work.go('define')">去核对题目 →</button></div>
      <details class="evaluation-settings"><summary>调整评测设置</summary>
       <label>每题最多给模型参考几段资料<input v-track="{action:'retrievalpage.edit_start',placement:'RetrievalPage.editor',kind:'edit'}" v-model.number="topK" type="number" min="1" max="20" /></label>
       <div class="button-row"><label class="check"><input v-track="{action:'run.rewrite',placement:'RetrievalPage.control_12'}" v-model="rewriting" type="checkbox" />先改写问题，帮助查找</label><label class="check"><input v-track="{action:'run.rerank',placement:'RetrievalPage.control_13'}" v-model="reranking" type="checkbox" />重新排列找到的资料</label></div>
       <RerankHelp v-if="reranking" :top-k="topK" />
       <p v-if="answers" class="muted">按参考资料检查回答是否准确、条件是否完整，并给出理由。前后比较沿用同一评分标准。</p>
      </details>
      <RunBriefing :session="work.state.session" :index="state.index" :cases="state.evalSet.cases.filter(c=>c.partition!=='HOLDOUT')" :config="{top_k:topK,query_rewrite:rewriting,rerank:reranking}" :verify-answers="answers" />
      <button v-track="{action:'run.baseline',placement:'RetrievalPage.control_15',core:true,reason:(work.state.busy ? 'busy' : !work.state.session ? 'connection' : work.state.session.credential_status !== 'PRESENT' ? 'credentials' : 'connection')}" class="primary" :disabled="!!work.state.busy || !!connectionBlocker" @click="rag.run('BASELINE',{...(state.answerSetupSource?.config||{}),top_k:topK,query_rewrite:rewriting,rerank:reranking},answers,scoringProfile)">{{state.pendingSubmission?'按原参数重试提交':'开始评测'}}</button>
      <div v-if="connectionBlocker" class="note warning" role="status"><p>{{connectionBlocker}}</p><div class="button-row"><button v-if="work.state.session?.credential_status==='PRESENT'" class="secondary" :disabled="!!work.state.busy" @click="work.testConnection">测试模型连接</button><button class="text-button" :disabled="!!work.state.busy" @click="work.go('setup')">去连接模型 →</button></div></div>
    </section>
    <template v-if="run">
      <div class="visual-run-toolbar"><span>{{run.run.run_type==='BASELINE'?'首次评测':'修改后复测'}} · {{({COMPLETE:'已完成',RUNNING:'运行中',PARTIAL:'部分完成',FAILED:'运行失败'})[run.run.status]||run.run.status}}</span><div class="button-row"><select v-if="state.retest" aria-label="查看哪次评测" v-model="runSide"><option value="BASELINE">修改前</option><option value="RETEST">修改后</option></select><button v-if="state.retest" type="button" class="text-button" :disabled="!!work.state.busy" @click="rag.compare">查看前后比较 →</button><button type="button" class="text-button" :disabled="csvBusy||!!work.state.busy||run.run.status==='RUNNING'" @click="downloadCsv('run')"><WorkspaceIcon name="download" :size="16" />{{csvBusy?'正在导出…':'导出结果'}}</button></div></div>
      <p v-if="run.run.status==='RUNNING'" class="note" role="status">已完成 {{run.run.case_results.filter(c=>c.case_latency_ms!=null).length}}/{{run.run.execution_order.length}} 题。后台继续运行，结果会自动更新。</p>
      <p v-if="run.run.controls.evaluation_scope?.holdout_count" class="visual-holdout-note">本次只评调试题；{{run.run.controls.evaluation_scope.holdout_count}} 道保留题留待独立验证。</p>
      <VisualResults ref="resultWorkbench" :view="run" v-model="activeCaseId" :can-modify="run.run.run_type==='BASELINE'&&['COMPLETE','PARTIAL'].includes(run.run.status)">
       <template #scorecheck="{row:c}"><ScoreCheckPanel :key="run.run.run_id+c.case_id" :view="run" :case-id="c.case_id" :can-review="answerFor(c.case_id)?.execution_status==='SUCCESS'&&answerFor(c.case_id)?.judge_status!=='FAILED'&&!answerFor(c.case_id)?.evaluation_error" @review="resultWorkbench.open('review')" /></template>
       <template #answer="{row:c}"><h3>{{c.query}}</h3><h4>Agent 的完整回答</h4><MarkdownContent class="agent-response" :source="answerFor(c.case_id)?.turn_evidence?.[0]?.response || '本题没有保存回答，请查看运行日志。'" /><template v-if="expectedFor(c.case_id)"><h4>预期回答</h4><MarkdownContent class="agent-response" :source="expectedFor(c.case_id)" /></template></template>
       <template #source="{row:c}"><h3>这题参考的资料 · {{c.results?.length||0}} 段</h3><ol class="rag-results"><li v-for="r in c.results" :key="r.chunk_id"><strong>{{run.run.controls.knowledge_snapshot?.documents?.find(d=>d.document_id===r.document_id)?.title||'参考资料'}}</strong><p>{{r.text}}</p></li></ol><p v-if="!c.results?.length" class="muted">本题没有返回资料，可在运行日志中查看查找过程。</p></template>
       <template #reason="{row:c}"><template v-if="run.run.verify_answers"><h3>判定理由</h3><p>{{excerpt(answerExplanation(answerFor(c.case_id)),220)}}</p></template><p v-else>本轮只检查资料查找，没有生成或评判回答。</p><ScoringEvidence v-if="answerFor(c.case_id)" :result="answerFor(c.case_id)" :retrieval="c" :top-k="run.run.retrieval_config?.top_k" :documents="run.run.controls.knowledge_snapshot?.documents" /><ScoreRecovery :key="run.run.run_id+c.case_id" :view="run" :case-id="c.case_id" /></template>
       <template #logs="{row:c}"><RunDiagnostics :retrieval="c" :answer="answerFor(c.case_id)" :verify-answers="run.run.verify_answers" expanded title="运行日志" /><ScoreRecovery :key="run.run.run_id+c.case_id" :view="run" :case-id="c.case_id" /><EvidenceDetails :data="c" title="本题原始记录" copyable /><button type="button" class="secondary" @click="copyCaseLog(c.case_id)">复制本题日志</button></template>
       <template #scoring="{row:c}"><ScoreRecovery :key="run.run.run_id+c.case_id" :view="run" :case-id="c.case_id" /></template>
       <template #primary-action="{row:c}"><button v-if="questionStatus(run,c)==='评分失败'" type="button" class="primary" @click="resultWorkbench.open('scoring')">仅重评本题 →</button><template v-else-if="run.run.run_type==='BASELINE'&&['COMPLETE','PARTIAL'].includes(run.run.status)"><button type="button" class="primary" :disabled="!!work.state.busy||flowActive" @click="resultWorkbench.open('modify')">选择改法 →</button></template><button v-else-if="state.retest&&run.run.status!=='RUNNING'" type="button" class="primary" :disabled="!!work.state.busy" @click="rag.compare">查看前后比较 →</button><button v-else type="button" class="secondary" @click="resultWorkbench.open('logs')">查看运行日志</button></template>
       <template #diagnosis="{row:c}"><LogConsultation ref="caseConsultation" compact consult-only log-label="本题完整运行日志" :view="run" :case-id="c.case_id" /></template>
       <template #case-tools><button type="button" @click="caseConsultation?.show('logs')">本题完整运行日志</button></template>
       <template #modify="{row:c}">
        <RagEvidenceSummary :view="run" :case-id="c.case_id" @inspect="resultWorkbench.open('evidence','reason')" @next="takeNext($event,c.case_id)" />
        <template v-if="!state.retest"><p v-if="state.change?.selected_case_ids.includes(c.case_id)" class="note">已记录：{{changeLabel(state.change.change_type)}} · {{changeStatus}}</p>
         <h3>这次只选一种改法</h3><div class="grouped-change-options" aria-label="选择本题修改方式"><section v-for="group in groupedChangeOptions" :key="group.id" class="visual-change-group" :aria-label="group.label"><div class="change-group-heading"><h3>{{group.label}}</h3><p>{{group.hint}}</p></div><div class="visual-change-options"><div v-for="option in group.options" :key="option.value" class="visual-change-option"><button type="button" class="visual-change-select" :aria-pressed="caseChoice===option.value" :disabled="!!work.state.busy" v-track="{action:'change.type',placement:'RagUpgrade.control'}" @click="caseChoice=option.value"><WorkspaceIcon :name="option.icon" :size="21" /><span><strong>{{option.label.split('（')[0]}} <em v-if="option.added">新</em></strong><small>{{option.hint}}</small></span><WorkspaceIcon v-if="caseChoice===option.value" name="check" :size="18" /></button><ChangeMethodHelp :type="option.value" :label="option.label" /></div></div></section></div>
         <div class="change-choice-footer"><span>{{caseChoice?changeLabel(caseChoice).split('（')[0]:'选择一项，再确认具体参数'}}</span><button type="button" class="primary" :disabled="!!work.state.busy||!caseChoice" @click="chooseCaseChange">{{caseChoiceAction}} →</button></div>
        </template><template v-else><p class="note">本轮复测使用：{{changeLabel(state.change?.change_type)}}</p><button type="button" class="primary" @click="openChangePlan">查看本轮修改</button></template>
       </template>
       <template #suggest="{row:c}"><TraceAssistant embedded :run-type="run.run.run_type" :run-id="run.run.run_id" :case-id="c.case_id" :can-suggest="run.run.run_type==='BASELINE'" @suggestion="useSuggestion" /></template>
       <template #review="{row:c}"><template v-for="a in run.effective_answer_results.filter(a=>a.case_id===c.case_id)" :key="a.case_id"><p>模型判定：{{({PASS:'通过',FAIL:'不通过',INVALID:'执行失败'})[a.original_status]||a.original_status}} · 人工复核：{{a.human_evaluation_state||a.human_final_status||'未复核'}}</p><div class="button-row"><button class="secondary" :disabled="a.execution_status!=='SUCCESS'||a.judge_status==='FAILED'||!!a.evaluation_error" @click="selectedAnswer={result:a,runId:run.run.run_id}">人工复核回答</button><button class="secondary" :disabled="!a.turn_evidence[0]?.response" @click="calibration.queue(run.run.run_id,c.case_id)">加入校准样本</button></div></template>
        <section v-if="selectedAnswer?.result.case_id===c.case_id" class="panel"><h3>回答人工复核</h3><label>人工最终判定<select v-model="reviewStatus"><option value="PASS">通过</option><option value="FAIL">不通过</option><option value="EVIDENCE_INSUFFICIENT">证据不足，无法评判</option><option value="NOT_APPLICABLE">不属于本次评测范围</option></select></label><label>回答复核理由<textarea v-model="reviewReason" rows="3" required /></label><label v-if="selectedAnswer.result.hard_rule_violations.length&&reviewStatus==='PASS'" class="check"><input v-model="override" type="checkbox" />确认覆盖规则检查的判定，保留原违规证据</label><button class="primary" :disabled="!!work.state.busy||!reviewReason.trim()||(selectedAnswer.result.hard_rule_violations.length&&reviewStatus==='PASS'&&!override)" @click="saveReview">保存回答复核</button></section>
        <RetrievalIssuePanel :run-id="run.run.run_id" :case-id="c.case_id" /></template>
       <template #checks><TrustedResults :view="run" @inspect-case="inspectCase" /></template>
       <template #metrics><RagCoverageSummary :summary="run.run.metrics.fact_coverage" /><p class="muted">本次运行：{{embeddingLabel(run.run.controls.index_snapshot)}}</p><div class="rag-metric-grid"><section v-for="metric in metrics" :key="metric.id" class="metric-card"><div class="metric-heading"><small>{{metric.label}}</small><MetricHelp :metric="metric" /></div><strong>{{format(run.run.metrics[metric.id])}}</strong><small>{{run.run.metrics.denominators?.[metric.id]||0}} 道有效标注题</small></section></div><h3>实际调用与用量</h3><p>调用 {{run.run.sample_flow?.cost?.actual_requests??'未记录'}} 次 · 已知用量 {{run.run.sample_flow?.cost?.known_total_tokens??'未记录'}} 个词元</p><p class="muted">未知用量的请求 {{run.run.sample_flow?.cost?.unknown_usage_requests??'未记录'}} 次；费用以服务账单为准。</p><ExperimentHealth :view="run" /></template>
       <template #records><p class="muted">导出包含本次全部题目，不受页面筛选影响。</p><button type="button" class="secondary" :disabled="csvBusy||!!work.state.busy||run.run.status==='RUNNING'" @click="downloadCsv('run')">导出本次结果 CSV</button><EvaluationLogExport ref="logExport" :key="run.run.run_id" :view="run" /><EvidenceDetails :data="run" title="本次运行的完整记录" /></template>
      </VisualResults>
    </template>
  </template>
  <template v-else-if="step==='improve'">
    <p v-if="!state.baseline" class="empty">先运行 Retrieval Baseline，再从结果选择问题。</p>
    <section v-else ref="improvePanel" class="panel" :class="{'plan-workbench':!state.change||editingChange||state.trialResult&&!state.retest||state.flow?.inputs?.execution_mode==='TRIAL'&&!state.retest}" tabindex="-1"><template v-if="!state.change || editingChange || state.trialResult&&!state.retest || state.flow?.inputs?.execution_mode==='TRIAL'&&!state.retest">
      <p v-if="editingChange" class="note">保存后使用新方案，原记录保留。<button type="button" class="text-button" @click="editingChange=false">取消修改</button></p>
      <p v-if="aiOrigin" class="note">已有 AI 草稿供参考，原因和效果尚未验证。保存方案不代表已确认根因。</p>
      <ChangePlanEditor :view="state.baseline" v-model:case-id="selected" v-model:type="type" v-model:next-k="nextK" v-model:answer-prompt="answerPrompt" v-model:confirmed="confirmed" :default-answer-prompt="defaultAnswerPrompt" :index="changeIndex" :knowledge="state.knowledge" :indices="changeIndices" v-model:index-id="indexChoice" v-model:retrieval-mode="retrievalMode" v-model:context-strategy="contextStrategy" v-model:candidate-pool="candidatePool" :index-job="state.indexJob" :index-loading="indexLoading" :options="changeOptions" :busy="!!work.state.busy||flowActive" :locked="!!state.retest||!!state.pendingSubmission" :session="work.state.session" :flow="state.flow" :trial="state.trialResult" :preview="state.preview" :can-preview="work.state.session?.credential_status==='PRESENT'" @submit="executePlan('FULL')" @trial="executePlan('TRIAL')" @compare="work.go('compare')" @refresh-baseline="refreshBaselineForPlan" @draft="propose" @return="returnToCase" @connect="work.go('setup')" @tests="work.go('define')" @knowledge="work.go('knowledge')" @supplement="rag.supplementFromReference({view:state.baseline,caseId:selected})" @prepare-index="prepareChangeIndex" @refresh-indices="loadChangeIndices" @cancel-index="rag.cancelIndex" @read-index="rag.syncIndex" @preview="rag.preview(currentCase.query)" />
     </template>
      <template v-else>
        <div class="saved-plan-hero"><div><div class="section-heading"><div><span class="eyebrow">本轮已保存的方案</span><h2>本轮修改记录</h2></div><span class="pill">{{state.retest?({RUNNING:'复测中',COMPLETE:'复测完成',PARTIAL:'部分完成',FAILED:'复测失败'})[state.retest.run.status]||'已有复测':changeStatus}}</span></div><div class="change-summary saved-method-summary"><strong>{{savedChangeSummary}}</strong><ChangeMethodHelp :type="state.change.change_type" /></div></div><ChangeMethodIllustration :type="state.change.change_type" :retrieval-mode="state.change.after_config.retrieval_mode||'VECTOR'" :context-strategy="state.change.after_config.context_strategy||'SELECTED'" :ready="state.change.implemented_status==='APPLIED'" /></div>
        <div class="saved-plan-actions" aria-label="这轮修改的下一步">
         <template v-if="state.retest"><p>{{state.retest.run.status==='RUNNING'?'复测正在运行，先查看进度。':'复测已结束，查看前后变化再做决定。'}}</p><div class="button-row"><button type="button" class="primary" :disabled="!!work.state.busy||state.retest.run.status==='RUNNING'" @click="showSavedResults">查看这轮结果 →</button><button type="button" class="secondary" :disabled="!!work.state.busy||flowActive||state.retest.run.status==='RUNNING'" @click="continueExperiment">准备下一轮实验</button></div><p class="muted">下一轮会重新初测，旧结果保留。</p><p v-if="work.state.session?.credential_status!=='PRESENT'||work.state.session?.text_connection_status!=='READY'" class="saved-connection-note">运行下一轮前，需要恢复模型连接。<button type="button" class="text-button" @click="work.go('setup')">恢复模型连接 →</button></p></template>
         <template v-else><p>核对方案后复测原题，也可以先调整方案。</p><div v-if="work.state.session?.credential_status!=='PRESENT'||work.state.session?.text_connection_status!=='READY'" class="note warning"><p>当前模型连接不可用。恢复连接后，就能运行这份方案。</p><button type="button" class="secondary" @click="work.go('setup')">恢复模型连接 →</button></div><div class="button-row"><button type="button" class="primary" :disabled="!!work.state.busy||flowActive||work.state.session?.credential_status!=='PRESENT'||work.state.session?.text_connection_status!=='READY'" @click="runSavedPlan">先按保存方案试本题</button><button v-if="!flowActive" type="button" class="secondary" @click="editingChange=true">调整方案</button></div></template>
        </div>
        <section v-if="savedCase" class="saved-plan-questions" aria-label="本次修改涉及的题目">
         <QuestionNavigator :items="savedQuestionItems" :model-value="savedCase.case_id" @update:model-value="savedCaseId=$event" label="修改题目导航" compact status-colors />
         <div class="saved-status-legend" aria-label="题号颜色说明"><span class="answer-pass"><WorkspaceIcon name="check" :size="14" />蓝色 · 答对</span><span class="answer-fail"><WorkspaceIcon name="close" :size="14" />红色 · 答错</span><span class="answer-unknown"><WorkspaceIcon name="minus" :size="14" />灰色 · 未检查或无法判断</span></div><p class="saved-status-scope">{{(state.retest||state.baseline)?.run.verify_answers?(state.retest?'题号按修改后的回答判定标注。':'题号按初测的回答判定标注。'):'这轮只检查了资料查找，还没有检查回答。'}}</p>
         <article class="saved-plan-case" aria-live="polite"><h3>{{savedCase.query}}</h3><p class="saved-case-status"><span :class="'answer-'+savedCaseOutcome(state.baseline).tone">修改前：{{savedCaseOutcome(state.baseline).status}}</span><span v-if="state.retest" :class="'answer-'+savedCaseOutcome(state.retest).tone">修改后：{{savedCaseOutcome(state.retest).status}}</span></p><button type="button" class="text-button" @click="openSavedCase">查看这题的资料与回答 →</button></article>
        </section>
        <details class="case-detail"><summary>查看当时的方案与判断记录</summary><p class="saved-change-reason">{{state.change.reason}}</p></details>
        <p v-if="state.change.implemented_status==='APPLIED' && !state.retest && !retestIndex" class="note warning">{{targetIndexError?'复测资料暂时无法读取，请同步状态后重试。':'正在读取复测资料…'}}</p>
        <RunBriefing v-if="state.change.implemented_status==='APPLIED' && !state.retest && retestIndex" :session="{configuration:state.baseline.run.provider_configuration_snapshot}" :index="retestIndex" :cases="state.baseline.run.controls.eval_set_snapshot.cases.filter(c=>c.partition!=='HOLDOUT')" :config="state.change.after_config" :verify-answers="state.baseline.run.verify_answers" />
        <LogConsultation kind="plan" :view="state.baseline" :case-id="savedCase?.case_id" :change="state.change" :flow="state.flow" />
        <EvidenceDetails data-analytics-location="RetrievalPage.EvidenceDetails.7" :data="state.change" title="完整修改记录" />
      </template>
    </section>
  </template>
  <template v-else-if="step==='compare'">
    <section v-if="!state.comparison&&singleTrialComparison" class="panel single-trial-comparison" aria-label="单题变化"><span class="eyebrow">单题试跑 · 1 / {{singleTrialComparison.total}} 题</span><h2>{{singleTrialComparison.question}}</h2><p class="muted">这里只查看本题；其余题目尚未复测。</p><PlanTrialResult comparison-mode :trial="state.trialResult" :baseline="state.baseline" :case-id="singleTrialComparison.caseId" /><button type="button" class="secondary" @click="work.go('improve')">返回修改方案 →</button></section>
    <section v-else-if="!state.comparison" class="panel visual-comparison-empty"><div class="visual-improve-stages"><span><WorkspaceIcon name="chart" :size="27" />首次评测</span><WorkspaceIcon name="arrow" /><span><WorkspaceIcon name="adjust" :size="27" />一次修改</span><WorkspaceIcon name="arrow" /><span><WorkspaceIcon name="compare" :size="27" />同题复测</span></div><h2>先试一道题，就能看变化</h2><p>试跑后查看本题的新旧回答，整批复测后再看其他题是否受影响。</p><button v-if="!state.baseline" type="button" class="primary" @click="work.go('evaluate')">先完成首次评测 →</button><button v-else-if="!state.retest" type="button" class="primary" @click="work.go('improve')">去试本题 →</button><button v-else type="button" class="primary" :disabled="!!work.state.busy" @click="rag.compare">生成前后比较 →</button></section>
    <template v-else><ComparisonDecision :trial="state.trialResult" :comparison="state.comparison" :baseline="state.baseline" :retest="state.retest" :change="state.change" :conclusions="practice.state.conclusions" :busy="!!work.state.busy" @case="activePairId=$event;compareTab='questions'" @career="work.go('career')" @continue="continueExperiment" @overview="compareTab='overview'" /><nav class="visual-report-tabs" aria-label="前后比较内容"><button v-for="t in [{id:'questions',label:'逐题变化',icon:'compare'},{id:'overview',label:'本次概览',icon:'chart'},{id:'decision',label:'独立验证',icon:'check'},{id:'records',label:'评分与原始记录',icon:'database'}]" :key="t.id" type="button" :aria-pressed="compareTab===t.id" @click="compareTab=t.id"><WorkspaceIcon :name="t.icon" :size="17" />{{t.label}}</button></nav><section v-if="compareTab==='overview'" class="panel"><h2>{{state.comparison.comparable?'控制条件可比较':'控制条件不可比较'}} · {{state.comparison.comparison_completeness}}</h2><p class="note warning">本次为单次对照，可重复运行检查变化是否稳定。</p><p v-if="state.comparison.comparison_completeness==='PARTIAL'">本次只比较已完成且有效的题目。</p><p v-if="state.comparison.comparability_reasons.length">{{state.comparison.comparability_reasons.join(' · ')}}</p></section>
      <RagCoverageSummary v-if="compareTab==='overview'&&state.comparison.paired_metrics.fact_coverage" :comparison="state.comparison.paired_metrics.fact_coverage" /><TrustedResults v-if="compareTab==='overview'" :comparison="state.comparison" /><EvaluationLogExport v-if="compareTab==='records'" ref="logExport" :key="state.comparison.comparison_id" :comparison="state.comparison" :baseline-view="state.baseline" :retest-view="state.retest" /><div v-if="compareTab==='overview'" class="rag-metric-grid"><section v-for="metric in metrics" :key="metric.id" class="metric-card"><div class="metric-heading"><small>{{metric.label}} · 有效匹配题</small><MetricHelp data-analytics-location="RetrievalPage.MetricHelp.8" :metric="metric" /></div><strong>{{format(state.comparison.paired_metrics.baseline[metric.id])}} → {{format(state.comparison.paired_metrics.retest[metric.id])}}</strong><small>分母 {{state.comparison.paired_metrics.baseline.denominators[metric.id]}}</small></section></div>
      <ScoreReportComparison v-if="compareTab==='records'" :key="state.comparison.comparison_id" :comparison="state.comparison" />
      <section v-if="compareTab==='questions'" class="panel"><h2>逐题比较</h2><QuestionNavigator :items="pairItems" :model-value="activePair?.case_id" @update:model-value="activePairId=$event" label="比较题目导航" /><div class="case-view-tabs" role="group" aria-label="比较视图"><button type="button" :aria-pressed="caseView==='answer'" @click="caseView='answer'">前后回答</button><button type="button" :aria-pressed="caseView==='logs'" @click="caseView='logs'">运行日志</button></div></section>
      <template v-if="compareTab==='questions'"><section v-for="p in visiblePairs" :key="p.case_id" class="panel rag-case"><div class="section-heading"><h3>{{p.query}}</h3><strong>{{labels[p.transition]}}</strong></div><p v-if="p.reason">{{p.reason}}</p>
        <div v-if="caseView==='answer'&&(p.baseline_answer||p.retest_answer)" class="pair-answer-overview" aria-label="两次回答判定"><article v-for="[key,label] in [['baseline_answer','修改前'],['retest_answer','修改后']]" :key="key" :class="['pair-answer-card',{'pair-pass':p[key]?.final_status==='PASS','pair-fail':p[key]?.final_status==='FAIL'}]"><div><span class="pair-verdict-symbol"><WorkspaceIcon :name="p[key]?.final_status==='PASS'?'check':p[key]?.final_status==='FAIL'?'close':'minus'" :size="22" /></span><span>{{label}}<strong>{{judgmentLabel(p[key]?.final_status)}}</strong></span></div><p>{{excerpt(p[key]?.original_reason,90)||'尚未形成有效判定。'}}</p></article></div>
        <div v-if="caseView==='logs'" class="two-column"><RunDiagnostics expanded :retrieval="p.baseline" :answer="p.baseline_answer" :verify-answers="state.baseline?.run.verify_answers" title="初测运行诊断" /><RunDiagnostics expanded :retrieval="p.retest" :answer="p.retest_answer" :verify-answers="state.retest?.run.verify_answers" title="复测运行诊断" /></div>
        <details v-if="caseView==='answer'" class="case-detail"><summary>查看两次查到的资料</summary><p>相关资料的位置：{{rank(p.baseline?.metrics.relevant_rank)}} → {{rank(p.retest?.metrics.relevant_rank)}} · 最终参考 {{p.baseline?.top_k??'未记录'}} → {{p.retest?.top_k??'未记录'}} 条</p><div class="two-column"><div><h4>修改前的资料</h4><ol class="rag-results"><li v-for="r in p.baseline?.results" :key="r.chunk_id">{{r.document_id}}<p>{{r.text}}</p></li></ol></div><div><h4>修改后的资料</h4><ol class="rag-results"><li v-for="r in p.retest?.results" :key="r.chunk_id">{{r.document_id}}<p>{{r.text}}</p></li></ol></div></div></details>
        <details v-if="caseView==='answer' && (p.baseline_answer || p.retest_answer)" class="evidence"><summary v-track="{action:'comparison.answer_change',placement:'RetrievalPage.control_37'}">展开两次完整回答 · {{({'FAIL→PASS':'回答由未通过变为通过','PASS→FAIL':'回答由通过变为未通过','PASS→PASS':'回答保持通过','FAIL→FAIL':'回答仍未通过',NOT_COMPARABLE:'本题回答无法比较'})[p.answer_transition]||'回答变化尚不确定'}}</summary><div class="two-column"><div><h4>修改前 · {{judgmentLabel(p.baseline_answer?.final_status)}}</h4><MarkdownContent :source="p.baseline_answer?.turn_evidence[0]?.response" /><p>{{p.baseline_answer?.original_reason}}</p><button v-if="state.baseline?.run.verify_answers" type="button" class="text-button" @click="comparisonScoreCheck={view:state.baseline,caseId:p.case_id}">检查修改前的评分</button></div><div><h4>修改后 · {{judgmentLabel(p.retest_answer?.final_status)}}</h4><MarkdownContent :source="p.retest_answer?.turn_evidence[0]?.response" /><p>{{p.retest_answer?.original_reason}}</p><button v-if="state.retest?.run.verify_answers" type="button" class="text-button" @click="comparisonScoreCheck={view:state.retest,caseId:p.case_id}">检查修改后的评分</button></div></div><p class="note">对照两次回答和判定理由，查看哪些地方变好了，哪些还需要调整。</p></details>
      <RetrievalIssuePanel :run-id="state.comparison.baseline_run_id" :case-id="p.case_id" :comparison-id="state.comparison.comparison_id" /><button type="button" class="secondary" @click="copyCaseLog(p.case_id)">复制本题对比日志</button></section></template><AgentHoldout v-if="compareTab==='decision'" :comparison="state.comparison" /><EvidenceDetails v-if="compareTab==='records'" data-analytics-location="RetrievalPage.EvidenceDetails.10" :data="state.comparison" title="完整检索比较证据" />
    </template>
  </template>
  <WorkspaceDrawer :open="savedCaseOpen" title="本题的资料与回答" @close="savedCaseOpen=false">
   <template v-if="savedCase"><h3 class="saved-drawer-question">{{savedCase.query}}</h3>
    <div v-if="state.retest" class="saved-case-tabs" role="group" aria-label="查看哪次记录"><button type="button" :class="savedCaseSide==='BASELINE'?'secondary':'text-button'" :aria-pressed="savedCaseSide==='BASELINE'" @click="savedCaseSide='BASELINE'">修改前</button><button type="button" :class="savedCaseSide==='RETEST'?'secondary':'text-button'" :aria-pressed="savedCaseSide==='RETEST'" @click="savedCaseSide='RETEST'">修改后</button></div>
    <h4>当时的回答</h4><MarkdownContent v-if="savedCaseAnswer?.turn_evidence?.length" class="agent-response" :source="savedCaseAnswer.turn_evidence.map(t=>t.response).filter(Boolean).join('\n\n')||'未保存回答原文。'" /><p v-else class="muted">{{savedCaseView?.run.verify_answers?'本题没有保存成功的回答，可以查看完整日志。':'这次只检查资料查找，没有生成客服回答。'}}</p>
    <details v-if="savedCaseExpected" class="case-detail"><summary>这题的参考答案</summary><p class="saved-case-passage">{{savedCaseExpected}}</p></details>
    <h4>当时提供的资料 · {{savedCaseResult?.results?.length??0}} 条</h4><article v-for="(r,i) in savedCaseResult?.results||[]" :key="r.chunk_id" class="saved-case-source"><h4>{{i+1}}. {{savedDocumentName(r.document_id)}}</h4><p class="saved-case-passage">{{r.text}}</p></article><p v-if="!savedCaseResult?.results?.length" class="muted">这份记录没有保存检索资料。</p>
    <LogConsultation :key="savedCase.case_id+savedCaseSide" :view="savedCaseView" :case-id="savedCase.case_id" />
   </template>
  </WorkspaceDrawer>
  <WorkspaceDrawer :open="!!comparisonScoreCheck" title="检查这次评分" @close="comparisonScoreCheck=null"><ScoreCheckPanel v-if="comparisonScoreCheck" :view="comparisonScoreCheck.view" :case-id="comparisonScoreCheck.caseId" /></WorkspaceDrawer>
</template>
<style scoped>
.visual-change-group .visual-change-options>button:only-child{grid-column:1/-1}
.grouped-change-options{margin-top:22px}.visual-change-group{margin:0 0 24px}.change-group-heading h3{font-size:15px!important;margin:0!important}.change-group-heading p{font-size:11px!important;color:var(--muted);margin:5px 0 0!important}.visual-change-group .visual-change-options{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:12px 0}.visual-change-group .visual-change-options button{padding:13px;gap:10px;align-items:flex-start}.visual-change-group .visual-change-options button>span{min-width:0}.visual-change-group .visual-change-options strong{font-size:13px;line-height:1.6}.visual-change-group .visual-change-options small{font-size:11px}.visual-change-group em{display:inline-block;vertical-align:middle;font-style:normal;font-size:9px;padding:1px 5px;background:#e5ecde;color:#526446;border-radius:4px;margin-left:4px}.change-choice-footer{position:sticky;bottom:-24px;margin:20px -24px -24px;padding:15px 24px;background:var(--color-surface);border-top:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:12px;z-index:1}.change-choice-footer>span{font-size:11px;color:var(--muted)}.change-choice-footer .primary{font-size:12px;flex-shrink:0}@media(max-width:500px){.visual-change-group .visual-change-options{grid-template-columns:1fr}.change-choice-footer{bottom:-18px;margin-inline:-18px;margin-bottom:-18px;padding:14px 18px}.change-choice-footer>span{max-width:110px}}

.pair-answer-overview{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:20px 0}.pair-answer-card{padding:18px;border:1px solid var(--border);background:var(--color-canvas);border-radius:10px;min-width:0}.pair-answer-card>div{display:flex;gap:12px;align-items:center}.pair-verdict-symbol{display:grid;place-items:center;width:38px;height:38px;border-radius:50%;background:#e8ebe4;color:#7f8875;flex-shrink:0}.pair-answer-card>div>span:last-child{font-size:12px;color:var(--muted)}.pair-answer-card strong{display:block;font-size:18px;line-height:1.6;color:var(--color-text)}.pair-answer-card>p{font-size:14px;line-height:1.85;margin:12px 0 0}.pair-pass .pair-verdict-symbol{background:#e5edf8;color:#5a80ac}.pair-pass strong{color:#42698f}.pair-fail .pair-verdict-symbol{background:#f5e7df;color:#b3745c}.pair-fail strong{color:#a7604c}@media(max-width:600px){.pair-answer-overview{grid-template-columns:1fr;gap:12px}.pair-answer-card{padding:15px}.pair-answer-card>p{font-size:14px}}
.recovery-read-note{display:block;margin-top:12px;line-height:1.7}
.case-change-choice{padding:20px;margin:0 0 24px;background:var(--color-canvas,#f5f5f2);border:1px solid var(--color-line,#ddd);border-radius:8px}.case-change-choice h4{margin:0 0 14px;font-size:16px}.recorded-choice{font-size:13px;line-height:1.7;margin:0 0 12px}.case-change-controls{display:flex;align-items:flex-end;gap:14px;flex-wrap:wrap}.case-change-controls label{flex:1;min-width:200px;max-width:390px;margin:0}.case-change-controls button{flex-shrink:0}.case-change-choice>.muted{font-size:12px;line-height:1.7;margin:12px 0 0}@media(max-width:600px){.case-change-choice{padding:16px}.case-change-controls{display:grid;gap:12px}.case-change-controls label{min-width:0;max-width:none}.case-change-controls button{width:100%}}
.change-question{font-size:14px;color:var(--muted);line-height:1.7}.change-summary{font-size:18px;margin:22px 0 10px}.saved-change-reason{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8}
.question-browser{scroll-margin-top:24px}.question-browser:focus{outline:none}.case-view-tabs{display:flex;gap:4px;border-bottom:1px solid var(--color-line,#ddd);margin:22px 0}.case-view-tabs button{background:none;border:0;border-radius:0;padding:12px 18px;font-size:14px;color:var(--muted)}.case-view-tabs button[aria-pressed="true"]{color:var(--color-text,#282b26);border-bottom:2px solid currentColor;font-weight:700}.case-question{font-size:20px;line-height:1.65;margin:24px 0 18px}.case-outcome{display:flex;gap:12px;align-items:center;margin-bottom:24px}.case-outcome strong{padding:5px 10px;background:var(--color-canvas,#f5f5f2);border-radius:6px;font-size:14px}.case-outcome span{font-size:12px;color:var(--muted)}.agent-response{white-space:normal;line-height:1.85;padding:18px;background:var(--color-canvas,#f5f5f2);border-radius:8px}.answer-reason{font-size:14px;line-height:1.85}.case-detail{margin:18px 0;font-size:14px}.case-detail summary,.evaluation-settings summary,.result-more>summary{cursor:pointer;font-weight:600}.case-detail .button-row{margin:16px 0}.case-actions{margin-top:24px}.evaluation-settings{margin:20px 0;font-size:14px}.evaluation-settings>label{margin-top:16px}.csv-download{display:flex;flex-direction:column;align-items:flex-end;gap:8px;flex-shrink:0}.csv-download small{font-size:12px;color:var(--muted)}@media(max-width:700px){.csv-download{align-items:flex-start;flex-shrink:1}.page-heading{flex-wrap:wrap}}
.saved-plan-actions{padding:20px;margin:20px 0;background:var(--color-canvas);border:1px solid var(--border);border-radius:10px}.saved-plan-actions>p{font-size:15px;line-height:1.8;margin:0 0 12px}.saved-plan-actions>.muted{font-size:14px;margin:12px 0 0}.saved-plan-actions .note p{margin:0 0 10px}@media(max-width:560px){.saved-plan-actions{padding:16px}.saved-plan-actions .button-row{align-items:stretch;flex-direction:column}.saved-plan-actions .button-row>button{justify-content:center}}
</style>

<style scoped>
.grouped-change-options{margin-top:22px}.visual-change-group{margin:0 0 24px}.change-group-heading h3{font-size:15px!important;margin:0!important}.change-group-heading p{font-size:11px!important;color:var(--muted);margin:5px 0 0!important}.visual-change-group .visual-change-options{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:12px 0}.visual-change-group .visual-change-options button{padding:13px;gap:10px;align-items:flex-start}.visual-change-group .visual-change-options button>span{min-width:0}.visual-change-group .visual-change-options strong{font-size:13px;line-height:1.6}.visual-change-group .visual-change-options small{font-size:11px}.visual-change-group em{display:inline-block;vertical-align:middle;font-style:normal;font-size:9px;padding:1px 5px;background:#e5ecde;color:#526446;border-radius:4px;margin-left:4px}.change-choice-footer{position:sticky;bottom:-24px;margin:20px -24px -24px;padding:15px 24px;background:var(--color-surface);border-top:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:12px;z-index:1}.change-choice-footer>span{font-size:11px;color:var(--muted)}.change-choice-footer .primary{font-size:12px;flex-shrink:0}@media(max-width:500px){.visual-change-group .visual-change-options{grid-template-columns:1fr}.change-choice-footer{bottom:-18px;margin-inline:-18px;margin-bottom:-18px;padding:14px 18px}.change-choice-footer>span{max-width:110px}}

.visual-run-toolbar{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:0 0 22px;font-size:12px;color:var(--muted)}.visual-run-toolbar .button-row{margin:0;gap:16px}.visual-run-toolbar .text-button{font-size:12px;min-height:30px;gap:6px}.visual-run-toolbar select{padding:4px 8px;min-height:32px;font-size:12px;max-width:130px}.visual-holdout-note{font-size:12px;color:var(--muted);margin:0 0 14px}.visual-change-options{display:grid;gap:10px;margin:20px 0}.visual-change-options button{display:flex;align-items:center;gap:16px;background:var(--color-canvas);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:left;color:var(--color-text);width:100%}.visual-change-options button[aria-pressed=true]{border-color:#7d957b;background:#eff4ed}.visual-change-options button>span{flex:1}.visual-change-options strong{font-size:14px;display:block}.visual-change-options small{font-size:12px;color:var(--muted);display:block;line-height:1.7;margin-top:5px}@media(max-width:600px){.visual-run-toolbar{margin-bottom:18px;align-items:flex-start}.visual-run-toolbar>.button-row{gap:8px;flex-wrap:wrap;justify-content:flex-end}.visual-change-options button{padding:12px}}
.saved-plan-actions{padding:20px;margin:20px 0;background:var(--color-canvas);border:1px solid var(--border);border-radius:10px}.saved-plan-actions>p{font-size:15px;line-height:1.8;margin:0 0 12px}.saved-plan-actions>.muted{font-size:14px;margin:12px 0 0}.saved-plan-actions .note p{margin:0 0 10px}@media(max-width:560px){.saved-plan-actions{padding:16px}.saved-plan-actions .button-row{align-items:stretch;flex-direction:column}.saved-plan-actions .button-row>button{justify-content:center}}
</style>

<style scoped>
.grouped-change-options{margin-top:22px}.visual-change-group{margin:0 0 24px}.change-group-heading h3{font-size:15px!important;margin:0!important}.change-group-heading p{font-size:11px!important;color:var(--muted);margin:5px 0 0!important}.visual-change-group .visual-change-options{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:12px 0}.visual-change-group .visual-change-options button{padding:13px;gap:10px;align-items:flex-start}.visual-change-group .visual-change-options button>span{min-width:0}.visual-change-group .visual-change-options strong{font-size:13px;line-height:1.6}.visual-change-group .visual-change-options small{font-size:11px}.visual-change-group em{display:inline-block;vertical-align:middle;font-style:normal;font-size:9px;padding:1px 5px;background:#e5ecde;color:#526446;border-radius:4px;margin-left:4px}.change-choice-footer{position:sticky;bottom:-24px;margin:20px -24px -24px;padding:15px 24px;background:var(--color-surface);border-top:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:12px;z-index:1}.change-choice-footer>span{font-size:11px;color:var(--muted)}.change-choice-footer .primary{font-size:12px;flex-shrink:0}@media(max-width:500px){.visual-change-group .visual-change-options{grid-template-columns:1fr}.change-choice-footer{bottom:-18px;margin-inline:-18px;margin-bottom:-18px;padding:14px 18px}.change-choice-footer>span{max-width:110px}}

.visual-improve-stages{display:flex;align-items:center;gap:18px;margin:20px 0 24px;color:#a3aa9b}.visual-improve-stages button{display:flex;gap:10px;align-items:center;border:0;background:none;padding:8px 0;color:var(--muted);font-size:13px}.visual-improve-stages button>span{display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:#ecf0e6;color:#758668}.visual-improve-stages button[aria-current=step]{color:var(--color-text);font-weight:600}.visual-improve-stages button[aria-current=step]>span{background:var(--color-primary);color:#fff}.visual-improve-stages>span{display:grid;justify-items:center;gap:10px;font-size:13px;color:var(--muted)}.visual-comparison-empty{padding:36px}.visual-comparison-empty .visual-improve-stages{gap:30px;margin:0 0 30px}.visual-comparison-empty h2{font-size:23px;margin-bottom:12px}.visual-comparison-empty p{font-size:14px;color:var(--muted);margin-bottom:24px}.visual-report-tabs{display:flex;flex-wrap:wrap;gap:22px;border-bottom:1px solid var(--border);margin-bottom:24px}.visual-report-tabs button{display:flex;gap:8px;align-items:center;border:0;border-bottom:2px solid transparent;background:none;padding:10px 0 13px;color:var(--muted);font-size:13px}.visual-report-tabs button[aria-pressed=true]{color:var(--color-text);border-color:var(--color-primary)}@media(max-width:600px){.visual-improve-stages{gap:12px}.visual-improve-stages button{font-size:12px;gap:6px}.visual-comparison-empty{padding:22px}.visual-comparison-empty .visual-improve-stages{gap:14px}.visual-report-tabs{gap:16px}.visual-report-tabs button{font-size:12px}}
.saved-plan-actions{padding:20px;margin:20px 0;background:var(--color-canvas);border:1px solid var(--border);border-radius:10px}.saved-plan-actions>p{font-size:15px;line-height:1.8;margin:0 0 12px}.saved-plan-actions>.muted{font-size:14px;margin:12px 0 0}.saved-plan-actions .note p{margin:0 0 10px}@media(max-width:560px){.saved-plan-actions{padding:16px}.saved-plan-actions .button-row{align-items:stretch;flex-direction:column}.saved-plan-actions .button-row>button{justify-content:center}}

.saved-plan-questions{margin:24px 0;padding-block:20px;border-block:1px solid var(--border)}.saved-plan-questions :deep(.question-navigator){margin:0}.saved-plan-questions :deep(.question-nav-heading strong){font-size:14px}.saved-plan-questions :deep(.question-nav-heading .text-button){font-size:14px;min-height:40px}.saved-plan-questions :deep(.question-numbers button){min-width:44px;min-height:44px;font-size:14px}.saved-plan-case{margin-top:18px}.saved-plan-case h3{font-size:18px;line-height:1.7;margin:0 0 10px}.saved-case-status{display:flex;gap:18px;flex-wrap:wrap;font-size:14px;color:var(--muted);margin:0 0 8px}.saved-plan-case>.text-button{font-size:14px;padding-left:0}.saved-drawer-question{font-size:21px;line-height:1.7;margin-bottom:18px}.saved-case-tabs{display:flex;gap:12px;margin:20px 0}.saved-case-source{padding:16px 0;border-bottom:1px solid var(--border)}.saved-case-source h4{font-size:15px;margin:0 0 10px}.saved-case-passage{white-space:pre-wrap;font-size:15px;line-height:1.85;margin:12px 0}.saved-case-tabs button{min-height:44px;font-size:14px}@media(max-width:560px){.saved-plan-case h3{font-size:17px}.saved-case-status{gap:6px 16px}}

.saved-status-legend{display:flex;gap:12px 20px;align-items:center;flex-wrap:wrap;margin-top:14px;font-size:13px}.saved-status-legend>span{display:flex;align-items:center;gap:5px}.answer-pass{color:#315f9d}.answer-fail{color:#a53e30}.answer-unknown{color:#666963}.saved-status-scope{font-size:13px;color:var(--muted);margin:8px 0 0}.saved-case-status>span{padding:4px 8px;border-radius:5px;background:var(--color-surface-subtle)}.saved-case-status>.answer-pass{background:#eef4fd}.saved-case-status>.answer-fail{background:#fbefeb}

.visual-change-option{position:relative;min-width:0}.visual-change-group .visual-change-option:only-child{grid-column:1/-1}.visual-change-group .visual-change-options .visual-change-select{height:100%;padding-inline-end:48px}.visual-change-option>.change-method-help{position:absolute;inset-inline-end:8px;bottom:8px}.saved-plan-hero{display:flex;align-items:center;justify-content:space-between;gap:24px}.saved-plan-hero>div{min-width:0;flex:1}.saved-plan-hero>svg{width:220px;flex-shrink:0}.saved-plan-hero .section-heading{margin-bottom:0}.saved-plan-hero .change-summary{margin-bottom:0}@media(max-width:600px){.saved-plan-hero{gap:10px}.saved-plan-hero>svg{width:115px}.saved-plan-hero .section-heading{flex-wrap:wrap}.saved-plan-hero h2{font-size:19px}.saved-plan-hero .change-summary{font-size:15px}}
.saved-method-summary{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
</style>
