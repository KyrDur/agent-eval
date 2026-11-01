<script setup>
import MarkdownContent from './MarkdownContent.vue'
import WorkspaceIcon from './WorkspaceIcon.vue'
import {computed} from 'vue'
import {questionAnswerOutcome,answerExplanation} from '../question-navigation.js'
import ScoringEvidence from './ScoringEvidence.vue'
import LogConsultation from './LogConsultation.vue'
import {trialUsesHistoricalReference,savedTrialComparison} from '../plan-trial.js'
const props=defineProps({trial:Object,baseline:Object,caseId:String,comparisonMode:Boolean})
const emit=defineEmits(['compare'])
const before=computed(()=>props.baseline?.effective_answer_results?.find(a=>a.case_id===props.caseId))
const after=computed(()=>props.trial?.view?.effective_answer_results?.find(a=>a.case_id===props.caseId))
const retrieval=computed(()=>props.trial?.view?.run.case_results.find(c=>c.case_id===props.caseId))
const historicalReference=computed(()=>trialUsesHistoricalReference(props.trial,props.baseline))
const changes=computed(()=>savedTrialComparison(props.trial,props.baseline))
const sourceSides=computed(()=>[{label:'原来提供的资料',row:props.baseline?.run.case_results.find(c=>c.case_id===props.caseId),view:props.baseline},{label:'试跑提供的资料',row:retrieval.value,view:props.trial?.view}])
const sourceTitle=(side,row)=>side.view?.run.controls?.knowledge_snapshot?.documents?.find(d=>d.document_id===row.document_id)?.title||row.document_id
const sides=computed(()=>[{key:'baseline',icon:'history',label:'原回答',view:props.baseline,answer:before.value},{key:'trial',icon:'refresh',label:'修改后',view:props.trial?.view,answer:after.value}].map(s=>({...s,outcome:questionAnswerOutcome(s.view,{case_id:props.caseId})})))
</script>
<template>
 <section v-if="trial?.view" class="plan-trial-result" aria-label="本题试跑结果" aria-live="polite">
  <div class="trial-result-heading"><h3>{{comparisonMode?'本题前后记录':'本题试跑结果'}}</h3><button v-if="!comparisonMode" type="button" class="text-button" @click="emit('compare')">查看本题变化 →</button></div><p class="trial-scope">{{historicalReference?'本次按当前程序试跑；原记录仅供参考，不能据此判定改善。':'仅试跑本题，尚未验证其他题。'}}</p>
  <p v-if="comparisonMode&&changes" class="trial-observed-change"><span>{{changes.answerChanged===true?'回答内容有变化':changes.answerChanged===false?'回答内容相同':'尚无两次完整回答'}}</span><span>资料新增 {{changes.added}} 段 · 移出 {{changes.removed}} 段</span></p>
  <div class="trial-answer-pair"><article v-for="side in sides" :key="side.label" :class="'outcome-'+side.outcome.tone"><div><span :class="['answer-side-label','answer-side-'+side.key]"><WorkspaceIcon :name="side.icon" :size="17" />{{side.label}}</span><strong>{{side.outcome.status}}</strong></div><p>{{side.answer?answerExplanation(side.answer):'本次只检查资料查找，未生成回答。'}}</p></article></div>
  <details :open="comparisonMode"><summary>查看完整回答与本次评分</summary><div class="trial-full-answers" :class="{'trial-answers-stacked':!comparisonMode}"><article v-for="side in sides" :key="side.label" :class="['trial-answer-card','answer-'+side.key]"><header class="answer-card-header"><span class="answer-card-icon"><WorkspaceIcon :name="side.icon" :size="23" /></span><h4>{{side.label}}</h4><span v-if="side.key==='baseline'" class="answer-card-stage">修改前</span></header><MarkdownContent class="trial-answer" :source="side.answer?.turn_evidence?.[0]?.response||'未保存回答'" /></article></div><ScoringEvidence v-if="after" :result="after" :retrieval="retrieval" :top-k="trial.view.run.retrieval_config.top_k" :documents="trial.view.run.controls.knowledge_snapshot.documents" /></details>
  <details v-if="comparisonMode"><summary>查看两次提供的资料</summary><div class="trial-full-answers"><section v-for="side in sourceSides" :key="side.label"><h4>{{side.label}} · {{side.row?.results?.length||0}} 段</h4><article v-for="(row,i) in side.row?.results||[]" :key="row.chunk_id||i" class="trial-source"><h5>{{i+1}}. {{sourceTitle(side,row)}}</h5><MarkdownContent :source="row.text" /></article><p v-if="!side.row?.results?.length">未保存检索资料。</p></section></div></details>
  <LogConsultation :view="trial.view" :flow="trial.flow" :case-id="caseId" :context="{原回答:before,原检索记录:baseline?.run.case_results.find(c=>c.case_id===caseId)}" label="复制本题试跑日志问 AI" log-label="本题试跑完整日志" />
 </section>
