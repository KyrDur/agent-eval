<script setup>
import {computed} from 'vue'
import {questionLabel} from '../question-navigation.js'
const props=defineProps({items:{type:Array,default:()=>[]},modelValue:String,label:{type:String,default:'题目导航'},compact:Boolean})
const emit=defineEmits(['update:modelValue'])
const index=computed(()=>Math.max(0,props.items.findIndex(c=>c.case_id===props.modelValue)))
function select(i){if(props.items[i])emit('update:modelValue',props.items[i].case_id)}
</script>
<template>
 <nav v-if="items.length" class="question-navigator" :class="{'compact-navigator':compact}" :aria-label="label">
  <div class="question-nav-heading"><strong>{{questionLabel(index+1)}} <span>/ 共 {{items.length}} 题</span></strong><div class="question-arrows"><button type="button" class="text-button" :disabled="index===0" @click="select(index-1)">上一题</button><button type="button" class="text-button" :disabled="index===items.length-1" @click="select(index+1)">下一题</button></div></div>
  <div class="question-numbers"><button v-for="(item,i) in items" :key="item.case_id" type="button" :aria-label="questionLabel(i+1)" :aria-pressed="index===i" :title="item.query" :class="{active:index===i}" @click="select(i)"><span>{{compact?i+1:questionLabel(i+1)}}</span><small v-if="item.status" :class="{'status-failed':['不通过','执行失败','未找到'].includes(item.status)}">{{item.status}}</small></button></div>
 </nav>
</template>
<style scoped>
.question-navigator{margin:20px 0;min-width:0}.question-nav-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.question-nav-heading strong{font-size:15px}.question-nav-heading strong>span{color:var(--muted);font-size:12px;font-weight:400}.question-arrows{display:flex;gap:12px}.question-arrows button{font-size:13px;padding:6px 0}.question-numbers{display:flex;flex-wrap:wrap;gap:8px}.question-numbers button{display:grid;gap:4px;justify-items:center;min-width:64px;padding:10px 10px;border:1px solid var(--color-line,#ddd);border-radius:8px;background:var(--color-surface,#fff);font-size:13px;color:var(--color-text,#282b26)}.question-numbers button.active{background:var(--color-ink,#282b26);border-color:var(--color-ink,#282b26);color:#fff}.question-numbers small{font-size:11px;font-weight:400;opacity:.8}.question-numbers .status-failed{color:#a74435}.question-numbers .active small{color:inherit}.question-numbers button:focus-visible{outline:2px solid #52725e;outline-offset:3px}@media(max-width:600px){.question-numbers{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))}.question-numbers button{min-width:0;padding:10px 4px}.question-nav-heading strong>span{display:block;margin-top:3px}}
</style>

<style scoped>.compact-navigator .question-numbers button{min-width:36px;min-height:34px;padding:6px 9px}.compact-navigator .question-numbers{display:flex;gap:6px}.compact-navigator .question-nav-heading{margin-bottom:10px}.compact-navigator .question-nav-heading strong{font-size:12px}.compact-navigator .question-nav-heading .text-button{min-height:28px;font-size:11px}</style>
