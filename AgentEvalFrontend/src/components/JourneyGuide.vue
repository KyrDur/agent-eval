<script setup>
import { computed, inject, ref } from 'vue'
import { journey, nextJourneyStep, evaluationIssueTypes } from '../journey-guidance.js'
const props=defineProps({step:String,opened:Boolean})
const emit=defineEmits(['navigate'])
const work=inject('workspace'),rag=inject('retrieval')
const expanded=ref(props.opened),showRoute=ref(false)
const reveal=ref(expanded.value?'automatic':'unknown')
function toggleExplanation(){expanded.value=!expanded.value;if(expanded.value)reveal.value='manual'}
const current=computed(()=>journey.find(s=>s.id===props.step))
const next=computed(()=>nextJourneyStep(work.state.session,rag.state))
</script>
<template>
 <section class="journey-guide" aria-label="操作引导">
  <div class="guide-heading"><div><p class="guide-kicker">{{current?'这一步要做什么':'从这里开始'}}</p><h2>{{current?.goal || '选好模型和资料，看看客服会怎么答。'}}</h2></div><button v-track="{action:'guide.expand',placement:'JourneyGuide.control_01'}" class="text-button" :aria-expanded="expanded" @click="toggleExplanation">{{expanded?'收起帮助':'需要帮助？'}} <span aria-hidden="true">{{expanded?'−':'＋'}}</span></button></div>
  <div v-if="expanded" class="guide-body">
   <ol v-if="current" class="guide-steps"><li v-for="(text,i) in current.steps" :key="text"><span>{{i+1}}</span><p>{{text}}</p></li></ol>
   <p v-else>用自己的模型评测现成的电商知识问答 Agent。可以先使用示例知识和测试题，再核对标准、选择修改；系统保存真实结果，帮助你整理项目复盘、简历草稿和面试材料。</p>
   <p v-if="current" class="guide-tip">{{current.tip}}</p>
   <section v-if="step==='evaluate'" class="guide-issue-types" aria-labelledby="guide-issue-title">
    <h3 id="guide-issue-title">常见错误：先看出在哪一步</h3>
    <p>下面是帮助你分析的例子，不是本次实验的错误统计。回答类问题需要开启最终回答检查，再核对原文与判定。</p>
    <dl><div v-for="issue in evaluationIssueTypes" :key="issue.title"><dt v-track="{action:'guide.issue',placement:'JourneyGuide.issue',kind:'view',issue_kind:issue.kind,reveal:reveal}"><span>{{issue.stage}}</span>{{issue.title}}</dt><dd><p>{{issue.example}}</p><p class="guide-issue-inspect">看哪里：{{issue.inspect}}</p></dd></div></dl>
    <div class="guide-execution-status"><h4>这两种情况，先不要当作答错</h4><p><strong>执行无效（INVALID）：</strong>连接失败、超时或模型请求异常等，可能导致本次没有有效结果。先排除执行问题，再重新评测。</p><p><strong>未检查：</strong>没有开启最终回答验证时，结果只能说明资料查找的表现，不能据此判断客服回答正确或错误。</p></div>
   </section>
   <div class="button-row"><button v-track="{action:'guide.next.'+next.id,placement:'JourneyGuide.control_02'}" v-if="!current" class="primary" :disabled="!!work.state.busy" @click="emit('navigate',next.id)">{{next.label}} →</button><button v-track="{action:'guide.route',placement:'JourneyGuide.control_03'}" class="text-button" :aria-expanded="showRoute" @click="showRoute=!showRoute">{{showRoute?'收起完整流程':'查看完整使用流程'}} →</button></div>
   <ol v-if="showRoute" class="journey-route"><li v-for="(stage,i) in journey" :key="stage.id"><span>{{i+1}}</span><div><button v-track="{action:'guide.navigate.'+stage.id,placement:'JourneyGuide.control_04'}" class="text-button" :disabled="!!work.state.busy" @click="emit('navigate',stage.id)">{{stage.label}} →</button><p>{{stage.goal}}</p></div></li></ol>
   <details class="guide-glossary"><summary v-track="{action:'guide.help',placement:'JourneyGuide.control_05'}">几个容易混淆的词</summary><dl><dt>知识与索引</dt><dd>知识是原始资料；索引是用这份资料建立的检索表示。先保存，再建索引，才能用于评测和聊天。</dd><dt>Embedding 与聊天模型</dt><dd>Embedding 负责找相关知识；聊天模型负责回答。本地 MiniLM 不消耗聊天 API 调用额度。</dd><dt>Baseline / Retest</dt><dd>第一次评测／修改后的同题复测。比较时必须核对冻结条件。</dd><dt>Judge / INVALID</dt><dd>Judge 是检查回答的模型，判定仍需核验。INVALID 是执行或采集无效，不能当作质量失败。</dd></dl></details>
  </div>
 </section>
</template>