</template>
<style scoped>
.plan-trial-result{padding:20px 0;margin-top:22px;border-top:1px solid var(--border)}.plan-trial-result h3{font-size:19px;margin:0 0 8px}.trial-scope{font-size:13px;color:var(--muted);margin:0 0 16px}.trial-answer-pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}.trial-answer-pair article{padding:15px;border:1px solid #dce1d7;border-radius:9px;background:#f7f7f2;min-width:0}.trial-answer-pair article.outcome-pass{background:#edf4fb;border-color:#c6d9ea}.trial-answer-pair article.outcome-fail{background:#fbefeb;border-color:#e8c8be}.trial-answer-pair article>div{display:flex;justify-content:space-between;gap:8px;font-size:14px}.trial-answer-pair p{font-size:13px;line-height:1.85;margin:12px 0 0;overflow-wrap:anywhere}.plan-trial-result details{margin-top:16px}.trial-answer{line-height:1.9;overflow-wrap:anywhere}.plan-trial-result :deep(.log-consultation){margin-bottom:0}@media(max-width:600px){.trial-answer-pair{grid-template-columns:1fr}}
</style>
<style scoped>
.trial-full-answers.trial-answers-stacked{grid-template-columns:1fr}.trial-full-answers>.trial-answer-card{--answer-accent:#8b7658;--answer-border:#d4c8b6;--answer-band:#f1ece3;--answer-icon:#e4d9c8;padding:0;border:1px solid var(--answer-border);border-top:4px solid var(--answer-accent);border-radius:10px;background:#fff;overflow:hidden}
.trial-full-answers>.answer-trial{--answer-accent:#796297;--answer-border:#c8b9dd;--answer-band:#efe9f7;--answer-icon:#e0d3f0}
.answer-card-header{display:flex;align-items:center;gap:11px;padding:15px 18px;background:var(--answer-band);border-bottom:1px solid var(--answer-border);color:var(--answer-accent)}.answer-card-icon{display:grid;place-items:center;flex-shrink:0;width:38px;height:38px;border-radius:10px;background:var(--answer-icon)}.trial-full-answers .answer-card-header h4{margin:0;font-size:20px;line-height:1.5;font-weight:750;color:inherit}.answer-card-stage{margin-left:auto;flex-shrink:0;border:1px solid var(--answer-border);border-radius:5px;padding:3px 7px;font-size:12px;font-weight:600;background:#ffffff80}.trial-answer-card>.trial-answer{padding:20px}
.answer-side-label{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:6px;font-size:14px;font-weight:700}.answer-side-baseline{background:#f1ece3;color:#786145}.answer-side-trial{background:#efe9f7;color:#71568f}.trial-answer-pair article>div{align-items:center}
@media(max-width:700px){.answer-card-header{padding:13px 15px}.trial-full-answers .answer-card-header h4{font-size:19px}.trial-answer-card>.trial-answer{padding:16px}.answer-card-icon{width:34px;height:34px}}
</style>
<style scoped>
.trial-result-heading{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}.trial-result-heading button{font-size:14px}.trial-observed-change{display:flex;gap:12px;flex-wrap:wrap;font-size:14px;margin:14px 0}.trial-observed-change span{padding:7px 10px;background:#f0f3e9;border-radius:7px;color:#50633f}.trial-full-answers{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px;margin:16px 0}.trial-full-answers>article,.trial-full-answers>section{min-width:0;padding:16px;border:1px solid #dce1d7;border-radius:9px;background:#fafbf7}.trial-full-answers h4{font-size:15px;margin:0 0 14px}.trial-full-answers .trial-answer{font-size:14px}.trial-source{padding:12px 0;border-top:1px solid #dce1d7;font-size:14px}.trial-source h5{font-size:13px;margin:0 0 9px}@media(max-width:700px){.trial-full-answers{grid-template-columns:1fr;gap:12px}}
</style>
