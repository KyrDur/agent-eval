<script setup>
import {ref,watch} from 'vue'
import {api} from '../api.js'
const props=defineProps({comparison:Object})
const options=ref([[],[]]),selected=ref(['','']),result=ref(null),error=ref(''),loaded=ref(false)
async function load(event){
 if(!event.target.open||loaded.value)return
 try{
  const ids=[props.comparison.baseline_run_id,props.comparison.retest_run_id]
  const sides=await Promise.all(ids.map(async id=>{
   const jobs=await api.get(`/retrieval-runs/${id}/scoring-jobs`)
   const details=await Promise.all(jobs.map(j=>api.get(`/scoring-jobs/${j.job_id}`)))
   return details.flatMap(d=>d.reports)
  }))
  options.value=sides;loaded.value=true
 }catch(e){error.value=e.status===404?'当前后端尚未启用评分修订。':e.message}
}
watch(selected,async values=>{
 result.value=null;if(!values.every(Boolean))return
 try{result.value=await api.get('/score-report-comparison?'+new URLSearchParams({before_report_id:values[0],after_report_id:values[1]}))}catch(e){error.value=e.message}
},{deep:true})
const rate=s=>`${s.pass_rate.numerator}/${s.pass_rate.denominator} 题通过 · ${s.coverage.numerator}/${s.coverage.denominator} 题可判定`
</script>
<template>
 <details class="panel" @toggle="load"><summary>比较新的评分修订</summary>
  <p class="muted">分别选择报告，同一评分协议和题目范围才能比较。原比较继续使用当时封存的结果。</p>
  <label v-for="(side,index) in options" :key="index">{{index===0?'初测':'复测'}}评分报告<select v-model="selected[index]"><option value="">请选择评分修订</option><option v-for="r in side" :key="r.report_id" :value="r.report_id">{{r.created_at}} · 修订 {{r.score_revision}} · {{r.case_ids.length}} 题</option></select></label>
  <template v-if="result"><p>{{result.comparable?'所选评分版本与范围一致':'所选报告无法作同口径比较'}}</p><p v-if="result.reasons.length">{{result.reasons.map(r=>({SCORING_PROTOCOL_MISMATCH:'评分协议不同',SCORING_SCOPE_MISMATCH:'题目范围不同',SCORING_SAMPLE_MISMATCH:'题目内容或规则不同'})[r]||r).join('；')}}</p><p>初测：{{rate(result.before_summary)}}</p><p>复测：{{rate(result.after_summary)}}</p><p class="muted">仅解释这些评分修订，不能据此认定 Agent 能力提升。</p></template>
  <p v-if="loaded&&!options.some(side=>side.length)" class="muted">这两次运行还没有新的评分修订。</p><p v-if="error" role="alert">{{error}}</p>
 </details>
</template>
