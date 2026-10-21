<script setup>
import {computed,inject,ref,watch} from 'vue'
import {api} from '../api.js'
import IssueCreateForm from './IssueCreateForm.vue'
import IssueProgress from './IssueProgress.vue'
const props=defineProps({runId:String,caseId:String,comparisonId:String,reviewId:String})
const work=inject('workspace'),cal=inject('calibration'),rag=inject('retrieval'),open=ref(false),source=ref(null),items=ref([]),error=ref(''),busy=ref(false),runs=ref([])
const sourceType=computed(()=>props.reviewId?'RETRIEVAL_REVIEW':props.comparisonId?'RETRIEVAL_COMPARISON':'RETRIEVAL_RUN')
async function load(){source.value=await api.get(`/calibration/issue-sources/${props.runId}?case_id=${encodeURIComponent(props.caseId)}&actor=${encodeURIComponent(cal.state.actor)}&source_type=${sourceType.value}`+((props.reviewId||props.comparisonId)?`&source_id=${encodeURIComponent(props.reviewId||props.comparisonId)}`:''));items.value=(await api.get(`/calibration/issues?run_id=${props.runId}&actor=${encodeURIComponent(cal.state.actor)}`)).filter(v=>v.issue.sample_id===props.caseId);const h=await api.get('/calibration/history');runs.value=[...h.runs,...(await api.get('/retrieval-history'))];if(props.comparisonId){const validations=await api.get('/retrieval-validations?comparison_id='+props.comparisonId);runs.value.push(...validations.filter(v=>v.status==='COMPLETE'&&v.released_at).map(v=>({run_id:v.validation_id,status:v.status,run_type:'已解封保留验证'})))}}
async function perform(fn){busy.value=true;error.value='';try{await fn()}catch(e){error.value=e.message||'读取失败，请重试。'}finally{busy.value=false}}
watch([open,()=>props.runId,()=>props.caseId],()=>{if(open.value)perform(load)})
async function create(body){await perform(async()=>{await api.post('/calibration/issues',{...body,dataset_id:source.value.dataset_id,run_id:props.runId,sample_id:props.caseId,actor:cal.state.actor,source_type:sourceType.value,source_id:props.reviewId||props.comparisonId||null});await load()})}
async function update(item,body){await perform(async()=>{await api.post(`/calibration/issues/${item.issue.issue_id}/events`,{...body,actor:cal.state.actor});await load()})}
async function navigate(issue){if(issue.layer==='AGENT'){await rag.action('打开问题对应的主实验',()=>rag.open(issue.run_id));work.go('improve')}else{cal.queue(issue.run_id,issue.sample_id);work.go('calibration')}}
</script>
<template><details class="retrieval-issue-panel" :open="open" @toggle="open=$event.target.open"><summary>记录问题、假设与修复验收 · {{items.length}}</summary><p class="muted">先核对判定和证据，再选择数据、Judge、标准或 Agent。允许多个候选原因和暂时无法定位。</p><p v-if="error" class="note danger" role="alert">{{error}}</p><p v-if="busy" role="status">正在读取问题证据…</p><IssueCreateForm v-if="source" :sample-id="caseId" :disabled="busy" @create="create"/><IssueProgress v-for="item in items" :key="item.issue.issue_id" :item="item" :runs="runs" :disabled="busy" @update="body=>update(item,body)" @navigate="navigate" /></details></template>
<style scoped>.retrieval-issue-panel{margin:16px 0;padding:14px;border:1px solid var(--border,#ddd);border-radius:10px;overflow-wrap:anywhere}summary{cursor:pointer}</style>
