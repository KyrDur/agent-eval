<script setup>
import {computed} from 'vue'
import {renderMarkdown} from '../markdown.js'
const props=defineProps({source:{type:String,default:''}})
const rendered=computed(()=>renderMarkdown(props.source))
</script>
<template><div class="markdown-content" v-html="rendered" /></template>
<style scoped>
.markdown-content{min-width:0;max-width:100%;font-size:inherit;line-height:1.85;white-space:normal;overflow-wrap:anywhere;color:inherit}
.markdown-content :deep(> :first-child){margin-top:0}.markdown-content :deep(> :last-child){margin-bottom:0}
.markdown-content :deep(p){margin:0 0 .85em;font-size:inherit;line-height:inherit;white-space:normal}
.markdown-content :deep(h1),.markdown-content :deep(h2),.markdown-content :deep(h3),.markdown-content :deep(h4),.markdown-content :deep(h5),.markdown-content :deep(h6){margin:1.2em 0 .55em;font-weight:650;line-height:1.5;color:inherit}
.markdown-content :deep(h1){font-size:1.4em}.markdown-content :deep(h2){font-size:1.25em}.markdown-content :deep(h3){font-size:1.12em}.markdown-content :deep(h4),.markdown-content :deep(h5),.markdown-content :deep(h6){font-size:1em}
.markdown-content :deep(strong){font-weight:700}.markdown-content :deep(ul),.markdown-content :deep(ol){display:block;list-style-position:outside;padding-left:1.6em;margin:.7em 0 1em}
.markdown-content :deep(ul){list-style-type:disc}.markdown-content :deep(ol){list-style-type:decimal}.markdown-content :deep(li){display:list-item;margin:.35em 0;padding-left:.15em;line-height:inherit}.markdown-content :deep(li>p){margin:.3em 0}
.markdown-content :deep(blockquote){margin:.9em 0;padding:.5em 1em;border-left:3px solid #a1ae91;background:#f2f4ed;color:inherit;white-space:normal}
.markdown-content :deep(code){font-size:.9em;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:#e9ece480;padding:.15em .35em;border-radius:4px}
.markdown-content :deep(pre){margin:.9em 0;padding:14px 16px;border:1px solid #dce1d7;border-radius:8px;background:#f4f5f0;overflow-x:auto;white-space:pre;overflow-wrap:normal;line-height:1.65;font-size:.9em;max-width:100%}.markdown-content :deep(pre code){padding:0;background:none;font-size:inherit;white-space:pre}
.markdown-content :deep(a){color:#315f9a;text-decoration:underline;text-underline-offset:3px}.markdown-content :deep(a:focus-visible){outline:2px solid #4779bd;outline-offset:3px}
.markdown-content :deep(.markdown-table-scroll){max-width:100%;overflow-x:auto;margin:1em 0}.markdown-content :deep(table){border-collapse:collapse;width:100%;font-size:.95em;line-height:1.65}.markdown-content :deep(th),.markdown-content :deep(td){border:1px solid #dce1d7;padding:9px 12px;min-width:100px;text-align:left;vertical-align:top}.markdown-content :deep(th){background:#edf1e7;font-weight:650}.markdown-content :deep(hr){border:0;border-top:1px solid #dce1d7;margin:1.2em 0}
</style>
