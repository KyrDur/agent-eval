<script setup>
import {nextTick,ref} from 'vue'
import EvidenceStrip from './EvidenceStrip.vue'
import '../landing.css'
defineProps({busy:Boolean,canContinue:Boolean})
const emit=defineEmits(['start','practice','resume','history','statistics'])
const menuOpen=ref(false),menuButton=ref(null),selectedId=ref(null)
function closeMenu(){menuOpen.value=false}
async function escapeMenu(){closeMenu();await nextTick();menuButton.value?.focus()}
function start(){closeMenu();emit('start')}
function resume(){closeMenu();emit('resume')}
// These examples are presentation-only. They never enter workspace state or API requests.
const examples=[
 {id:'001',question:'定制商品可以无理由退货吗？',rule:'定制商品不支持无理由退货。',source:'来源：模拟店铺规则 · 退换货条款',answer:'所有商品都可以无理由退货。',retrieval:'找到规则',exampleKind:'rule_conflict',state:'fail',verdict:'回答与店铺规则不一致',reason:'回答没有遵守给定规则。',answerStatus:'未通过'},
 {id:'002',question:'退款什么时候到账？',rule:'退款审核通过后原路退回，到账时间以支付渠道为准。',source:'来源：模拟店铺规则 · 退款条款',answer:null,retrieval:'找到规则',exampleKind:'unchecked',state:'unchecked',verdict:'回答尚未检查',reason:'本示意未开启回答检查，不能据此判断客服答对了。',answerStatus:'未检查'},
 {id:'003',question:'如何申请电子发票？',rule:'申请电子发票需提供订单信息与发票抬头。',source:'来源：模拟店铺规则 · 发票条款',answer:null,retrieval:'未取得结果',exampleKind:'invalid_execution',state:'invalid',verdict:'执行无效，暂不能判断',reason:'本示意的请求未完成；执行失败不等于回答错误。',answerStatus:'未检查'},
 {id:'004',question:'积分可以提现吗？',rule:'积分仅可用于兑换，不支持提现。',source:'来源：模拟店铺规则 · 积分条款',answer:'积分可以用于兑换，不能直接提现。',retrieval:'找到规则',exampleKind:'supported_answer',state:'pass',verdict:'示例回答符合给定规则',reason:'本示意的回答保留了兑换用途与提现限制。',answerStatus:'通过'},
]
const selected=()=>examples.find(e=>e.id===selectedId.value)
</script>
<template>
 <div class="landing-page">
  <header class="landing-header landing-container">
   <a v-track="{action:'site.home',placement:'LandingPage.control_01'}" class="landing-wordmark" href="#product" @click="closeMenu">Agent Eval <span>Agent 评测项目实践</span></a>
   <button v-track="{action:'welcome.menu',placement:'LandingPage.control_02'}" ref="menuButton" class="landing-menu-toggle" :aria-expanded="menuOpen" aria-controls="landing-navigation" @click="menuOpen=!menuOpen">{{menuOpen?'收起导航':'菜单'}}<span aria-hidden="true">{{menuOpen?'−':'＋'}}</span></button>
   <nav id="landing-navigation" class="landing-navigation" :class="{'is-open':menuOpen}" aria-label="首页导航" @keydown.esc="escapeMenu">
    <a v-track="{action:'welcome.section',placement:'LandingPage.control_03'}" href="#product" @click="closeMenu">产品介绍</a>
    <a v-track="{action:'welcome.section',placement:'LandingPage.control_04'}" href="#example" @click="closeMenu">评测示例</a>
    <a v-track="{action:'welcome.section',placement:'LandingPage.control_05'}" href="#workflow" @click="closeMenu">使用流程</a>
    <button v-if="canContinue" v-track="{action:'site.navigate.evaluate',placement:'LandingPage.control_06',core:true}" class="primary landing-nav-action" :disabled="busy" @click="resume">继续实验 <span aria-hidden="true">→</span></button>
    <button v-else v-track="{action:'welcome.setup',placement:'LandingPage.control_06',core:true}" class="primary landing-nav-action" :disabled="busy" @click="start">开始评测 <span aria-hidden="true">→</span></button>
   </nav>
  </header>

  <section id="product" class="landing-hero landing-container" aria-labelledby="landing-title">
   <div class="landing-hero-copy"><p class="landing-eyebrow">AGENT EVAL · 从一个完整案例开始</p><h1 id="landing-title" v-track="{action:'welcome.content',placement:'LandingPage.content_product',kind:'view',content:'product'}">客服 Agent 答错了，<br/>你知道该改哪里吗？</h1><p class="landing-intro">资料没找对？回答漏了条件？还是评分模型判错了？先看一个案例怎样查明原因、尝试修改、对比结果，再跟着做一道题。</p>
    <div class="landing-actions"><button class="primary landing-main-action" :disabled="busy" @click="emit('practice')">先看一个完整案例 →</button><button v-track="{action:'welcome.setup',placement:'App.control_10',core:true}" class="secondary landing-main-action" :disabled="busy" @click="start">使用自己的模型做实验 <span aria-hidden="true">→</span></button><button v-if="canContinue" v-track="{action:'site.navigate.evaluate',placement:'App.control_11',core:true}" class="text-button" :disabled="busy" @click="resume">继续已有实验 <span aria-hidden="true">→</span></button></div>
    <p class="landing-key-note">看示范、做练习都不需要 API Key。使用自己的模型时，调用费用由模型服务商收取。</p>
   </div>
   <div class="product-preview" aria-label="Agent Eval 单题评测示意">
    <aside class="product-preview-sidebar" aria-hidden="true"><strong>Agent Eval</strong><small>准备评测</small><span>连接模型</span><span>准备资料</span><span>测试题</span><small>评测与改进</small><span class="is-current">首次评测</span><span>改进方案</span><span>复测比较</span><small>整理成果</small><span>项目复盘与导出</span></aside>
    <div class="product-preview-content"><div class="preview-heading"><p>单题分析 / 模拟案例</p><span class="illustration-label">评测示意</span></div><h2>这道题为什么没有通过？</h2><EvidenceStrip :example="examples[0]" compact/><p class="preview-footnote">模拟例子，点击下方题目可以看依据。</p></div>
   </div>
  </section>

  <section id="workflow" class="landing-workflow" aria-label="三步使用流程"><ol class="landing-container"><li><span>01</span><div><h2 v-track="{action:'welcome.content',placement:'LandingPage.content_workflow',kind:'view',content:'workflow'}">连接模型</h2><p>配置你已开通的模型服务，确认连接成功。</p></div></li><li><span>02</span><div><h2>准备资料和题目</h2><p>可以用示例，也可以让 AI 帮你起草。核对后看看客服怎么答。</p></div></li><li><span>03</span><div><h2>改完，再跑一次</h2><p>选一个具体问题来改，比较前后结果，也看看有没有别的题变差。</p></div></li></ol></section>

  <section id="example" class="landing-example landing-container landing-section" aria-labelledby="example-title">
   <div class="landing-section-heading"><p class="landing-eyebrow">01 / 评测示例</p><h2 id="example-title" v-track="{action:'welcome.content',placement:'LandingPage.content_example',kind:'view',content:'example'}">同一句回答，<br/>为什么有人觉得对，有人觉得错？</h2><p>别急着改模型。先把客服的话和店铺规则放在一起看看。</p></div>
   <div class="landing-example-content"><div class="illustration-caption"><span class="illustration-label">评测示意</span><span>模拟店铺 · 开启回答检查后的示例</span></div><EvidenceStrip :example="examples[0]"/><p class="landing-caption">先看资料找得对不对，再看回答有没有遵守规则。</p></div>
  </section>

  <section id="results" class="landing-results-band"><div class="landing-container landing-results-layout landing-section">
   <div class="results-preview ui-surface"><div class="results-preview-heading"><div><p class="landing-eyebrow">题目列表</p><h3>模拟电商客服评测</h3></div><span class="illustration-label">静态示意</span></div><p class="results-preview-note">下面是模拟例子，点“查看”展开每题的依据。</p>
    <div class="results-table-scroll"><table class="results-preview-table"><caption class="sr-only">模拟题目的检索结果和回答检查，均为静态示意</caption><thead><tr><th scope="col">题目</th><th scope="col">检索结果</th><th scope="col">回答检查</th><th scope="col">依据</th></tr></thead><tbody><tr v-for="row in examples" :key="row.id" :class="{'is-selected':selectedId===row.id}"><th scope="row"><span>{{row.id}}</span>{{row.question}}</th><td><span class="results-cell-label">检索结果</span><span :class="['preview-status',row.state==='invalid'?'preview-status--invalid':'preview-status--pass']">{{row.retrieval}}</span></td><td><span class="results-cell-label">回答检查</span><span :class="['preview-status','preview-status--'+(row.state==='invalid'?'unchecked':row.state)]">{{row.answerStatus}}</span></td><td><button v-track="{action:'welcome.evidence',placement:'LandingPage.control_07',example_kind:row.exampleKind}" class="preview-evidence-button" :aria-label="'查看示意题 '+row.id+' 的依据'" :aria-pressed="selectedId===row.id" @click="selectedId=row.id">查看 <span aria-hidden="true">↗</span></button></td></tr></tbody></table></div>
    <div v-if="selectedId" class="selected-evidence"><p class="selected-evidence-title">示意题 {{selectedId}} · 对应依据</p><EvidenceStrip :example="selected()" compact/></div><p class="sr-only" role="status">{{selectedId?'当前显示示意题 '+selectedId+' 的依据':'可点击查看每条示意题的依据'}}</p>
   </div>
   <div class="landing-section-heading"><p class="landing-eyebrow">02 / 结果与依据</p><h2 v-track="{action:'welcome.content',placement:'LandingPage.content_results',kind:'view',content:'results'}">分数之外，<br/>看看每一道题发生了什么。</h2><p>同样是没答好，原因可能不同。点开原文和回答，才能知道下一次值得试什么。</p><p class="landing-secondary-copy">没跑完、还没检查的题会单独列出，不会算成答对。</p>
    <button v-if="canContinue" v-track="{action:'site.navigate.evaluate',placement:'LandingPage.control_08',core:true}" class="primary" :disabled="busy" @click="resume">查看我的实验 <span aria-hidden="true">→</span></button><button v-else v-track="{action:'welcome.setup',placement:'LandingPage.control_08',core:true}" class="primary" :disabled="busy" @click="start">连接模型，查看自己的结果 <span aria-hidden="true">→</span></button>
   </div>
  </div></section>

  <section id="project" class="landing-project landing-container landing-section" aria-labelledby="project-title">
   <div class="landing-section-heading"><p class="landing-eyebrow">03 / 项目经历</p><h2 id="project-title" v-track="{action:'welcome.content',placement:'LandingPage.content_project',kind:'view',content:'project'}">把你做过的事，<br/>留成能讲清楚的记录。</h2><p>当时发现了什么，为什么这样改，改完到底怎样。实验结束后，可以整理成复盘，也可以用来准备面试。</p><a v-track="{action:'welcome.section',placement:'LandingPage.control_09'}" class="landing-text-link" href="#project-document">查看项目复盘结构 <span aria-hidden="true">→</span></a><p class="landing-caption">当前材料支持复制与导出 Markdown。个人贡献需要由你核对填写。</p></div>
   <article id="project-document" class="project-document ui-surface" aria-label="项目复盘结构示意"><header><div><p class="landing-eyebrow">项目复盘 / 结构预览</p><h3>一次有依据的客服评测</h3></div><span class="illustration-label">材料示意</span></header><div class="project-document-body"><section><h4>01 项目背景</h4><p>明确模拟客服的业务范围、用户问题与资料边界。</p></section><section><h4>02 评测方法</h4><p>以店铺资料为依据，分别检查资料查找和客服回答。</p></section><section><h4>03 关键发现</h4><p>关联具体问题、规则原文、实际回答与判定理由。</p></section><section><h4>04 优化与回归</h4><p>说明为什么调整，在固定条件下复测，检验判断并保留改善与退化。</p></section><section><h4>05 实际结果和限制</h4><p>引用真实记录，注明无效、无法比较和未验证的范围。</p></section><section><h4>06 个人贡献</h4><p>由你填写实际完成的工作，结合证据生成材料。</p></section></div><footer>结构示意，不是已生成的项目经历。</footer></article>
  </section>

  <section class="landing-closing"><div class="landing-container"><div><p class="landing-eyebrow">从现在开始</p><h2>先看一道题，<br/>再决定怎么改。</h2><p>不需要先准备一整套资料。做完练习，再连接自己的模型试一次。</p></div><button v-if="canContinue" v-track="{action:'site.navigate.evaluate',placement:'LandingPage.control_10',core:true}" class="landing-accent-action" :disabled="busy" @click="resume">继续已有实验 <span aria-hidden="true">→</span></button><button v-else v-track="{action:'welcome.setup',placement:'LandingPage.control_10',core:true}" class="landing-accent-action" :disabled="busy" @click="start">开始评测 <span aria-hidden="true">→</span></button></div></section>
  <footer class="landing-footer landing-container"><div><strong>Agent Eval</strong><p>模拟电商客服评测，不查询真实订单或执行退款。</p></div><nav aria-label="页脚导航"><a v-track="{action:'welcome.section',placement:'LandingPage.control_11'}" href="#workflow">使用流程</a><button v-track="{action:'site.history',placement:'App.control_05'}" class="landing-footer-link" :disabled="busy" @click="emit('history')">历史实验</button><button v-track="{action:'site.statistics',placement:'App.control_12'}" class="landing-footer-link" @click="emit('statistics')">统计设置</button></nav></footer>
 </div>
</template>
