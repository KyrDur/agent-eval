<script setup>
import {computed} from 'vue'
const props=defineProps({row:Object,view:Object})
const emit=defineEmits(['review','answer-setup','logs','inspect-source'])
const contexts=computed(()=>props.row?.results||[])
</script>
<template>
 <section class="evidence-path" aria-label="本题使用的资料">
  <p>{{contexts.length?`这题参考了 ${contexts.length} 段资料，可以对照原文查看是否漏掉条件。`:'这份记录没有保存可用的参考片段。'}}</p>
  <div class="button-row"><button type="button" class="secondary" @click="emit('inspect-source')">查看参考资料</button><button type="button" class="text-button" @click="emit('logs')">完整运行日志</button></div>
 </section>
</template>
<style scoped>.evidence-path{padding:16px;margin:16px 0;border:1px solid var(--border);border-radius:8px;background:var(--color-canvas)}.evidence-path p{font-size:14px;line-height:1.8;margin:0 0 12px}</style>
