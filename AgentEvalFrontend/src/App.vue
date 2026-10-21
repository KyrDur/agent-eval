<script setup>
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { createWorkspace } from './workspace.js'
import SetupPage from './pages/SetupPage.vue'
import DefinePage from './pages/DefinePage.vue'
import EvaluatePage from './pages/EvaluatePage.vue'
import ImprovePage from './pages/ImprovePage.vue'
import ComparePage from './pages/ComparePage.vue'
import StatusBadge from './components/StatusBadge.vue'
import RetrievalPage from './pages/RetrievalPage.vue'
import { createRetrievalWorkspace } from './retrieval-workspace.js'
import { createCareerWorkspace } from './career-workspace.js'
import CareerPage from './pages/CareerPage.vue'
import { prepareWorkspace,api } from './api.js'
import { createPracticeWorkspace } from './practice-workspace.js'
import JourneyGuide from './components/JourneyGuide.vue'
import WorkspaceIcon from './components/WorkspaceIcon.vue'
import WorkspaceDrawer from './components/WorkspaceDrawer.vue'
import {createAiAssistance,restoreAiDrafts} from './ai-assistance.js'
import ChatPage from './pages/ChatPage.vue'
import KnowledgePage from './pages/KnowledgePage.vue'
import PracticeTestsPage from './pages/PracticeTestsPage.vue'
import {analytics} from './analytics.js'
import {refreshControls} from './analytics-controls.js'
import LandingPage from './components/LandingPage.vue'
import CalibrationPage from './pages/CalibrationPage.vue'
const OperationsPage=defineAsyncComponent(()=>import('./pages/OperationsPage.vue'))
const operationsPage=ref(null)
import LearningPage from './pages/LearningPage.vue'
import {createCalibrationWorkspace} from './calibration-workspace.js'
const analyticsExcluded=ref(false), statisticsOpen=ref(false), statisticsNotice=ref('')
async function toggleStatistics(){
  try { analyticsExcluded.value=await analytics.preference(!analyticsExcluded.value);statisticsNotice.value='设置已保存。' }
  catch {statisticsNotice.value='设置未保存，请稍后重试。'}
}
const anonymousWorkspace = ref(false)
provide('anonymousWorkspace', anonymousWorkspace)
const work = createWorkspace(), { state } = work
watch(()=>state.step, step=>analytics.page(step))
const rag = createRetrievalWorkspace(work)
const calibration=createCalibrationWorkspace(work)
provide('calibration',calibration)
const ai=createAiAssistance();provide('ai',ai)
const mode = ref(localStorage.getItem('agenteval.experiment-mode') === 'AGENT_BEHAVIOR' ? 'AGENT_BEHAVIOR' : 'RETRIEVAL')
watch(mode,value=>analytics.setPath(value),{immediate:true})
const practice=createPracticeWorkspace(work,rag)
provide('practice',practice)
const career=createCareerWorkspace(work,rag,mode)
provide('career',career)
let ragReady=false
watch(()=>state.session?.provider_session_id,()=>{if(mode.value==='RETRIEVAL' && ragReady)rag.persist()})
provide('workspace', work)
provide('retrieval', rag)
provide('experimentMode', mode)
onMounted(async () => {
  const identity = await work.action('建立浏览器工作区', () => prepareWorkspace(), false)
  if (state.error) return
  anonymousWorkspace.value = !!identity?.isolated
  void analytics.start(state.step).then(value=>{analyticsExcluded.value=value;refreshControls()})
  await work.initialize()
  if(state.error)return
  if(mode.value==='RETRIEVAL'){await rag.action('恢复检索实验',rag.restore);ragReady=true}
  if(state.error)return
  await work.action('读取聊天与知识库',practice.restore)
  if(state.error)return
  await work.action('恢复 AI 生成草稿',()=>restoreAiDrafts(ai,api))
  if(state.error)return
  await work.action('恢复评测校准',calibration.restore)
}); onUnmounted(()=>{work.dispose();rag.dispose()})
async function switchMode(){localStorage.setItem('agenteval.experiment-mode',mode.value);showHistory.value=false;
  ragReady=false;if(mode.value==='RETRIEVAL'){await rag.action('读取检索实验',rag.restore);ragReady=true}}
