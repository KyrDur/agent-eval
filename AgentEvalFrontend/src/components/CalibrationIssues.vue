<script setup>
import {computed,inject,onMounted,ref,watch} from 'vue'
import IssueCreateForm from './IssueCreateForm.vue'
import IssueProgress from './IssueProgress.vue'
const cal=inject('calibration'),work=inject('workspace'),rag=inject('retrieval'),{state}=cal
const runId=ref(''),sampleId=ref(''),error=ref('')
const runs=computed(()=>state.history.runs.filter(r=>r.dataset_id===state.dataset?.dataset_id&&r.status!=='RUNNING'))
const visibleSamples=computed(()=>state.run?.run.run_id===runId.value?state.run.results.map(r=>state.dataset.samples.find(s=>s.sample_id===r.sample_id)).filter(Boolean):[])
async function perform(fn){error.value='';try{await fn()}catch(e){error.value=e.message||'请检查输入'}}
async function refresh(){if(state.dataset)await cal.loadIssues()}
onMounted(()=>perform(refresh))
watch(()=>[state.dataset?.dataset_id,state.actor],()=>{runId.value='';sampleId.value='';perform(refresh)})
watch(()=>state.issueDraft,d=>{if(d){runId.value=d.run_id;sampleId.value=d.sample_id}},{immediate:true})
async function create(body){await perform(()=>cal.createIssue({...body,run_id:runId.value,sample_id:sampleId.value}))}
async function navigate(issue){if(issue.layer==='AGENT'){const id=issue.baseline_snapshot?.source_run_id;if(id){await rag.action('打开问题对应主实验',()=>rag.open(id));work.go('improve')}else work.state.notice='本题没有可关联的主 Agent 运行。请保存来源后新建受控实验。'}else cal.go(issue.layer==='RUBRIC'?2:6)}
</script>
<template><section class="panel"><h2>问题与修复记录</h2><p>初步原因是待验证假设。预先声明验收条件，再区分复测完成、确已修复、误报澄清和暂不修复。</p><p v-if="error" role="alert" class="note danger">{{error}}</p><p v-if="!state.dataset" class="empty">先选择样本集，或从主实验逐题结果直接建立问题。</p><template v-else><label>问题来源运行<select v-model="runId" @change="sampleId=''"><option value="">选择已完成运行</option><option v-for="r in runs" :key="r.run_id" :value="r.run_id">{{r.run_id.slice(0,8)}} · {{r.partition}} · {{r.status}}</option></select></label><button class="secondary" :disabled="!runId||!!work.state.busy" @click="perform(()=>cal.loadRun(runId))">读取可查看的题目</button><label>关联问题<select v-model="sampleId"><option value="">先读取运行，再选择已提交标注的题目</option><option v-for="s in visibleSamples" :key="s.sample_id" :value="s.sample_id">{{s.question}}</option></select></label><IssueCreateForm :sample-id="sampleId" :initial-title="state.issueDraft?.title||''" :disabled="!!work.state.busy" @create="create" /></template></section><IssueProgress v-for="item in state.issues" :key="item.issue.issue_id" :item="item" :runs="[...runs,...rag.state.history]" :disabled="!!work.state.busy" @update="body=>perform(()=>cal.updateIssue(item.issue.issue_id,body))" @navigate="navigate"/><p v-if="state.dataset&&!state.issues.length" class="empty">还没有此查看者可见的问题；先完成对应题目的标注才能查看机器结果。</p></template>
