<script setup>
import {inject,ref,computed} from 'vue'
import {api} from '../api.js'
const rag=inject('retrieval'),work=inject('workspace'),pack=ref(null),error=ref('')
const selected=computed(()=>rag.state.knowledge?.metadata?.pack_id==='rag-policy-v1')
async function load(){try{pack.value=await api.get('/rag-policy-pack')}catch(e){error.value=e.message}}
async function save(){await rag.saveKnowledge({name:pack.value.name,documents:pack.value.documents,metadata:{pack_id:pack.value.pack_id,source:pack.value.source,review_status:pack.value.review_status}});if(!work.state.error)await rag.buildIndex({chunk_size:200,chunk_overlap:20,algorithm:'normalized-character-window-v1'},'all-MiniLM-L6-v2')}
async function tests(){if(!pack.value)await load();if(pack.value)await rag.saveEvalset({name:'完整政策包 · 16 个开发题族（待审）',cases:pack.value.debug_cases,split_reviewed:false})}
</script>
<template><details class="panel"><summary @click="!pack&&load()">完整政策实验包（模拟资料，待人工审核）</summary><template v-if="pack"><p>{{pack.notice}}</p><p>{{pack.documents.length}} 份政策 · {{pack.debug_cases.length}} 个开发题族 · {{pack.holdout_count}} 个保留题族草稿。保留题未展示，当前不能声称通过保留验证。</p><ul><li v-for="d in pack.documents" :key="d.document_id">{{d.title}}</li></ul><div class="button-row"><button class="secondary" :disabled="!!work.state.busy" v-track="{action:'rag.policy.load',placement:'RagUpgrade.control'}" @click="save">另存完整知识包并准备索引</button><button class="secondary" :disabled="!!work.state.busy||!selected||!rag.state.index||rag.state.index.knowledge_dataset_id!==rag.state.knowledge.knowledge_dataset_id" v-track="{action:'rag.policy.tests',placement:'RagUpgrade.control'}" @click="tests">载入 16 道待审开发题</button></div><p class="muted">会建立新的知识与题集；原实验仍可从历史读取。载入后请在测试题中审核事实映射，再决定是否作为人工参照。</p></template><p role="status">{{error}}</p></details></template>
