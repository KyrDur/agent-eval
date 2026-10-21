<script setup>
import {computed} from 'vue'
import {writingExample,optimizationExamples,optimizationExample} from '../learning-example.js'
const props=defineProps({stage:{type:String,required:true},kept:Boolean,methodId:{type:String,default:'RERANK_TOGGLE'}})
const emit=defineEmits(['update:methodId'])
const sample=computed(()=>optimizationExample(props.methodId))
const rows=computed(()=>writingExample(props.stage,props.kept,props.methodId))
</script>
<template>
 <aside class="writing-example" aria-label="填写示范"><div class="writing-example-heading"><strong>参考写法 · {{sample.title}}</strong><label>示范改法<select :value="sample.id" @change="emit('update:methodId',$event.target.value)"><option v-for="method in optimizationExamples" :key="method.id" :value="method.id">{{method.title}}</option></select></label></div><p class="writing-example-intro">这是另一道预设题的写法，不是当前题的答案。</p><dl><div v-for="[label,text] in rows" :key="label"><dt>{{label}}</dt><dd>{{text}}</dd></div></dl></aside>
</template>
<style scoped>
.writing-example{margin:20px 0;padding:17px 19px;border:1px solid var(--border);border-radius:8px;background:var(--color-canvas)}.writing-example-heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.writing-example-heading strong{font-size:13px}.writing-example-heading label{display:flex;align-items:center;gap:8px;font-size:10px;color:var(--muted);margin:0;flex-shrink:0}.writing-example-heading select{width:auto;max-width:180px;min-height:32px;padding:5px 8px;font-size:11px}.writing-example-intro{font-size:11px;color:var(--muted);margin:8px 0 0!important}.writing-example dl{margin:14px 0 0;display:grid;gap:12px}.writing-example dt{font-size:11px;color:var(--muted);margin-bottom:4px}.writing-example dd{margin:0;font-size:13px;line-height:1.85}@media(max-width:650px){.writing-example-heading{display:block}.writing-example-heading label{margin-top:10px}.writing-example{padding:15px}.writing-example dd{font-size:12px}}
</style>
