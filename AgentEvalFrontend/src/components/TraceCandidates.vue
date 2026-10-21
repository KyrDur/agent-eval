<script setup>
defineProps({items:{type:Array,default:()=>[]},returned:{type:Array,default:()=>[]},relevantIds:{type:Array,default:()=>[]}})
const score=value=>typeof value==='number'?value.toFixed(4):'未记录'
</script>
<template>
 <ol class="trace-candidates"><li v-for="(item,i) in items" :key="item.chunk_id||i"><div class="candidate-heading"><strong>#{{item.rank||i+1}} · {{item.title||item.document_id||'资料片段'}}</strong><span v-if="returned.some(r=>r.chunk_id===item.chunk_id)" title="这是检索最终选中的资料。生成回答时会作为参考，不代表模型一定采用或答对。">选为回答参考</span><span v-if="relevantIds.includes(item.document_id)||relevantIds.includes(item.chunk_id)">命中标注</span></div><p class="candidate-score">检索相似度 {{score(item.score)}}<template v-if="item.rerank_score!=null"> · 重排分数 {{score(item.rerank_score)}}</template></p><p class="candidate-preview">{{item.text?.slice(0,180)}}{{item.text?.length>180?'…':''}}</p><details><summary>片段全文与标识</summary><p class="candidate-full">{{item.text}}</p><p class="candidate-id">文档 {{item.document_id||'未记录'}} · 片段 {{item.chunk_id||'未记录'}} · 距离 {{score(item.distance)}}</p></details></li></ol><p v-if="!items.length" class="trace-empty">本步骤没有保存资料片段。</p>
</template>
<style scoped>
.trace-candidates{padding:0;list-style:none;margin:14px 0;display:grid;gap:12px}.trace-candidates>li{border:1px solid var(--color-line,#ddd);border-radius:8px;padding:14px;min-width:0}.candidate-heading{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:13px}.candidate-heading span{font-size:10px;padding:3px 6px;background:var(--color-canvas,#f5f5f2);border-radius:4px}.candidate-score,.candidate-id,.trace-empty{font-size:11px;color:var(--muted);overflow-wrap:anywhere}.candidate-preview,.candidate-full{font-size:13px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere}.trace-candidates details{font-size:12px}.trace-candidates summary{cursor:pointer}
</style>
