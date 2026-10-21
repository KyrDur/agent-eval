<script setup>
defineProps({example:{type:Object,required:true},compact:Boolean})
</script>
<template>
 <ol class="evidence-strip" :class="{'evidence-strip--compact':compact}" aria-label="测试问题、规则依据、客服回答与检查结论">
  <li class="evidence-strip__item"><div class="evidence-strip__label"><span aria-hidden="true">01</span><strong>测试问题</strong></div><p>{{example.question}}</p></li>
  <li class="evidence-strip__item"><div class="evidence-strip__label"><span aria-hidden="true">02</span><strong>规则依据</strong></div><p>{{example.rule}}</p><small>{{example.source}}</small></li>
  <li class="evidence-strip__item"><div class="evidence-strip__label"><span aria-hidden="true">03</span><strong>客服回答</strong></div><p :class="{'evidence-strip__answer':example.answer}">{{example.answer || '未取得回答'}}</p></li>
  <li class="evidence-strip__item evidence-strip__verdict" :class="'evidence-strip__verdict--'+example.state"><div class="evidence-strip__label"><span aria-hidden="true">04</span><strong>检查结论</strong></div><p class="evidence-strip__status">{{example.verdict}}</p><p>{{example.reason}}</p></li>
 </ol>
</template>
