<script setup>
import {computed} from 'vue'
import {changeEvidenceSummary,recommendedNextStep} from '../retrieval-change-options.js'
const props=defineProps({view:Object,caseId:String,compact:Boolean})
const emit=defineEmits(['inspect','next'])
const evidence=computed(()=>changeEvidenceSummary(props.view,props.caseId))
const next=computed(()=>recommendedNextStep(props.view,props.caseId))
</script>
<template>
 <section :class="['rag-evidence-summary',{compact}]" aria-label="本题的知识与检索证据">
  <div class="evidence-summary-heading"><strong>{{next.action==='review'?'先选一种改法，再用原题验证':next.title}}</strong><button type="button" class="text-button" @click="emit('inspect')">查看证据 →</button></div>
  <p>{{next.action==='review'?'可以先对照参考答案和实际资料。每次只改一项，观察哪些题变好、哪些题变差。':next.reason}}</p>
  <div v-if="!compact&&next.action==='method'" class="button-row"><button type="button" class="primary" @click="emit('next',next)">{{next.label}} →</button></div>
 </section>
</template>
<style scoped>
.rag-evidence-summary{border-block:1px solid var(--border);padding:20px 0;margin:16px 0 24px}.evidence-summary-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.evidence-summary-heading>strong{font-size:18px}.rag-evidence-summary>p{font-size:15px;line-height:1.8;margin:12px 0}.evidence-summary-stages{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;padding-top:16px}.evidence-summary-stages>div{display:grid;gap:8px}.evidence-summary-stages small,.evidence-summary-stages span{font-size:14px;line-height:1.7;color:var(--muted)}.evidence-summary-stages strong{font-size:15px}.rag-evidence-summary details{margin-top:16px}.compact .evidence-summary-heading>strong{font-size:16px}.compact>p{margin-bottom:8px}@media(max-width:600px){.evidence-summary-stages{grid-template-columns:1fr}.evidence-summary-heading{align-items:flex-start;flex-wrap:wrap}}
</style>
