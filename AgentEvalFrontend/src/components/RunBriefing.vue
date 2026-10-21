<script setup>
import { computed } from 'vue'
import { runBriefing } from '../journey-guidance.js'
import { embeddingLabel } from '../embedding-models.js'
const props=defineProps({session:Object,index:Object,cases:Array,config:Object,verifyAnswers:Boolean})
const brief=computed(()=>runBriefing(props))
</script>
<template>
 <section class="run-briefing" aria-label="运行前确认"><h3>{{brief.count}} 道题，这次会这样评</h3>
  <ol class="briefing-process"><li><strong>找资料</strong><span>每题从知识库取前 {{config?.top_k}} 条相关内容</span></li><template v-if="verifyAnswers"><li><strong>Agent 回答</strong><span>根据找到的资料生成回复</span></li><li><strong>检查回答</strong><span>评分模型对照原文，检查回答是否正确</span></li></template><li v-else><strong>检查查找结果</strong><span>对照每题标注，检查是否找到了正确资料</span></li></ol>
  <p class="call-estimate">预计调用模型 <strong>{{brief.totalCalls}}</strong> 次<template v-if="verifyAnswers">（回答 {{brief.calls.agent}} 次，评分 {{brief.calls.judge}} 次<template v-if="brief.calls.rewrite+brief.calls.rerank">，改写与排序 {{brief.calls.rewrite+brief.calls.rerank}} 次</template>）</template></p>
  <details class="briefing-details"><summary>模型、用量与设置</summary><dl class="briefing-facts"><div><dt>回答模型</dt><dd>{{verifyAnswers?brief.answerModel:'本次只查资料'}}</dd></div><div v-if="verifyAnswers"><dt>评分模型</dt><dd>{{brief.judgeModel}}</dd></div><div><dt>知识版本</dt><dd>v{{brief.knowledgeVersion ?? '尚未建立'}} · {{embeddingLabel(index)}}</dd></div><div><dt>查找设置</dt><dd>查询改写{{config?.query_rewrite?'开启':'关闭'}} · 结果重排{{config?.rerank?'开启':'关闭'}}</dd></div></dl><p class="muted">按每题成功调用一次估算，重试会增加调用。费用按模型服务商的实际用量计算。</p></details>
  <p v-if="brief.budget!=null && brief.totalCalls>brief.budget" class="note warning">预计请求数超过本次配置的 {{brief.budget}} 次调用上限，请减少范围或到模型高级设置调整预算。</p>
 </section>
</template>
<style scoped>
.briefing-process{list-style:none;padding:0;display:flex;gap:20px;counter-reset:step}.briefing-process li{flex:1;min-width:0;counter-increment:step}.briefing-process strong{display:block;font-size:14px}.briefing-process strong:before{content:counter(step) ' · ';color:var(--muted)}.briefing-process span{display:block;font-size:12px;color:var(--muted);line-height:1.7;margin-top:6px}.briefing-details{font-size:13px;margin-top:16px}.briefing-details summary{cursor:pointer}.briefing-facts{margin-top:16px}.briefing-details .muted{font-size:12px;line-height:1.7}@media(max-width:600px){.briefing-process{display:grid;gap:14px}}
</style>
