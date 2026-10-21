<script setup>
import {computed,inject,nextTick,ref,watch} from 'vue'
import {api} from '../api.js'
import {questionLabel} from '../question-navigation.js'
import AssistModel from './AssistModel.vue'
const props=defineProps({view:Object,comparison:Object,scoreReport:Object})
const work=inject('workspace'),ai=inject('ai'),caseId=ref(''),composer=ref(null),lastReply=ref(null)
const source=computed(()=>props.comparison?{comparison_id:props.comparison.comparison_id}:{run_id:props.view.run.run_id,...(props.scoreReport?{score_report_id:props.scoreReport.report_id}:{})})
const scope=computed(()=>({...source.value,...(caseId.value?{case_id:caseId.value}:{})}))
const key=computed(()=>JSON.stringify(scope.value))
const cases=computed(()=>props.comparison?props.comparison.case_pairs.map(p=>({case_id:p.case_id,query:p.query||p.baseline?.query||p.retest?.query||p.case_id})):props.view.run.case_results.filter(c=>!props.scoreReport||props.scoreReport.case_ids.includes(c.case_id)))
const state=computed(()=>{if(!ai.evaluationChats[key.value])ai.evaluationChats[key.value]={turns:[],question:'',error:'',loading:false,sending:false,loaded:false,pending:null,newThread:false};return ai.evaluationChats[key.value]})
const session=computed(()=>ai.modelSession?ai.providerOptions.find(s=>s.provider_session_id===ai.modelSession):work.state.session)
const ready=computed(()=>session.value?.credential_status==='PRESENT'&&session.value?.text_connection_status==='READY')
const model=computed(()=>session.value?.configuration.role_overrides?.general?.model||session.value?.configuration.model||'尚未连接')
const suggestions=computed(()=>caseId.value?['这道题为什么这样判？','缺了什么资料？我该怎么补？','这题是 Agent 答错了，还是评分有问题？']:props.comparison?['这次修改真的变好了吗？','哪些题变差了？下一步先查什么？','用简单的话解释这份比较。']:['为什么有些题不能判断？','运行完成了，为什么不一定代表通过？','我下一步应该做什么？'])
const sourceNames={score_report:'所选评分修订',run_overview:'本次运行记录',baseline_overview:'修改前的运行记录',retest_overview:'修改后的运行记录',comparison:'前后比较记录',focused_case:'当前题的资料与回答'}
async function load(){const s=state.value;if(s.loaded||s.loading)return;s.loading=true;s.error='';try{const result=await api.get('/ai/evaluation-chat?'+new URLSearchParams(scope.value));s.turns=result.turns;s.loaded=true}catch(e){s.error=e.message}finally{s.loading=false}}
watch(key,load,{immediate:true})
function useQuestion(text){state.value.question=text;nextTick(()=>composer.value?.focus())}
function askAboutCase(id){caseId.value=id;useQuestion('这道题为什么这样判？请说明已有证据、缺口和下一步。');nextTick(()=>composer.value?.scrollIntoView({block:'center',behavior:'smooth'}))}
defineExpose({askAboutCase})
function newThread(){const s=state.value;s.turns=[];s.pending=null;s.newThread=true;s.error='';composer.value?.focus()}
async function send(){
 const s=state.value,question=s.question.trim();if(!question||!ready.value||s.sending||s.loading)return
 const payload={...scope.value,provider_session_id:session.value.provider_session_id,question,parent_turn_id:s.newThread?null:s.turns.at(-1)?.turn_id||null}
 const fingerprint=JSON.stringify(payload)
 if(s.pending?.fingerprint!==fingerprint)s.pending={fingerprint,request_id:crypto.randomUUID()}
 s.sending=true;s.error=''
 try{const turn=await api.post('/ai/evaluation-chat',{...payload,request_id:s.pending.request_id});if(!s.turns.some(t=>t.turn_id===turn.turn_id))s.turns.push(turn);s.question='';s.pending=null;s.newThread=false;s.loaded=true;await nextTick();lastReply.value?.scrollIntoView({block:'nearest',behavior:'smooth'})}
 catch(e){s.error=e.message}finally{s.sending=false}
}
function usage(turn){const u=turn.usage;if(!u||u.unknown_usage_requests)return `${turn.provider_call_count} 次请求 · 用量${u?.known_total_tokens?`已知 ${u.known_total_tokens} Token，其余`:''}未完整返回`;return `${turn.provider_call_count} 次请求 · ${u.known_total_tokens} Token`}
</script>
<template>
 <section class="panel evaluation-chat" aria-label="评测结果 AI 问答" :aria-busy="state.sending">
  <div class="section-heading"><div><p class="eyebrow">AI 帮你读结果</p><h2>看不懂结果？直接问 AI</h2></div><span class="chat-model">{{model}}</span></div>
  <p class="muted">{{scoreReport?'只解释所选评分修订及其中的题目。':'结合本次记录解释结果，也可以继续追问。'}}</p>
  <div class="chat-context"><label>聊天范围<select v-model="caseId" :disabled="state.sending"><option value="">{{comparison?'整份前后比较':'本次全部题目'}}</option><option v-for="(c,i) in cases" :key="c.case_id" :value="c.case_id">{{questionLabel(i+1)}} · {{c.query.length>28?c.query.slice(0,28)+'…':c.query}}</option></select></label><details class="chat-settings"><summary>模型与发送内容</summary><AssistModel/><p class="chat-cost">发送本次运行记录和最近 6 轮问答。选择具体题时，包含该题资料和回答。</p></details></div>
  <p class="chat-cost">每次发送调用你的模型 API，按实际用量计费。</p>
  <div v-if="state.loading" role="status" class="muted">正在读取本页问答…</div>
  <div v-else-if="!state.turns.length" class="chat-empty">先从下面的问题选一个，或者直接输入你想问的内容。</div>
  <ol v-if="state.turns.length" class="chat-turns" aria-label="本页问答记录"><li v-for="turn in state.turns" :key="turn.turn_id"><div class="chat-message chat-user"><strong>你</strong><p>{{turn.question}}</p></div><div class="chat-message chat-assistant"><strong>AI 解释</strong><p>{{turn.answer}}</p><small>{{usage(turn)}}</small><details><summary>核对这条解释的依据</summary><div v-for="name in turn.evidence_keys" :key="name"><strong>{{sourceNames[name]||'评测记录'}}</strong><pre>{{JSON.stringify(turn.sources[name],null,2)}}</pre></div></details></div></li></ol>
  <div ref="lastReply" />
  <div class="chat-suggestions" aria-label="可以这样问"><button v-for="text in suggestions" :key="text" type="button" class="secondary" :disabled="state.sending" @click="useQuestion(text)">{{text}}</button></div>
  <p v-if="state.error" class="note danger" role="alert">{{state.error}}<button v-if="!state.loaded&&!state.loading" type="button" class="text-button" @click="load">重读问答记录</button></p>
  <div v-if="!ready" class="note"><p>先连接模型，就能在这里提问。已经保存的问答仍可查看。</p><button type="button" class="secondary" @click="work.go('setup')">去连接模型 →</button></div>
  <form @submit.prevent="send"><label>向 AI 提问<textarea ref="composer" v-model="state.question" rows="3" maxlength="2000" :disabled="state.sending||state.loading" placeholder="例如：为什么 8 道题都显示证据不足？我已经有知识库了。" /></label><div class="chat-actions"><button type="submit" class="primary" :disabled="!ready||!state.question.trim()||state.loading||state.sending">{{state.sending?'AI 正在解释…':'发送给 AI'}}</button><button v-if="state.turns.length" type="button" class="text-button" :disabled="state.sending" @click="newThread">开始新一段问答</button><span v-if="state.sending" role="status">正在读取评测记录并回答，请稍候。</span></div></form>
  <p class="chat-boundary">问答会自动保存，评测结果保持原记录。</p>
 </section>
