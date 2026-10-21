<script setup>
import {computed,nextTick,ref,watch} from 'vue'
import {diagnoseCase,elapsed,operationNames,statusNames,tokenSummary} from '../run-diagnostics.js'
import {traceSteps,preferredTraceStep,traceErrorText} from '../trace-view.js'
import TraceCall from './TraceCall.vue'
import TraceCandidates from './TraceCandidates.vue'
const props=defineProps({retrieval:Object,answer:Object,observations:Array,verifyAnswers:Boolean,latencyMs:Number,mode:{type:String,default:'evaluation'},title:{type:String,default:'运行诊断'},expanded:Boolean})
const opened=ref(props.expanded),activeOperation=ref(''),attempt=ref(0),candidateView=ref('returned'),notice=ref(''),stageRail=ref(null)
watch(()=>props.expanded,value=>{opened.value=value})
const row=computed(()=>props.retrieval||{})
const calls=computed(()=>props.observations||row.value.provider_call_traces||row.value.provider_observations||[])
const diagnosis=computed(()=>diagnoseCase(row.value,props.answer,props.verifyAnswers,props.mode))
const tokens=computed(()=>tokenSummary(calls.value,!!row.value.diagnostic_version))
const steps=computed(()=>traceSteps(row.value,props.answer,calls.value,props.verifyAnswers))
const duration=computed(()=>props.latencyMs??row.value.case_latency_ms)
const selected=computed(()=>steps.value.find(step=>step.operation===activeOperation.value)||steps.value[0])
const currentCall=computed(()=>{const call=selected.value?.calls[attempt.value]||selected.value?.calls[0];const issues=props.answer?.evidence_evaluation?.validation_issues;return call&&selected.value?.operation==='JUDGE'&&Array.isArray(issues)?{...call,validation_issues:issues}:call})
const candidates=computed(()=>candidateView.value==='pre'?row.value.pre_rerank_results||[]:candidateView.value==='post'?row.value.post_rerank_results||[]:row.value.results||[])
watch(()=>[props.retrieval,props.answer],()=>{activeOperation.value=preferredTraceStep(steps.value);attempt.value=0;notice.value=''},{immediate:true})
watch([activeOperation,opened],async([value])=>{attempt.value=0;candidateView.value=value==='RERANK'?'post':'returned';await nextTick();const rail=stageRail.value,button=rail?.querySelector('[aria-pressed="true"]');if(rail&&button&&rail.scrollWidth>rail.clientWidth)rail.scrollTo({left:rail.scrollLeft+button.getBoundingClientRect().left-rail.getBoundingClientRect().left-(rail.clientWidth-button.clientWidth)/2})},{immediate:true})
const logData=computed(()=>({case_id:row.value.case_id||props.answer?.case_id||null,query:row.value.query||null,retrieval:row.value,answer:props.answer||null,model_calls:calls.value}))
function download(){const file=new Blob([JSON.stringify(logData.value,null,2)],{type:'application/json;charset=utf-8'}),url=URL.createObjectURL(file),a=document.createElement('a');a.href=url;a.download=`run-log-${String(row.value.case_id||'case').replace(/[^a-zA-Z0-9_-]/g,'_')}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice.value='已下载本题保存的日志。'}
async function copy(){try{await navigator.clipboard.writeText(JSON.stringify(logData.value,null,2));notice.value='本题日志已复制。'}catch{notice.value='复制未完成，可以下载 JSON 查看。'}}
</script>
<template>
 <section class="run-diagnostics" :class="diagnosis.tone" aria-label="运行诊断" data-testid="run-diagnostics">
  <div class="diagnostic-heading"><div><h4>{{title}}</h4><p>{{diagnosis.title}}</p></div><div class="log-actions"><button type="button" class="text-button" @click="download">下载日志 JSON</button><button type="button" class="text-button" @click="copy">复制日志</button></div></div>
  <dl class="diagnostic-summary"><div><dt>{{duration!=null?'本题总耗时':'检索总耗时'}}</dt><dd>{{elapsed(duration??row.latency_ms)}}</dd></div><div><dt>模型调用</dt><dd>{{calls.length||row.diagnostic_version?`${calls.length} 次`:'历史未记录'}}</dd></div><div><dt>Token</dt><dd>{{tokens.text}}</dd></div></dl>
  <p v-if="notice" class="log-notice" role="status">{{notice}}</p>
  <details class="diagnostic-process" :open="opened" @toggle="opened=$event.target.open">
   <summary>查看调用链与每步输入输出</summary>
   <div v-if="opened" class="trace-workbench">
    <nav ref="stageRail" class="trace-stages" aria-label="日志步骤"><button v-for="(step,i) in steps" :key="step.operation" type="button" :aria-label="operationNames[step.operation]||step.operation" :aria-pressed="selected?.operation===step.operation" :class="[step.status.toLowerCase(),{active:selected?.operation===step.operation}]" @click="activeOperation=step.operation"><span class="step-number">{{i+1}}</span><span class="step-name">{{operationNames[step.operation]||step.operation}}<small>{{statusNames[step.status]||step.status}}<template v-if="step.status!=='SKIPPED'&&step.latency_ms!=null"> · {{elapsed(step.latency_ms)}}</template></small></span><span v-if="step.calls.length" class="step-call-count">{{step.calls.length}} 次</span></button></nav>
    <section v-if="selected" class="trace-stage-detail" :aria-label="(operationNames[selected.operation]||selected.operation)+'详情'">
     <div class="stage-title"><h5>{{operationNames[selected.operation]||selected.operation}}</h5><span>{{statusNames[selected.status]||selected.status}}</span></div>
     <div v-if="selected.error" class="stage-error" role="note"><strong>{{traceErrorText(selected.error)}}</strong><code>{{selected.error}}</code></div>
     <p v-if="selected.status==='SKIPPED'" class="stage-empty">本次没有开启此步骤。</p><p v-else-if="selected.status==='NOT_RUN'" class="stage-empty">本步骤没有执行，可查看前面失败的步骤。</p>
     <template v-else-if="selected.operation==='RETRIEVAL'">
      <dl class="retrieval-facts"><div><dt>查找数量</dt><dd>取前 {{row.top_k??'未记录'}} 条</dd></div><div><dt>候选 / 返回</dt><dd>{{row.pre_rerank_results?.length??'未记录'}} / {{row.results?.length??'未记录'}}</dd></div><div><dt>执行方式</dt><dd>本地检索</dd></div></dl>
      <h6>检索输入</h6><p class="query-text">{{row.effective_query||'未保存实际检索查询'}}</p><details v-if="row.query!==row.effective_query"><summary>原始问题</summary><p class="query-text">{{row.query||'未记录'}}</p></details>
      <div class="candidate-views" role="group" aria-label="检索资料范围"><button type="button" :aria-pressed="candidateView==='returned'" @click="candidateView='returned'">最终选中的参考资料</button><button type="button" :aria-pressed="candidateView==='pre'" @click="candidateView='pre'">全部检索候选</button></div>
      <p class="trace-empty">“选为回答参考”表示这是检索最终选中的资料；生成回答时会随问题一起提供给模型，不代表模型一定采用或答对。</p>
      <TraceCandidates :items="candidates" :returned="row.results" :relevant-ids="[...row.relevant_document_ids||[],...row.relevant_chunk_ids||[]]" />
      <details><summary>索引与原始记录</summary><pre>{{JSON.stringify({index_id:row.index_id,top_k:row.top_k,steps:row.steps,pre_rerank_results:row.pre_rerank_results},null,2)}}</pre></details>
     </template>
     <template v-else>
      <div v-if="selected.operation==='QUERY_REWRITE'" class="query-change"><h6>改写前</h6><p class="query-text">{{row.query}}</p><h6>改写后</h6><p class="query-text">{{row.effective_query||'未形成有效查询'}}</p></div>
      <div v-if="selected.calls.length>1" class="call-selector"><label>查看哪次调用<select v-model.number="attempt"><option v-for="(call,i) in selected.calls" :key="call.call_id||i" :value="i">第 {{call.request_number}} 次 · {{call.status==='FAILED'?'请求失败':'已返回'}}</option></select></label></div>
      <TraceCall v-if="currentCall" :key="currentCall.call_id||selected.operation+attempt" :call="currentCall" :step-status="selected.status" :stage-error="selected.error" />
      <p v-else class="stage-empty">{{row.diagnostic_version?'本步骤没有保存模型调用，可查看原始记录。':'这条历史记录没有保存模型输入输出。'}}</p>
      <details v-if="selected.operation==='RERANK'" class="ranking-details"><summary>重排前后的资料顺序</summary><div class="candidate-views" role="group" aria-label="排序资料范围"><button type="button" :aria-pressed="candidateView==='pre'" @click="candidateView='pre'">重排前</button><button type="button" :aria-pressed="candidateView==='post'" @click="candidateView='post'">重排后</button></div><TraceCandidates :items="candidates" :returned="row.results" :relevant-ids="[...row.relevant_document_ids||[],...row.relevant_chunk_ids||[]]" /></details>
     </template>
    </section>
   </div>
  </details>
 </section>
</template>
<style scoped>
.run-diagnostics{border:1px solid var(--color-line,#ddd);border-radius:12px;padding:20px;margin:18px 0;min-width:0;background:var(--color-surface,#fff)}.diagnostic-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.diagnostic-heading h4{margin:0;font-size:15px}.diagnostic-heading p{margin:8px 0 0;font-size:12px;color:var(--muted)}.log-actions{display:flex;gap:12px;flex-shrink:0}.log-actions button{font-size:11px;padding:0}.diagnostic-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:20px 0}.diagnostic-summary dt{font-size:11px;color:var(--muted)}.diagnostic-summary dd{margin:7px 0 0;font-size:15px;font-weight:600;overflow-wrap:anywhere}.diagnostic-process>summary{font-size:13px;font-weight:600;cursor:pointer}.trace-workbench{display:grid;grid-template-columns:174px minmax(0,1fr);margin-top:20px;border-top:1px solid var(--color-line,#ddd);padding-top:20px;gap:20px}.trace-stages{display:grid;align-content:start;gap:6px}.trace-stages>button{display:flex;align-items:center;gap:9px;text-align:left;background:transparent;border:1px solid transparent;border-radius:7px;padding:10px 8px;font-size:12px;min-width:0;color:var(--ink)}.trace-stages>button.active{background:var(--color-canvas,#f5f5f2);border-color:var(--color-line,#ddd)}.step-number{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border:1px solid var(--color-line,#ddd);border-radius:50%;font-size:10px;flex-shrink:0}.trace-stages .failed .step-number{border-color:#bb6f64;color:#aa4033}.step-name{flex:1;line-height:1.6;min-width:0}.step-name small{display:block;color:var(--muted);font-size:10px;font-weight:400}.step-call-count{font-size:10px;color:var(--muted);white-space:nowrap}.trace-stages .skipped{opacity:.65}.trace-stage-detail{border-left:1px solid var(--color-line,#ddd);padding-left:20px;min-width:0;font-size:13px}.stage-title{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px}.stage-title h5{margin:0;font-size:15px}.stage-title>span{font-size:11px;color:var(--muted)}.stage-error{padding:12px;background:#fdf0ed;border-radius:6px;color:#983c31;font-size:12px;margin-bottom:18px;line-height:1.7}.stage-error code{display:block;font-size:10px;margin-top:5px;overflow-wrap:anywhere}.stage-empty,.log-notice{font-size:12px;color:var(--muted);line-height:1.8}.retrieval-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0 0 20px}.retrieval-facts dt{font-size:11px;color:var(--muted)}.retrieval-facts dd{font-size:12px;margin:6px 0 0;overflow-wrap:anywhere}.trace-stage-detail h6{font-size:12px;margin:18px 0 8px}.query-text{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.8;background:var(--color-canvas,#f5f5f2);padding:12px;border-radius:6px}.trace-stage-detail details{margin-top:16px;font-size:12px}.trace-stage-detail summary{cursor:pointer}.trace-stage-detail pre{font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;max-height:400px;overflow:auto}.candidate-views{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 10px}.candidate-views button{border:1px solid var(--color-line,#ddd);border-radius:5px;background:none;padding:6px 9px;font-size:11px}.candidate-views button[aria-pressed=true]{background:var(--color-canvas,#f5f5f2);font-weight:700}.call-selector{margin-bottom:16px}.call-selector label{font-size:12px}.call-selector select{font-size:12px;margin-top:7px}
@media(max-width:1050px){.trace-workbench{grid-template-columns:1fr}.trace-stages{display:flex;overflow-x:auto;padding-bottom:8px;gap:8px}.trace-stages>button{flex:0 0 130px}.trace-stage-detail{border-left:0;border-top:1px solid var(--color-line,#ddd);padding:18px 0 0}}@media(max-width:600px){.run-diagnostics{padding:14px}.diagnostic-heading{flex-wrap:wrap}.log-actions{gap:18px}.trace-stages>button{flex-basis:120px}.retrieval-facts{grid-template-columns:1fr 1fr}.diagnostic-summary{gap:8px}}
</style>