async function navigate(step){showHistory.value=false;if(['chat','knowledge'].includes(step) && mode.value!=='RETRIEVAL'){mode.value='RETRIEVAL';await switchMode()}work.go(step)}
async function sync(){if(state.step==='operations')await work.action('同步日志评测',()=>operationsPage.value?.sync());else if(state.step==='calibration')await work.action('同步校准状态',calibration.restore);else if(mode.value==='RETRIEVAL')await rag.action('同步检索状态',rag.restore);else await work.action('同步后端状态',work.restore)}
function reset(){if(mode.value==='RETRIEVAL'){rag.reset();work.go('define')}else work.reset();showHistory.value=false}
const showHistory = ref(false)
const isWelcome = computed(()=>state.step==='welcome' && !showHistory.value)
// Keep a long landing page from carrying its scroll position into the workspace.
watch(isWelcome,async()=>{await nextTick();window.scrollTo({top:0,left:0,behavior:'instant'})})
const canContinueEvaluation = computed(()=>mode.value==='RETRIEVAL' ? !!rag.state.evalSet : !!state.evalSet)
async function beginFirstEvaluation(){
  if(mode.value!=='RETRIEVAL'){mode.value='RETRIEVAL';await switchMode()}
  work.go('setup')
}
watch(showHistory, value=>analytics.page(value?'history':state.step))
const helpOpen=ref(false),settingsOpen=ref(false)
const activeGroup=computed(()=>['setup','knowledge','define'].includes(state.step)?'prepare':['operations','calibration'].includes(state.step)?'quality':state.step)
const navigation=[{id:'prepare',title:'准备',icon:'prepare'},{id:'evaluate',title:'看结果',icon:'chart'},{id:'improve',title:'试修改',icon:'adjust'},{id:'compare',title:'看变化',icon:'compare'},{id:'career',title:'整理项目',icon:'folder'},{id:'quality',title:'日志与评分',icon:'scale'}]
const preparationTabs=[['setup','连接模型','plug'],['knowledge','知识资料','document'],['define','测试题目','list']]
const qualityTabs=[['operations','日志评测','log'],['calibration','评测标准','scale']]
const currentTabs=computed(()=>activeGroup.value==='prepare'?preparationTabs:activeGroup.value==='quality'?qualityTabs:[])
async function navigateGroup(id){
 const target=id==='prepare'?(['setup','knowledge','define'].includes(state.step)?state.step:!state.session?'setup':!rag.state.index?'knowledge':'define'):id==='quality'?'operations':id
 await navigate(target)
}
watch(()=>state.step,async()=>{helpOpen.value=false;await nextTick();window.scrollTo({top:0,left:0,behavior:'instant'})})
const projectName = run => state.evalSets.find(e => e.eval_set_id === run.eval_set_id)?.metadata.objective?.name || '电商客服实验'
async function open(id) { if(mode.value==='RETRIEVAL'){await rag.action('打开检索实验',()=>rag.open(id));work.go('evaluate')}else await work.action('打开历史实验', () => work.openHistory(id)); showHistory.value = false }
async function history() { if(mode.value==='RETRIEVAL')await rag.action('读取检索历史',rag.restore);else await work.action('读取历史实验', work.history); showHistory.value = true }
const visibleHistory=computed(()=>mode.value==='RETRIEVAL'?rag.state.history:state.history)
const projectTitle=computed(()=>state.step==='learning'?'练习':state.step==='calibration' ? '评测校准' : mode.value==='RETRIEVAL' ? rag.state.evalSet?.name || rag.state.knowledge?.name || '我的实验' : state.evalSet?.metadata.objective?.name || '我的实验')
</script>
<template>
  <div class="workspace-shell visual-workspace" :class="{'welcome-screen':isWelcome}">
    <aside v-if="!isWelcome" class="sidebar visual-sidebar">
     <button class="brand" aria-label="Agent Eval 首页" @click="work.go('welcome')"><span class="visual-brand-mark"><WorkspaceIcon name="prepare" :size="25" /></span><strong>Agent Eval</strong></button>
     <span class="visual-nav-caption">我的工作台</span>
     <nav class="task-navigation" aria-label="主导航"><button v-for="item in navigation" :key="item.id" type="button" :class="{selected:activeGroup===item.id}" :aria-current="activeGroup===item.id?'page':undefined" :disabled="!!state.busy" @click="navigateGroup(item.id)"><WorkspaceIcon :name="item.icon" :size="19" /><strong>{{item.title}}</strong><span v-if="activeGroup===item.id" class="visual-nav-current" /></button></nav>
     <div class="visual-sidebar-bottom"><button type="button" class="visual-sidebar-link" :class="{selected:state.step==='learning'}" @click="navigate('learning')"><WorkspaceIcon name="book" :size="18" />新手入门</button><button type="button" class="visual-sidebar-link" :disabled="!!state.busy" @click="history"><WorkspaceIcon name="history" :size="18" />历史实验</button><button type="button" class="secondary" :disabled="!!state.busy" @click="reset"><WorkspaceIcon name="plus" :size="17" />新实验</button></div>
    </aside>
    <div class="workspace-body"><header v-if="!isWelcome" class="topbar visual-topbar"><div><span class="breadcrumb">我的实验</span><span class="separator">/</span><strong>{{projectTitle}}</strong></div><div class="visual-topbar-actions"><button type="button" class="text-button" aria-label="工作区设置" @click="settingsOpen=true"><WorkspaceIcon name="adjust" :size="16" /><span>工作区</span></button><button type="button" class="text-button" aria-label="同步状态" :disabled="!!state.busy" @click="sync"><WorkspaceIcon name="refresh" :size="16" /><span>同步</span></button><button type="button" class="text-button" aria-label="帮助" @click="helpOpen=true"><WorkspaceIcon name="help" :size="17" /><span>帮助</span></button></div></header>
      <nav v-if="!isWelcome&&currentTabs.length" class="visual-preparation-tabs" :aria-label="activeGroup==='prepare'?'准备步骤':'日志与评分功能'"><button v-for="[id,title,icon] in currentTabs" :key="id" type="button" :class="{active:state.step===id}" :aria-current="state.step===id?'page':undefined" :disabled="!!state.busy" @click="navigate(id)"><WorkspaceIcon :name="icon" :size="18" />{{title}}</button></nav>
      <main>
        <div v-if="state.error" class="error-banner" role="alert"><div><small v-if="state.error.operation">{{ state.error.operation }} · </small><strong>{{ state.error.title }}</strong><p>{{ state.error.message }}</p></div><button v-track="{action:'site.dismiss_error',placement:'App.control_07'}" class="text-button" @click="state.error = null">关闭</button></div>
        <div v-if="state.notice" class="note positive" role="status">{{ state.notice }}</div>
        <p v-if="state.busy" class="busy-label" role="status"><span class="spinner small" />{{ state.busy }}</p>

        <section v-if="showHistory" class="panel history-panel"><div class="section-heading"><div><span class="eyebrow">历史实验</span><h2>我的实验记录</h2></div><button v-track="{action:'history.return',placement:'App.control_08'}" class="text-button" @click="showHistory = false">返回工作台</button></div><p class="muted">已保存的结果可以随时回看。</p>
          <p v-if="!visibleHistory.length" class="empty">还没有实验记录。</p><button v-track="{action:'history.open',placement:'App.control_09'}" v-for="run in visibleHistory" :key="run.run_id" class="history-row" :disabled="!!state.busy" @click="open(run.run_id)"><span><strong>{{ mode === 'RETRIEVAL' ? run.name : projectName(run) }}</strong><small>{{ run.run_type === 'BASELINE' ? '首次评测' : '修改后复测' }} / {{ new Date(run.created_at).toLocaleString('zh-CN') }}</small></span><StatusBadge :status="run.status" /><span>→</span></button>
        </section>
        <LandingPage v-else-if="state.step === 'welcome'" :busy="!!state.busy" :can-continue="canContinueEvaluation" @start="beginFirstEvaluation" @practice="navigate('learning')" @resume="navigate('evaluate')" @history="history" @statistics="statisticsOpen=!statisticsOpen" />
        <OperationsPage ref="operationsPage" v-else-if="state.step === 'operations'" /><LearningPage v-else-if="state.step === 'learning'" /><CalibrationPage v-else-if="state.step === 'calibration'" /><ChatPage v-else-if="state.step === 'chat'" /><KnowledgePage v-else-if="state.step === 'knowledge'" /><PracticeTestsPage v-else-if="state.step === 'define' && mode === 'RETRIEVAL'" /><CareerPage v-else-if="state.step === 'career'" /><SetupPage v-else-if="state.step === 'setup'" /><RetrievalPage v-else-if="mode === 'RETRIEVAL'" :step="state.step" /><DefinePage v-else-if="state.step === 'define'" /><EvaluatePage v-else-if="state.step === 'evaluate'" /><ImprovePage v-else-if="state.step === 'improve'" /><ComparePage v-else-if="state.step === 'compare'" />
      </main><footer v-if="!isWelcome" class="workspace-footer"><span>Agent Eval · 每次判断，都有依据。</span><button v-track="{action:'site.statistics',placement:'App.control_12'}" class="text-button" @click="statisticsOpen=!statisticsOpen">统计设置</button><span>{{ anonymousWorkspace ? '此浏览器的独立工作区' : '本地工作区' }}</span></footer>
      <section v-if="statisticsOpen" class="note" style="margin:0 32px 24px" aria-label="统计设置"><strong>匿名使用统计</strong><p>统计页面浏览和功能操作状态，不采集 API Key、聊天正文或材料内容。可排除当前浏览器的测试记录；清除 Cookie 后需重新设置。</p><button v-track="{action:'site.exclusion',placement:'App.control_13'}" class="secondary" @click="toggleStatistics">{{analyticsExcluded?'恢复当前浏览器统计':'排除当前浏览器统计'}}</button><p role="status">{{statisticsNotice}}</p></section>
    </div>
    <WorkspaceDrawer :open="helpOpen" title="这一步怎么做" @close="helpOpen=false"><JourneyGuide v-if="mode==='RETRIEVAL'&&!['calibration','learning','operations'].includes(state.step)" :key="state.step" :step="state.step" opened @navigate="navigate" /><template v-else-if="state.step==='learning'"><p>先选资料重排、查询改写、调整返回条数、修改回答提示词或补充知识库，再逐步查看证据、修改和复测。</p><p>这些是预设教学案例。真正的修改与结果，请进入自己的实验。</p><a href="/evaluation-guide.html">打开评测原理图解 →</a></template><template v-else><p>日志评测用来检查已保存的回答；评测标准用来核对模型打分是否合理。</p><a href="/evaluation-guide.html">打开图解说明 →</a></template></WorkspaceDrawer>
    <WorkspaceDrawer :open="settingsOpen" title="工作区设置" @close="settingsOpen=false"><label>实验类型<select v-model="mode" :disabled="!!state.busy" @change="switchMode"><option value="RETRIEVAL">客服知识问答</option><option value="AGENT_BEHAVIOR">客服行为与工具调用</option></select></label><p class="note">{{mode==='RETRIEVAL'?'固定知识与索引，缓存关闭。':'此路径不使用知识检索或长期记忆。'}}</p><p v-if="anonymousWorkspace" class="note">此浏览器独立保存实验入口。清除 Cookie、无痕浏览或换设备后，旧记录无法自动找回；服务器重启后需重新输入模型 Key。</p><div class="button-row"><button type="button" class="secondary" @click="settingsOpen=false;history()">历史实验</button><button type="button" class="secondary" @click="settingsOpen=false;navigate('learning')">新手入门</button><button type="button" class="secondary" :disabled="!!state.busy" @click="settingsOpen=false;reset()">新实验</button></div><a href="/evaluation-guide.html">新手图解说明 →</a></WorkspaceDrawer>
  </div>
</template>

<style scoped>
.task-navigation{gap:8px}.experiment-navigation{border-block:1px solid var(--border);padding:14px 0;margin:10px 0}.experiment-navigation>summary{font-size:12px;color:var(--muted);padding:5px 12px;cursor:pointer}.experiment-navigation[open]>summary{margin-bottom:8px}.experiment-nav-items{display:grid;gap:3px}
@media(max-width:900px){.sidebar .task-navigation{display:flex;flex-wrap:wrap;align-items:flex-start;justify-content:flex-start;gap:8px}.task-navigation>button{flex:1;min-width:130px}.experiment-navigation{flex:1;min-width:180px;margin:0;padding:0;border:0}.experiment-navigation>summary{padding:9px 12px;font-size:12px}.experiment-nav-items{grid-template-columns:repeat(3,minmax(0,1fr))}.experiment-navigation[open]{order:3;flex-basis:100%}}
</style>
