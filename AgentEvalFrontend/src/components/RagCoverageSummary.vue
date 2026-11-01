<script setup>
defineProps({comparison:Object,summary:Object})
const names={knowledge:'库内原文',chunks:'索引片段',candidates:'候选召回',selected:'选中片段',context:'实际上下文'}
const percent=v=>v==null?'不可计算':(v*100).toFixed(1)+'%'
</script>
<template><section class="panel"><h3>必要事实的原文包含情况</h3><p class="muted">仅计算已审核且可检查的题。原文包含不等于语义正确或业务任务完成；未审核、冲突、失败与历史缺失记录保留为不可计算。</p><div class="table-scroll"><table><thead><tr><th>阶段</th><th>初测</th><th v-if="comparison">复测</th><th>有效题 / 范围</th><th v-if="comparison">改善 / 退化</th></tr></thead><tbody><tr v-for="(label,key) in names" :key="key"><td>{{label}}</td><template v-if="comparison"><td>{{percent(comparison.stages[key]?.baseline_mean)}}</td><td>{{percent(comparison.stages[key]?.retest_mean)}}</td><td>{{comparison.stages[key]?.common_confirmed_cases??0}} 道共同已审核题</td><td>{{comparison.stages[key]?.improved_count??0}} / {{comparison.stages[key]?.regressed_count??0}}</td></template><template v-else><td>{{percent(summary?.stages[key]?.mean_inclusion)}}</td><td>{{summary?.stages[key]?.confirmed_eligible_count??0}} / {{summary?.stages[key]?.total_case_count??0}}</td></template></tr></tbody></table></div></section></template>
<style scoped>.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;border-bottom:1px solid var(--border);padding:10px;white-space:nowrap}</style>
