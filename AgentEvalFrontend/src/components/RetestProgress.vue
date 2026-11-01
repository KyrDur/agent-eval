<script setup>
import {computed} from 'vue'
import {flowStages,flowTerminal} from '../retest-flow.js'
import LogConsultation from './LogConsultation.vue'
const props=defineProps({flow:Object,baseline:Object,retest:Object,change:Object,busy:Boolean})
const emit=defineEmits(['sync','resume','cancel','compare','setup'])
const trial=computed(()=>props.flow?.inputs?.execution_mode==='TRIAL')
const stageLabel=stage=>trial.value?({SUBMITTING:'正在启动本题试跑',RUNNING:'正在快速试本题',COMPLETE:'本题试跑已完成'}[stage]||flowStages[stage]):flowStages[stage]
const active=computed(()=>props.flow&&!flowTerminal.includes(props.flow.stage))
const stages=['SAVED','PREPARING','APPLYING','RUNNING','COMPARING']
const finished=computed(()=>new Set(props.flow?.events?.map(e=>e.stage)))
const completed=computed(()=>props.retest?.run.case_results?.filter(c=>c.case_latency_ms!=null).length||0)
</script>
<template>
 <section v-if="flow" class="retest-progress panel" aria-label="方案执行进度" role="status">
  <div class="section-heading"><h2>{{stageLabel(flow.stage)||'旧记录未提供执行阶段'}}</h2><span v-if="flow.run_id">{{completed}} / {{flow.confirmed_scope?.case_ids?.length??retest?.run.execution_order.length??'未知'}} 题已完成</span></div>
  <ol v-if="active||flow.stage==='FAILED'"><li v-for="s in stages.filter(s=>(s!=='PREPARING'||flow.inputs?.prepare_index)&&(s!=='COMPARING'||!trial))" :key="s" :class="{reached:finished.has(s),current:flow.stage===s}">{{stageLabel(s)}}</li></ol>
  <p v-if="flow.error" class="note warning">{{flow.error==='FLOW_RECONCILE_REQUIRED'?'连接中断后需要核对已有任务；不会自动重复提交。':flow.error==='RUN_INTERRUPTED_RESULT_UNKNOWN'?'运行中断，外部请求结果可能未知。已完成结果保留；读取不会再次调用模型。':'执行未完成，失败阶段和原始错误保留在日志中。'}} <code>{{flow.error}}</code></p>
  <p v-if="flow.stage==='PARTIAL'||flow.stage==='CANCELLED'">已完成题目保留；未完成题不计作改善。停止后已发出的请求可能仍产生用量。</p>
  <div class="button-row"><button v-if="flow.stage==='UNKNOWN'" type="button" class="primary" :disabled="busy" @click="emit('resume')">核对已有回执后继续</button><button type="button" class="secondary" :disabled="busy" @click="emit('sync')">读取已保存进度</button><button v-if="active&&!flow.cancel_requested" type="button" class="text-button" :disabled="busy" @click="emit('cancel')">停止后续任务</button><span v-if="flow.cancel_requested&&active">正在停止后续派发…</span><button v-if="flow.comparison_id" type="button" class="text-button" @click="emit('compare')">查看已保存比较 →</button></div>
  <LogConsultation compact :view="retest||baseline" :change="change" :flow="flow" label="复制执行记录问 AI" />
  <details><summary>实际阶段、任务与调用范围</summary><pre>{{JSON.stringify({confirmed_scope:flow.confirmed_scope,index_job_id:flow.index_job_id,run_id:flow.run_id,events:flow.events},null,2)}}</pre></details>
 </section>
</template>
<style scoped>.retest-progress{margin:0 0 24px}.retest-progress h2{font-size:20px}.retest-progress ol{display:flex;list-style:none;gap:12px;padding:0;margin:20px 0;flex-wrap:wrap}.retest-progress li{font-size:14px;color:var(--muted);padding:8px 12px;border:1px solid var(--border);border-radius:6px}.retest-progress li.reached{border-color:var(--color-primary);color:var(--color-text)}.retest-progress li.current{background:var(--color-success-surface);font-weight:600}.retest-progress pre{font:14px/1.8 var(--font-mono);max-height:400px;overflow:auto;white-space:pre-wrap}.retest-progress .section-heading{flex-wrap:wrap}.retest-progress .section-heading>span{font-size:14px}</style>
