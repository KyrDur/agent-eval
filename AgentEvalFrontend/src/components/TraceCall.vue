<script setup>
import {computed,ref,watch} from 'vue'
import {callOperation,callUsage,elapsed} from '../run-diagnostics.js'
import {requestPayload,responseText,parseSavedJson,judgeFormatIssues,traceDimensionNames} from '../trace-view.js'
const props=defineProps({call:{type:Object,required:true},stepStatus:String,stageError:String})
const tab=ref('output')
watch(()=>props.call.call_id,()=>{tab.value='output'})
const payload=computed(()=>requestPayload(props.call))
const text=computed(()=>responseText(props.call))
const parsed=computed(()=>parseSavedJson(text.value))
const usage=computed(()=>callUsage(props.call))
const isJudge=computed(()=>callOperation(props.call)==='JUDGE')
const formatIssues=computed(()=>isJudge.value&&props.stepStatus==='FAILED'?judgeFormatIssues(props.call):[])
const fragments=computed(()=>Array.isArray(payload.value?.sample?.fragment_catalog)?payload.value.sample.fragment_catalog:[])
const messages=computed(()=>Array.isArray(props.call.model_inputs?.messages)?props.call.model_inputs.messages:[])
const rawCall=computed(()=>{const {request_number,...saved}=props.call;return saved})
const sources=[['ANSWER','被评分的回答'],['RETRIEVED','Agent 查到的资料'],['REFERENCE','评分用的参考政策']]
const stringify=value=>JSON.stringify(value,null,2)
const contentText=value=>typeof value==='string'?value:JSON.stringify(value,null,2)
const scoreText=value=>({0:'不符合（0）',1:'部分符合（1）',2:'符合（2）',NA:'不适用（NA）',INSUFFICIENT:'资料不足'})[value]||(value===null?'格式错误：null':'未记录')
</script>
<template>
 <section class="trace-call" aria-label="模型调用详情">
  <div class="trace-request-heading"><strong>第 {{call.request_number}} 次模型调用</strong><span :class="call.status==='FAILED'?'failed':'returned'">{{call.status==='SUCCESS'?'请求已返回':call.status==='FAILED'?'请求失败':'返回状态未记录'}}</span></div>
  <dl class="call-facts"><div><dt>模型</dt><dd>{{call.requested_model||'未记录'}}</dd></div><div><dt>调用耗时</dt><dd>{{elapsed(call.latency_ms)}}</dd></div><div><dt>输入 / 输出 Token</dt><dd>{{usage?`${usage.input} / ${usage.output}`:'未返回'}}</dd></div></dl>
  <p v-if="call.status==='SUCCESS'&&stepStatus==='FAILED'" class="call-state-note">模型已返回内容，后续处理未通过。下方保留返回正文和格式问题。</p>
  <p v-if="call.input_truncated||call.output_truncated||call.content_redacted" class="snapshot-note">{{call.content_redacted?'凭据信息已隐藏。 ':''}}{{call.input_truncated?'保存的输入快照已截取。 ':''}}{{call.output_truncated?'保存的输出快照已截取，无法核对完整返回。':''}}</p>
  <div class="call-tabs" role="group" aria-label="调用内容"><button type="button" :aria-pressed="tab==='input'" @click="tab='input'">输入</button><button type="button" :aria-pressed="tab==='output'" @click="tab='output'">输出</button><button type="button" :aria-pressed="tab==='raw'" @click="tab='raw'">原始记录</button></div>
  <div v-if="tab==='input'" class="call-content" role="region" aria-label="模型输入">
   <template v-if="payload?.sample">
    <h5>评分问题</h5><p class="saved-text">{{payload.sample.question}}</p>
    <p class="snapshot-note">评分规则：{{payload.rubric?.name||'见原始记录'}} · 参考覆盖：{{payload.sample.reference_complete===true?'已确认':payload.sample.reference_complete===false?'已知不完整':'未确认'}}</p>
    <details v-if="payload.rubric"><summary>本次评分规则</summary><pre>{{stringify(payload.rubric)}}</pre></details>
    <details v-for="[scope,label] in sources" :key="scope" :open="scope==='ANSWER'"><summary>{{label}} · {{fragments.filter(f=>f.scope===scope).length}} 段</summary><article v-for="f in fragments.filter(f=>f.scope===scope)" :key="f.fragment_id" class="input-fragment"><strong>{{f.fragment_id}}</strong><p class="saved-text">{{f.text}}</p></article></details>
   </template>
   <template v-else-if="payload?.query">
    <h5>问题</h5><p class="saved-text">{{payload.query}}</p>
    <details v-if="Array.isArray(payload.retrieved_knowledge)" open><summary>交给模型的资料 · {{payload.retrieved_knowledge.length}} 条</summary><article v-for="(item,i) in payload.retrieved_knowledge" :key="item.chunk_id||i" class="input-fragment"><strong>{{item.document_id||`资料 ${i+1}`}}</strong><p class="saved-text">{{item.text}}</p></article></details>
    <details v-if="payload.conversation_history?.length"><summary>对话上下文 · {{payload.conversation_history.length}} 条</summary><p v-for="(m,i) in payload.conversation_history" :key="i" class="saved-text">{{m.role}}：{{contentText(m.content)}}</p></details>
    <details><summary>完整上下文</summary><pre>{{stringify(payload)}}</pre></details>
   </template>
   <template v-else><article v-for="(message,i) in messages" :key="i" class="input-fragment"><strong>{{message.role}}</strong><pre>{{contentText(message.content)}}</pre></article><p v-if="!messages.length" class="snapshot-note">本次记录未保存输入上下文。</p></template>
   <details v-if="call.model_inputs?.system"><summary>系统提示词</summary><pre>{{call.model_inputs.system}}</pre></details>
   <details><summary>推理参数与输入预算</summary><pre>{{stringify({model:call.model_inputs?.model,temperature:call.model_inputs?.temperature,max_tokens:call.model_inputs?.max_tokens,input_budget:call.input_budget})}}</pre></details>
  </div>
  <div v-else-if="tab==='output'" class="call-content" role="region" aria-label="模型输出">
   <div v-if="formatIssues.length" class="format-issues" role="note"><strong>{{formatIssues[0].source==='BACKEND'?'服务端评分校验问题':'保存返回的只读辅助检查'}}</strong><div v-for="issue in formatIssues" :key="issue.path"><code>{{issue.path}}</code><p>{{issue.message}}</p></div></div>
   <template v-if="isJudge&&parsed?.dimensions">
    <h5>{{stepStatus==='FAILED'?'评分未采用，模型返回如下':'模型返回的逐项评分'}}</h5><details v-for="(value,key) in parsed.dimensions" :key="key"><summary>{{traceDimensionNames[key]||key}} · {{scoreText(value?.score)}}</summary><p class="saved-text">{{value?.reason}}</p><p class="snapshot-note">回答片段：{{value?.answer_fragment_ids?.join('、')||'未记录'}} · 资料片段：{{value?.evidence_fragment_ids?.join('、')||'未记录'}}</p></details>
    <p class="saved-text">{{parsed.reason}}</p><p class="snapshot-note">以上是模型返回值，本题最终判定见评测结果。</p>
    <details><summary>查看返回正文</summary><pre>{{stringify(parsed)}}</pre></details>
   </template>
   <template v-else><h5>返回正文</h5><pre v-if="text">{{parsed?stringify(parsed):text}}</pre><p v-else class="snapshot-note">{{call.status==='FAILED'?'请求失败，没有返回正文。':'本条记录未保存返回正文。'}}</p></template>
   <p v-if="call.error" class="call-error">调用错误：{{call.error}}</p>
   <p class="snapshot-note">结束原因：{{call.model_outputs?.stop_reason||'未记录'}}<template v-if="call.response_model_identifier"> · 返回模型：{{call.response_model_identifier}}</template></p>
  </div>
  <div v-else class="call-content" role="region" aria-label="模型原始记录"><h5>保存的调用记录</h5><pre>{{stringify(rawCall)}}</pre></div>
  <details class="call-identifiers"><summary>调用标识</summary><p>调用 ID：{{call.call_id||'未记录'}}</p><p>响应 ID：{{call.response_identifier||'未记录'}}</p></details>
 </section>
