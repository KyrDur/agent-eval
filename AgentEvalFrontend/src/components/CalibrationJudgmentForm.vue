<script setup>
import {computed} from 'vue'
import {dimensionLabels,labelFor,localFragments,verdictFor,judgmentProblems} from '../calibration-presentation.js'
const value=defineModel({type:Object,required:true})
const props=defineProps({sample:Object,rubric:Object,fragments:Array,submitLabel:{type:String,default:'提交标注'},disabled:Boolean})
const emit=defineEmits(['submit'])
const fragments=computed(()=>props.fragments||localFragments(props.sample))
const answers=computed(()=>fragments.value.filter(f=>f.scope==='ANSWER'))
const evidence=computed(()=>fragments.value.filter(f=>f.scope!=='ANSWER'))
const problems=computed(()=>judgmentProblems(value.value,props.sample,props.rubric))
const verdict=computed(()=>verdictFor(value.value,props.rubric))
const lines=text=>text.split('\n').map(s=>s.trim()).filter(Boolean)
function selected(d,f){return f.scope==='ANSWER'?d.answer_quotes.includes(f.text):d.citations.some(c=>c.scope===f.scope&&c.evidence_id===f.evidence_id&&c.quote===f.text)}
function toggle(d,f){
  if(f.scope==='ANSWER')d.answer_quotes=selected(d,f)?d.answer_quotes.filter(t=>t!==f.text):[...d.answer_quotes,f.text]
  else d.citations=selected(d,f)?d.citations.filter(c=>!(c.scope===f.scope&&c.evidence_id===f.evidence_id&&c.quote===f.text)):
    [...d.citations,{scope:f.scope,evidence_id:f.evidence_id,quote:f.text}]
}
function submit(){if(!problems.value.length)emit('submit',{...value.value,verdict:verdict.value})}
</script>
<template>
  <form class="cal-judgment-form" @submit.prevent="submit">
    <p class="note">先选分数，再点选支持判断的回答和政策原文。缺少资料可选“证据不足”。回答诚实与用户问题是否解决要分别判断。</p>
    <section v-for="(d,key) in value.dimensions" :key="key" class="cal-rubric" :data-dimension="key">
      <h3>{{dimensionLabels[key]}}</h3>
      <div class="cal-score-anchors"><span v-for="level in ['0','1','2']" :key="level"><b>{{level}} 分</b> {{rubric.dimensions[key].anchors[level]}}</span></div>
      <p class="muted">边界：{{rubric.dimensions[key].boundary}}</p>
      <div class="two-column"><label>{{dimensionLabels[key]}}评分<select v-model="d.score"><option :value="0">0 分</option><option :value="1">1 分</option><option :value="2">2 分</option><option value="INSUFFICIENT">证据不足</option><option v-if="rubric.rules.na_allowed.includes(key)" value="NA">不适用</option></select></label><label>简短理由<textarea v-model="d.reason" rows="2" required /></label></div>
      <details class="cal-fragment-picker"><summary>点选回答原文 · 已选 {{d.answer_quotes.length}} 段</summary><button v-for="f in answers" :key="f.fragment_id" type="button" class="cal-fragment" :class="{selected:selected(d,f)}" :aria-pressed="selected(d,f)" @click="toggle(d,f)">{{f.text}}</button></details>
      <details class="cal-fragment-picker"><summary>点选政策依据 · 已选 {{d.citations.length}} 段</summary><p v-if="!evidence.length" class="empty">本题没有可用政策，按实际情况选择证据不足。</p><button v-for="f in evidence" :key="f.fragment_id" type="button" class="cal-fragment" :class="{selected:selected(d,f)}" :aria-pressed="selected(d,f)" @click="toggle(d,f)"><small>{{f.scope==='RETRIEVED'?'当时检索资料':'完整参考政策'}} · {{f.evidence_id}}</small>{{f.text}}</button></details>
      <div v-if="d.answer_quotes.length||d.citations.length" class="cal-selected-quotes"><p v-for="(q,i) in d.answer_quotes" :key="'a'+i">回答：{{q}} <button type="button" class="text-button" @click="d.answer_quotes.splice(i,1)">移除</button></p><p v-for="(c,i) in d.citations" :key="'c'+i">{{c.scope==='RETRIEVED'?'检索资料':'参考政策'}}：{{c.quote}} <button type="button" class="text-button" @click="d.citations.splice(i,1)">移除</button></p></div>
    </section>
    <div class="two-column"><label>用户问题是否解决<select v-model="value.task_resolved" aria-label="用户问题是否解决"><option value="YES">是</option><option value="NO">否</option><option value="INSUFFICIENT">无法评价</option></select></label><label>是否忠于可用证据<select v-model="value.faithful_to_available" aria-label="是否忠于可用证据"><option value="YES">是</option><option value="NO">否</option><option value="INSUFFICIENT">证据不足</option></select></label></div>
    <p class="muted">“没有编造”不代表“问题已解决”；诚实说明不知道，也可能留下未解决的任务。</p>
    <label v-for="(label,key) in rubric.critical_errors" :key="key" class="check"><input v-model="value.critical_errors" type="checkbox" :value="key" />{{label}}</label>
    <label>任务失败原因 · 每行一项<textarea :value="value.task_failure_reasons.join('\n')" rows="2" @input="value.task_failure_reasons=lines($event.target.value)" placeholder="例如：检索没有提供必要政策" /></label>
    <label>回答错误标签 · 每行一项<textarea :value="value.error_tags.join('\n')" rows="2" @input="value.error_tags=lines($event.target.value)" /></label>
    <label>证据不足项 · 每行一项<textarea :value="value.insufficient_items.join('\n')" rows="2" @input="value.insufficient_items=lines($event.target.value)" /></label>
    <label>总理由<textarea v-model="value.reason" rows="3" required /></label>
    <slot />
    <p class="note">按当前评分细则，判定为：<strong>{{labelFor(verdict)}}</strong>。该判定来自上面填写的分数和严重错误。</p>
    <details v-if="problems.length" class="cal-form-problems"><summary>提交前还需填写 {{problems.length}} 项</summary><ul><li v-for="problem in problems" :key="problem">{{problem}}</li></ul></details>
    <button class="primary" type="submit" :disabled="disabled||problems.length>0">{{submitLabel}}</button>
  </form>
</template>
