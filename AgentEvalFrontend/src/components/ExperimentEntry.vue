<script setup>
import PaperIllustration from './PaperIllustration.vue'
import WorkspaceIcon from './WorkspaceIcon.vue'
defineProps({entry:Object,busy:Boolean})
defineEmits(['fresh','resume','history','cancel'])
</script>
<template>
 <section class="experiment-entry" aria-labelledby="experiment-entry-title">
  <PaperIllustration /><span class="eyebrow">我的工作台</span>
  <h1 id="experiment-entry-title">这次从哪里开始？</h1>
  <p class="muted">由你选择要打开的实验，进入页面时不会自动读取旧记录。</p>
  <div v-if="entry.loading" class="panel entry-loading" role="status"><span class="spinner small"/><div><strong>正在读取你选择的实验</strong><p class="muted">最多等待 20 秒，也可以随时取消。</p></div><button type="button" class="secondary" @click="$emit('cancel')">取消读取</button></div>
  <div v-if="entry.error" class="note danger" role="alert"><strong>{{entry.error.title}}</strong><p>{{entry.error.message}}</p></div>
  <div class="entry-options">
   <article class="panel"><span class="entry-art"><WorkspaceIcon name="plus" :size="30"/></span><h2>开始新实验</h2><p class="muted">从连接模型开始，旧实验仍保存在历史记录中。</p><button type="button" class="primary" :disabled="busy" @click="$emit('fresh')">开始新实验</button></article>
   <article class="panel"><span class="entry-art"><WorkspaceIcon name="history" :size="30"/></span><h2>继续之前的实验</h2><p class="muted">{{entry.hasSaved?'读取此浏览器上次使用的实验，恢复后显示当前下一步与连接阻塞。':'此浏览器没有记住上次的实验，可以从历史记录中选择。'}}</p><button type="button" class="secondary" :disabled="busy||entry.loading||!entry.hasSaved" @click="$emit('resume')">继续上次实验</button><button type="button" class="text-button" :disabled="busy||entry.loading" @click="$emit('history')">从历史实验中选择 →</button></article>
  </div>
 </section>
</template>
<style scoped>
.experiment-entry{max-width:960px;margin:24px auto}.experiment-entry>h1{margin:12px 0}.entry-options{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px;margin-top:30px}.entry-options .panel{display:flex;flex-direction:column;align-items:flex-start;padding:30px}.entry-art{display:grid;place-items:center;background:#edf0e7;border-radius:15px;width:64px;height:64px;color:#77876b;margin-bottom:16px}.entry-options h2{font-size:21px;margin:6px 0}.entry-options p{flex:1;line-height:1.8;margin:8px 0 24px}.entry-options .text-button{margin-top:14px}.entry-loading{display:flex;align-items:center;gap:15px;margin-top:24px}.entry-loading>div{flex:1}.entry-loading p{margin:6px 0 0;font-size:13px}@media(max-width:650px){.entry-options{grid-template-columns:1fr;gap:14px;margin-top:22px}.entry-options .panel{padding:24px}.entry-loading{flex-wrap:wrap}.experiment-entry{margin-top:12px}}
</style>