</template>
<style scoped>
.trace-call{min-width:0}.trace-request-heading{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;font-size:13px}.returned{color:#376448}.failed,.call-error{color:#a13c32}.call-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:18px 0}.call-facts dt{font-size:11px;color:var(--muted)}.call-facts dd{font-size:13px;margin:6px 0 0;overflow-wrap:anywhere}.call-tabs{display:flex;gap:16px;border-bottom:1px solid var(--color-line,#ddd);margin:20px 0 12px}.call-tabs button{border:0;background:none;border-radius:0;padding:9px 2px;color:var(--muted);font-size:13px}.call-tabs button[aria-pressed=true]{color:var(--ink);font-weight:700;border-bottom:2px solid currentColor}.call-content{min-width:0;font-size:13px;overflow-wrap:anywhere}.call-content h5{font-size:13px;margin:18px 0 10px}.call-content details{margin:14px 0}.call-content summary{cursor:pointer;font-size:13px;line-height:1.7}.saved-text{white-space:pre-wrap;line-height:1.85;overflow-wrap:anywhere}.input-fragment{border-left:2px solid var(--color-line,#ddd);padding:8px 12px;margin:12px 0}.input-fragment>strong{font-size:12px}.snapshot-note,.call-state-note{font-size:12px;line-height:1.7;color:var(--muted)}.call-state-note{padding:10px 12px;background:#fbf4e7;border-radius:6px;color:#80601e}.call-content pre{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;background:var(--color-canvas,#f5f5f2);padding:14px;border-radius:6px;font-size:11px;line-height:1.8;max-height:480px;overflow:auto}.format-issues{border-left:3px solid #b64d40;background:#fdf0ed;padding:14px;border-radius:4px;font-size:13px}.format-issues code{display:block;margin-top:12px;font-size:11px;overflow-wrap:anywhere}.format-issues p{margin:8px 0 0;line-height:1.8}.call-identifiers{font-size:11px;color:var(--muted);margin-top:20px}.call-identifiers p{overflow-wrap:anywhere}.call-identifiers summary{cursor:pointer}@media(max-width:600px){.call-facts{grid-template-columns:1fr 1fr}.call-facts>div:first-child{grid-column:1/-1}}
</style>