</template>
<style scoped>
.evaluation-chat{scroll-margin-top:24px;overflow-wrap:anywhere}.evaluation-chat .section-heading{align-items:flex-start}.evaluation-chat h2{margin:5px 0 0}.chat-model{font-size:12px;padding:6px 10px;background:var(--color-canvas);border-radius:6px;max-width:40%;overflow-wrap:anywhere}.chat-context{display:flex;gap:18px;align-items:flex-start;margin-top:20px}.chat-context>label{flex:1;min-width:0;margin:0}.chat-context select{max-width:100%}.chat-settings{flex:1;min-width:0;padding-top:7px}.chat-cost,.chat-boundary{font-size:12px;line-height:1.7;color:var(--color-text-secondary);margin:12px 0}.chat-empty{padding:20px;background:var(--color-canvas);border:1px dashed var(--color-line);border-radius:8px;color:var(--color-text-secondary);font-size:14px}.chat-turns{list-style:none;padding:0;margin:18px 0;max-height:600px;overflow-y:auto;overscroll-behavior:contain}.chat-turns>li{display:grid;gap:10px;margin-bottom:20px}.chat-message{padding:16px 18px;border:1px solid var(--color-line);border-radius:10px}.chat-message>strong{font-size:13px}.chat-message>p{white-space:pre-wrap;line-height:1.85;margin:8px 0 0}.chat-user{margin-left:12%;background:var(--color-canvas)}.chat-assistant{margin-right:5%}.chat-assistant small{display:block;margin-top:12px;color:var(--color-text-secondary);font-size:12px}.chat-assistant details{margin-top:12px;font-size:12px}.chat-assistant pre{max-height:220px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}.chat-suggestions{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0}.chat-suggestions button{font-size:13px;text-align:left;padding:9px 12px;min-width:0;white-space:normal}.chat-actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.chat-actions>span{font-size:13px;color:var(--color-text-secondary)}.evaluation-chat textarea{min-height:90px;resize:vertical}.evaluation-chat summary{cursor:pointer}
@media(max-width:600px){.evaluation-chat .section-heading{flex-direction:column;align-items:flex-start;gap:10px}.chat-context{display:block}.chat-settings{padding-top:16px}.chat-model{max-width:100%}.chat-user{margin-left:6%}.chat-assistant{margin-right:0}.chat-message{padding:14px}.chat-turns{max-height:500px}.chat-suggestions{display:grid}.chat-actions>button:first-child{width:100%}}
</style>
