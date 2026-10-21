<script setup>
defineProps({pool:{type:Number,default:20},topK:{type:Number,default:3},rank:Number})
</script>
<template>
 <aside class="rerank-help" aria-label="资料重排原理">
  <p><strong>重排（Rerank）怎么起作用？</strong></p>
  <ol><li>先按本轮检索方式，从知识库找出最多 {{pool}} 段候选资料。</li><li>开启重排后，你配置的模型会对照问题阅读这些候选，按相关性重新排序。</li><li>取新顺序的前 {{topK}} 段，放进回答模型的输入，供它参考。</li></ol>
  <p v-if="rank&&rank>topK">本次初测中，标注的正确资料排第 {{rank}}，前 {{topK}} 条没有它。如果它在候选中，重排可能把它提前；是否有效要看复测结果。</p>
  <p v-else>例如正确资料原排第 6、只取前 3 条时，重排可能把它提到前 3。</p>
  <p>它只调整已有候选的顺序，不能补出没找到的资料，也不保证排对。开启后每题多一次模型请求，会增加耗时与用量。</p>
 </aside>
</template>
<style scoped>
.rerank-help{background:var(--color-canvas,#f5f5f2);border-radius:8px;padding:14px 18px;margin:18px 0;font-size:13px;line-height:1.8}.rerank-help p{margin:6px 0}.rerank-help ol{padding-left:22px;margin:10px 0}
</style>
