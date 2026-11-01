<script setup>
import {analytics} from '../analytics.js'
import { computed, inject, reactive, ref, watch } from 'vue'
import { modelPresets, presetConfig, identifyPreset, isAcceptanceConnection } from '../model-presets.js'
import { api } from '../api.js'
import { toolStates } from '../presentation'
import IndependentJudge from '../components/IndependentJudge.vue'
const work = inject('workspace'), { state } = work
const startNewExperiment=inject('newExperiment')
const anonymousWorkspace = inject('anonymousWorkspace', ref(false))
const experimentMode=inject('experimentMode'), rag=inject('retrieval')
const isRetrieval=computed(()=>experimentMode?.value==='RETRIEVAL')
const activeBaseline=computed(()=>isRetrieval.value?rag?.state.baseline:state.baseline)
const config = reactive({ ...presetConfig('deepseek'), temperature: 0,
  max_tokens: 1024, timeout_seconds: 60, max_calls: 100, context_window_tokens:32768 })
const selectedPreset = ref('deepseek')
const preset = computed(() => modelPresets.find(p => p.id === selectedPreset.value))
const siteStatus=ref(''), siteBusy=ref(false)
const siteMessages={AVAILABLE:'站点 API 当前有可用额度，可以连接使用。',SUCCESS:'已连接站点 API，可以继续准备资料。',NO_BALANCE:'站点 API 额度已用完，请在下方连接自己的 API。',NOT_CONFIGURED:'站点 API 暂未开放，请连接自己的 API。',AUTH_FAILED:'站点 API 暂不可用，请连接自己的 API。',CHECK_FAILED:'暂时无法查询额度，可重试或连接自己的 API。',CONNECTION_FAILED:'站点 API 连接未通过，请重试或连接自己的 API。'}
async function checkSite(connect=false){
 siteBusy.value=true
 try{const result=connect?await work.connectSite():await api.post('/site-provider/check');siteStatus.value=result?.status||'CHECK_FAILED'}
 catch{siteStatus.value='CHECK_FAILED'}finally{siteBusy.value=false}
}
const key = ref(''), roles = ref('{}'), outputMode=ref('text')
const historicalTestConnection=computed(()=>isAcceptanceConnection(state.session?.configuration))
watch(() => state.session, session => { if (session) {
 if(isAcceptanceConnection(session.configuration)){
  selectedPreset.value='deepseek';outputMode.value='text';roles.value='{}'
  Object.assign(config,presetConfig('deepseek'),{temperature:0,max_tokens:1024,timeout_seconds:60,max_calls:100,context_window_tokens:32768})
  return
 }
 outputMode.value=session.configuration.judge_output_mode||'text';Object.assign(config,{thinking_mode:null},session.configuration);selectedPreset.value=identifyPreset(session.configuration);roles.value=JSON.stringify(session.configuration.role_overrides||{},null,2)
} },{immediate:true})
function presetChanged() { outputMode.value='text'; Object.assign(config, presetConfig(selectedPreset.value)); key.value = ''; roles.value = '{}' }
function providerChanged() { outputMode.value='text'; selectedPreset.value = 'custom'; config.thinking_mode = null; config.base_url = config.provider === 'openai-compatible' ? '' : 'https://api.anthropic.com'; key.value = '' }
async function save() {
  try { await work.action('校验模型配置', async () => JSON.parse(roles.value))
    if (state.error){analytics.blocked('setup.save','invalid_input');return}
    // A new main connection must not inherit an old Judge's lost credential.
    // The independent Judge panel explicitly binds a verified connection later.
    const {judge_provider_session_id, judge_provider_configuration, judge_output_mode, ...mainConfig} = config
    await work.connectAndCheck({ ...mainConfig, ...(outputMode.value!=='text'?{judge_output_mode:outputMode.value}:{}), role_overrides: JSON.parse(roles.value) }, key.value)
  } finally { key.value = '' }
}
</script>
<template>
  <div class="page-heading"><div><h1>连接模型</h1></div><span class="pill">Key 仅保留在当前后端内存</span></div>
  <section class="panel"><h2>使用站点 API</h2><p>无需填写 Key，使用站点提供的 DeepSeek。可以先检查额度；连接检查会发送一次简短测试请求，后续实验使用站点额度。</p>
    <div class="button-row"><button class="secondary" :disabled="siteBusy || !!state.busy" @click="checkSite()">{{siteBusy?'正在检查…':'检查站点 API 额度'}}</button><button class="primary" :disabled="siteBusy || !!state.busy" @click="checkSite(true)">使用站点 API 并检查连接</button></div>
    <p v-if="siteStatus" role="status">{{siteMessages[siteStatus]||siteMessages.CHECK_FAILED}}</p>
    <p class="muted">额度是共享的，本次检查可用不保证后续始终充足。也可以直接使用下方自己的 API。</p>
  </section>
  <div class="two-column setup-columns">
    <section class="panel"><h2>使用自己的 API</h2><p v-if="historicalTestConnection" class="note">旧实验使用本地测试服务。这里已填入 DeepSeek 官方配置，也可以改选其他服务；输入密钥后点击“连接并检查”。</p><p class="muted">连接并检查会保存当前配置并发送一次测试请求；费用以服务账单为准。</p>
      <form @submit.prevent="save">
        <label>模型服务<select aria-label="模型服务" v-track="{action:'setup.service',placement:'SetupPage.control_01'}" v-model="selectedPreset" @change="presetChanged"><option v-for="item in modelPresets" :key="item.id" :value="item.id">{{ item.label }}</option></select></label>
        <p class="muted preset-note">{{ anonymousWorkspace ? '公开站点支持 DeepSeek、百炼、Kimi、OpenAI、Claude、硅基流动、智谱、MiniMax 和火山方舟的已配置官方 HTTPS 地址。自定义地址也须在上述服务范围内。模型名称以你的账号实际开通为准。' : preset?.note }} <a v-track="{action:'setup.docs',placement:'SetupPage.control_02'}" v-if="preset?.docs" :href="preset.docs" target="_blank" rel="noopener noreferrer">官方说明 ↗</a></p>
        <label>Base URL<input aria-label="Base URL" v-track="{action:'setuppage.edit_start',placement:'SetupPage.editor',kind:'edit'}" v-model="config.base_url" type="url" required placeholder="https://api.openai.com/v1" /></label>
        <label>Model<input aria-label="Model" v-track="{action:'setuppage.edit_start',placement:'SetupPage.editor',kind:'edit'}" v-model="config.model" list="model-suggestions" required placeholder="选择建议或输入已开通的模型名" /></label>
        <datalist id="model-suggestions"><option v-for="model in preset?.models" :key="model" :value="model" /></datalist>
        <label>API Key<input aria-label="API Key" v-track="{action:'setuppage.edit_start',placement:'SetupPage.editor',kind:'edit'}" v-model="key" type="password" required autocomplete="off" spellcheck="false" placeholder="仅用于本次后端会话" /></label>
        <details><summary>生成参数（可选）</summary><div class="form-row"><label>Temperature<input v-track="{action:'setuppage.edit_start',placement:'SetupPage.editor',kind:'edit'}" v-model.number="config.temperature" type="number" min="0" max="1" step="0.1" required /></label><label>Max Tokens<input v-track="{action:'setuppage.edit_start',placement:'SetupPage.editor',kind:'edit'}" v-model.number="config.max_tokens" type="number" min="1" max="4096" required /></label></div></details>
        <details class="advanced"><summary v-track="{action:'setup.advanced',placement:'SetupPage.control_03'}">高级设置</summary><div class="form-row"><label>请求超时（秒）<input v-track="{action:'setuppage.edit_start',placement:'SetupPage.editor',kind:'edit'}" v-model.number="config.timeout_seconds" type="number" min="0.1" max="120" step="0.1" required /></label><label>上下文总预算（含输出预留）<input v-model.number="config.context_window_tokens" type="number" min="1024" max="2000000" required /></label><label>单次调用预算<input v-track="{action:'setuppage.edit_start',placement:'SetupPage.editor',kind:'edit'}" v-model.number="config.max_calls" type="number" min="1" max="500" required /></label></div>
          <label>Provider<select v-track="{action:'setup.protocol',placement:'SetupPage.control_04'}" v-model="config.provider" @change="providerChanged"><option value="openai-compatible">OpenAI-compatible</option><option value="anthropic-compatible">Anthropic-compatible</option></select></label>
          <details v-if="config.provider==='openai-compatible'"><summary>评分输出约束（可选）</summary><label>服务支持的格式<select v-model="outputMode"><option value="text">文本 JSON · 默认</option><option value="json_object">JSON 模式</option><option value="json_schema">严格 JSON Schema</option></select></label><p class="muted">按当前地址与模型的实际支持选择。服务拒绝时会保留错误，不会自动切换格式。</p></details>
          <label v-if="config.provider === 'openai-compatible'">输出预算参数<select v-track="{action:'setup.budget_parameter',placement:'SetupPage.control_05'}" v-model="config.completion_token_parameter"><option>max_completion_tokens</option><option>max_tokens</option></select></label>
          <label v-if="config.provider === 'openai-compatible'">模型思考模式<select v-track="{action:'setup.thinking',placement:'SetupPage.control_06'}" v-model="config.thinking_mode"><option :value="null">使用服务默认设置</option><option value="disabled">普通对话（服务支持时关闭思考）</option></select></label>
          <label>角色配置覆盖（JSON）<textarea v-track="{action:'setuppage.edit_start',placement:'SetupPage.editor',kind:'edit'}" v-model="roles" rows="5" spellcheck="false" placeholder='{"judge":{"model":"your-judge-model"}}' /></label><p class="muted">general / technical / billing / escalation / composer / intent / judge。未覆盖字段继承用户默认配置。</p>
        </details>
        <button v-track="{action:'setup.save',placement:'SetupPage.control_07',core:true,reason:(!key ? 'missing_input' : !config.model ? 'missing_input' : 'busy')}" class="primary" :disabled="!!state.busy || !key || !config.model">连接并检查</button>
      </form>
    </section>
    <div class="stack"><section class="panel connection-panel"><h2>{{historicalTestConnection?'旧实验的连接':'当前连接'}}</h2>
      <p v-if="state.session&&!historicalTestConnection" class="muted">{{state.session.configuration.base_url}} · {{state.session.configuration.model}}</p>
      <p v-if="historicalTestConnection" class="note warning">这份记录来自本地测试，不能作为你当前可用的模型连接。原来的实验结果仍可查看。</p>
      <div class="connection-check"><div><p>{{ state.session?.credential_status === 'PRESENT' && state.session?.text_connection_status === 'READY' ? '✓ 当前连接可用' : state.session?.credential_status !== 'PRESENT' ? '当前凭据不可用，请重新连接；历史测试结果仅供回看' : state.session?.text_connection_status === 'FAILED' ? '模型连接失败，请检查地址、模型名称和凭据' : '等待连接检查' }}</p><button v-track="{action:'setup.test',placement:'SetupPage.control_08',core:true,reason:(state.session?.credential_status !== 'PRESENT' ? 'credentials' : 'busy')}" class="secondary" :disabled="!!state.busy || state.session?.credential_status !== 'PRESENT'" @click="work.testConnection">测试连接</button></div></div>
      <details v-if="!isRetrieval"><summary>工具能力检查</summary><div class="connection-check"><span class="check-number">2</span><div><h3>工具调用能力 <span class="badge" :class="state.session?.tool_call_capability?.toLowerCase()">{{ toolStates[state.session?.tool_call_capability] || '未测试' }}</span></h3><p>检查模型能否正确调用工具，不会执行真实退款。</p><button v-track="{action:'setup.tools',placement:'SetupPage.control_09',core:true,reason:(state.session?.credential_status !== 'PRESENT' ? 'credentials' : state.session?.text_connection_status !== 'READY' ? 'connection' : 'busy')}" class="secondary" :disabled="!!state.busy || state.session?.credential_status !== 'PRESENT' || state.session?.text_connection_status !== 'READY'" @click="work.testTools">测试工具能力</button></div></div>
      </details><p v-if="!isRetrieval&&state.session?.tool_call_capability === 'UNSUPPORTED'" class="note danger">该模型可以普通对话，但当前无法运行智能电商 Agent 的完整客服评测。{{isRetrieval?'Retrieval 路径可使用文本连接；它不执行原业务工具链。':''}}</p>
      <p v-if="!isRetrieval&&state.session?.tool_call_capability === 'FAILED'" class="note warning">探针暂时失败。这不等同于明确不支持，请检查连接与参数后重试。</p>
      <p v-if="!isRetrieval&&state.session?.tool_call_capability === 'VERIFIED'" class="note positive">工具格式已验证；这不代表完整客服链路或回答质量已经通过。</p>
      <div class="button-row"><button v-track="{action:'setup.next',placement:'SetupPage.control_10'}" class="primary" :disabled="!!state.busy || state.session?.text_connection_status !== 'READY' || state.session?.credential_status !== 'PRESENT'" @click="work.go(activeBaseline ? 'evaluate' : isRetrieval ? 'knowledge' : 'define')">{{ activeBaseline ? '返回当前实验' : isRetrieval ? '下一步：准备资料' : '下一步：准备题目' }} <span>→</span></button><button type="button" class="secondary" :disabled="!!state.busy" @click="startNewExperiment">开始新实验</button></div>
    </section></div>
  </div>
  <details v-if="isRetrieval" class="separate-judge"><summary>使用另一模型评分（可选）</summary><IndependentJudge /></details>
</template>
