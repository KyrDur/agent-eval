<script setup>
import {computed,ref} from 'vue'
import {sourcePassages,samePassage} from '../source-passages.js'
const props=defineProps({documents:{type:Array,default:()=>[]},modelValue:{type:Array,default:()=>[]},version:Number,allowAlternatives:{type:Boolean,default:true}})
const emit=defineEmits(['update:modelValue'])
const activeGroup=ref(0),docId=ref('')
const groups=computed(()=>props.modelValue.length?props.modelValue:[[]])
const passages=computed(()=>sourcePassages(props.documents).filter(p=>!docId.value||p.document_id===docId.value))
function pick(p){const next=groups.value.map(a=>a.map(x=>({...x}))),group=next[activeGroup.value]||next[0],at=group.findIndex(x=>samePassage(x,p));if(at>=0)group.splice(at,1);else {const {title,...ref}=p;group.push({...ref,knowledge_version:props.version??null})}emit('update:modelValue',next)}
function addGroup(){emit('update:modelValue',[...groups.value,[]]);activeGroup.value=groups.value.length}
function removeGroup(i){const next=groups.value.filter((_,j)=>i!==j);emit('update:modelValue',next);activeGroup.value=0}
function remove(i,j){const next=groups.value.map(a=>[...a]);next[i].splice(j,1);emit('update:modelValue',next)}
</script>
<template>
 <div class="source-picker">
  <p>同一组内的原文需共同支持要点；不同组是可替代的依据。选择时保留必要条件与例外。</p>
  <div class="source-groups"><article v-for="(group,i) in groups" :key="i"><div class="section-heading"><button type="button" class="text-button" :aria-pressed="activeGroup===i" @click="activeGroup=i">{{i?'或：另一组依据':'一组联合依据'}} {{i+1}}</button><button v-if="groups.length>1" type="button" class="text-button" @click="removeGroup(i)">移除此组</button></div><blockquote v-for="(q,j) in group" :key="j"><small>{{q.document_id}} · {{q.knowledge_version?'v'+q.knowledge_version:'原记录版本'}} · {{q.source_start??'位置未记录'}}–{{q.source_end??'位置未记录'}}</small><p>{{q.quote}}</p><button type="button" class="text-button" @click="remove(i,j)">移除此段</button></blockquote><p v-if="!group.length">从下方选择原文加入第 {{i+1}} 组。</p></article></div>
  <button v-if="allowAlternatives" type="button" class="secondary" :disabled="groups.length>=12" @click="addGroup">添加可替代的一组依据</button>
  <label>选择来源文档<select v-model="docId"><option value="">全部文档</option><option v-for="d in documents" :key="d.document_id" :value="d.document_id">{{d.title||d.document_id}}</option></select></label>
  <div class="source-options" aria-label="选择政策原文"><button v-for="(p,i) in passages" :key="p.document_id+':'+p.source_start" type="button" :aria-pressed="groups[activeGroup]?.some(q=>samePassage(p,q))||false" @click="pick(p)"><small>{{p.title}} · 原文 {{p.source_start}}–{{p.source_end}}</small><span>{{p.quote}}</span></button><p v-if="!passages.length">本版本没有可选择的政策原文。</p></div>
 </div>
</template>
<style scoped>.source-picker p{font-size:14px;line-height:1.8}.source-groups>article{padding:12px 0;border-bottom:1px solid var(--border);margin-bottom:16px}.source-groups button[aria-pressed=true]{font-weight:700;text-decoration:underline}.source-picker blockquote{margin:12px 0;padding:12px 16px;border-left:3px solid var(--color-primary);background:var(--color-canvas)}.source-picker small{font-size:12px;color:var(--muted)}.source-picker blockquote p{white-space:pre-wrap;margin:8px 0}.source-options{max-height:370px;overflow:auto;display:grid;gap:8px;margin:16px 0}.source-options>button{text-align:left;border:1px solid var(--border);border-radius:6px;padding:14px;background:var(--color-surface)}.source-options>button[aria-pressed=true]{border:2px solid var(--color-primary);background:var(--color-success-surface)}.source-options span{display:block;font-size:14px;white-space:pre-wrap;line-height:1.8;margin-top:8px}.source-picker label{font-size:14px;margin:20px 0}.source-picker select{max-width:100%;width:100%}</style>
