<script setup>
import {computed,inject,onBeforeUnmount,ref,watch} from 'vue'
import {api} from '../api.js'
import ScoringEvidence from './ScoringEvidence.vue'
import TraceCall from './TraceCall.vue'
import EvaluationLogExport from './EvaluationLogExport.vue'
const props=defineProps({view:Object,caseId:String})
const work=inject('workspace'),available=ref(false),jobs=ref([]),detail=ref(null),preview=ref(null),busy=ref(false),error=ref(''),pending=ref(null),revision=ref('')
let timer=null,generation=0
const session=computed(()=>work.state.session)
const ready=computed(()=>session.value?.credential_status==='PRESENT'&&session.value?.text_connection_status==='READY')
const reports=computed(()=>detail.value?.reports||[])
const report=computed(()=>reports.value.find(r=>r.report_id===revision.value)||detail.value?.report)
const adopted=computed(()=>report.value?.adoption_manifest.find(r=>r.case_id===props.caseId))
const result=computed(()=>adopted.value?{scoring_protocol:{calibration_status:'INITIAL_UNVALIDATED'},evidence_evaluation:adopted.value.result}:null)
const attempts=computed(()=>(detail.value?.events||[]).filter(e=>e.case_id===props.caseId&&e.phase!=='STARTED').sort((a,b)=>a.number-b.number))
const active=computed(()=>detail.value&&['QUEUED','RUNNING'].includes(detail.value.job.status)&&!detail.value.interrupted)
const eligible=computed(()=>props.view?.run.controls.scoring_profile&&props.view?.effective_answer_results.some(a=>a.case_id===props.caseId&&a.execution_status==='SUCCESS'))
const labels={PASS:'通过',FAIL:'不通过',EVIDENCE_INSUFFICIENT:'资料不足',EXECUTION_FAILED:'评分失败',NOT_RUN:'待评分'}
async function readJob(id,token=generation){
 const value=await api.get(`/scoring-jobs/${encodeURIComponent(id)}`)
 if(token!==generation)return
 detail.value=value
 if(['QUEUED','RUNNING'].includes(value.job.status)&&!value.interrupted)timer=setTimeout(()=>readJob(id,token).catch(e=>{if(token===generation)error.value=e.message}),1200)
}
async function chooseJob(event){clearTimeout(timer);generation++;revision.value='';detail.value=null;try{await readJob(event.target.value)}catch(e){error.value=e.message}}
async function load(){
 const token=++generation;clearTimeout(timer);detail.value=null;preview.value=null;error.value='';pending.value=null;revision.value=''
 if(!props.view?.run.run_id||!props.caseId)return
 try{
  await api.get('/judge-contract');if(token!==generation)return;available.value=true
  const history=await api.get(`/retrieval-runs/${encodeURIComponent(props.view.run.run_id)}/scoring-jobs`)
  if(token!==generation)return
  jobs.value=history.filter(j=>j.case_ids.includes(props.caseId)).sort((a,b)=>a.created_at.localeCompare(b.created_at))
  if(jobs.value.length)await readJob(jobs.value.at(-1).job_id,token)
 }catch(e){if(token===generation){if(e.status===404)available.value=false;else error.value=e.message}}
}
watch(()=>[props.view?.run.run_id,props.caseId],load,{immediate:true})
onBeforeUnmount(()=>{generation++;clearTimeout(timer)})
async function prepare(){busy.value=true;error.value='';try{preview.value=await api.post(`/retrieval-runs/${props.view.run.run_id}/scoring-preview`,{case_ids:[props.caseId],provider_session_id:session.value.provider_session_id,max_attempts:2});pending.value=null}catch(e){error.value=e.message}finally{busy.value=false}}
async function start(){
 if(busy.value||!preview.value)return
 busy.value=true;error.value=''
 const p=preview.value
 if(!pending.value)pending.value={request_id:crypto.randomUUID(),case_ids:[props.caseId],provider_session_id:session.value.provider_session_id,max_attempts:2,protocol_hash:p.protocol_hash,request_budget:p.maximum_requests,token_budget:p.maximum_requests*p.token_reservation_per_attempt}
 try{detail.value=await api.post(`/retrieval-runs/${props.view.run.run_id}/scoring-jobs`,pending.value);if(!jobs.value.some(j=>j.job_id===detail.value.job.job_id))jobs.value.push(detail.value.job);preview.value=null;await readJob(detail.value.job.job_id)}catch(e){error.value=e.message}finally{busy.value=false}
}
async function resume(){busy.value=true;error.value='';try{detail.value=await api.post(`/scoring-jobs/${detail.value.job.job_id}/resume`);await readJob(detail.value.job.job_id)}catch(e){error.value=e.message}finally{busy.value=false}}
async function download(){try{const file=await api.download(`/score-reports/${report.value.report_id}/export`);const url=URL.createObjectURL(file.blob),a=document.createElement('a');a.href=url;a.download=file.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){error.value=e.message}}
</script>
<template>
 <section v-if="available&&eligible" class="score-recovery" aria-label="单题评分恢复">
  <p class="muted">可使用已保存的回答和资料重新评分。原报告保留，新结果单独统计。</p>
  <button v-if="!preview" type="button" class="secondary" :disabled="!ready||busy||active" @click="prepare">仅重评这一题</button>
  <div v-if="preview" class="note"><p>最多 {{preview.maximum_requests}} 次评分请求。格式或临时网络错误最多恢复一次；有效的不通过结果会直接停止。</p><p>采用新版评分协议，仅统计本题。Agent 回答与检索保持本次封存内容。</p><details><summary>协议与预算</summary><p>协议 {{preview.protocol_hash}}</p><p>输出方式 {{preview.protocol.output_mode}} · 总 Token 预留上限 {{preview.maximum_requests*preview.token_reservation_per_attempt}} · 费用以模型服务账单为准</p></details><div class="button-row"><button type="button" class="primary" :disabled="busy" @click="start">开始评分</button><button type="button" class="secondary" :disabled="busy" @click="preview=null">取消</button></div></div>
  <p v-if="active" role="status">正在评分，刷新只会读取已保存的进度。</p>
  <p v-if="detail?.interrupted" class="note">评分进程已中断。恢复会跳过已完成题；发送情况未知的请求会保留为未知。</p>
  <button v-if="detail?.interrupted" type="button" class="secondary" :disabled="busy" @click="resume">恢复未完成任务</button>
  <p v-if="detail?.job.last_error" class="note">{{detail.job.last_error}}</p>
  <label v-if="jobs.length>1">评分任务<select :value="detail?.job.job_id" :disabled="busy" @change="chooseJob"><option v-for="j in jobs" :key="j.job_id" :value="j.job_id">{{j.created_at}} · {{j.status}}</option></select></label>
  <template v-if="report">
   <label>评分修订<select v-model="revision"><option value="">最近修订</option><option v-for="r in reports" :key="r.report_id" :value="r.report_id">修订 {{r.score_revision}}</option></select></label>
   <p><strong>新协议 · {{labels[adopted?.evaluation_state]||'待评分'}}</strong> · 形成判定 {{report.summary.coverage.numerator}}/{{report.summary.coverage.denominator}} 题 · 通过 {{report.summary.pass_rate.numerator}}/{{report.summary.pass_rate.denominator}} 题</p>
   <p class="muted">仅限本协议所选题目；评分变化不代表 Agent 能力提升。</p>
   <ScoringEvidence :result="result" /><button type="button" class="secondary" @click="download">下载本修订 CSV</button>
   <details><summary>历次评分尝试 · {{attempts.length}} 次</summary><article v-for="attempt in attempts" :key="attempt.attempt_id"><h5>第 {{attempt.number}} 次 · {{attempt.result?.error||attempt.result?.judgment?.verdict||attempt.phase}}</h5><p v-for="(i,index) in attempt.result?.validation_issues||[]" :key="index"><code>{{i.field_path}}</code> · {{i.code}} · 实际值 {{JSON.stringify(i.actual)}}</p><TraceCall v-for="(call,index) in attempt.traces" :key="call.call_id" :call="{...call,request_number:index+1,validation_issues:attempt.result?.validation_issues}" :step-status="attempt.result?.status==='SUCCESS'?'SUCCESS':'FAILED'" /></article></details>
   <details><summary>复制这份评分修订的日志</summary><EvaluationLogExport :key="report.report_id" :view="view" :score-report="report" /></details>
  </template>
  <p v-if="error" class="note danger" role="alert">{{error}}</p>
 </section>
</template>
<style scoped>
.score-recovery{padding:16px 0;border-top:1px solid var(--color-line,#ddd);margin-top:20px;overflow-wrap:anywhere}.score-recovery details{margin-top:16px}.score-recovery article{padding:12px 0;border-top:1px solid var(--color-line,#ddd)}.score-recovery select{max-width:100%}
</style>
