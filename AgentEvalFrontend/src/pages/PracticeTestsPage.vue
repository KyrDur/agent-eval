<script setup>
import {api} from '../api.js'
import {analytics} from '../analytics.js'
import { cloneArtifact } from '../practice-data.js'
import { computed, inject, ref, watch } from 'vue'
import QuestionNavigator from '../components/QuestionNavigator.vue'
import WorkspaceIcon from '../components/WorkspaceIcon.vue'
import WorkspaceDrawer from '../components/WorkspaceDrawer.vue'
import {excerpt} from '../visual-results.js'
import {selectedQuestion,questionLabel} from '../question-navigation.js'
import { demoCases } from '../rag-demo.js'
import TestGenerator from '../components/TestGenerator.vue'
import ScenarioRuleEditor from '../components/ScenarioRuleEditor.vue'
import {appendGeneratedCases} from '../ai-assistance.js'
const work=inject('workspace'),rag=inject('retrieval'),practice=inject('practice'),error=ref(''),confirmed=ref(false)
const splitReviewed=ref(false),panel=ref('')
async function suggestGroups(){try{const result=await api.post('/retrieval-case-groups',{cases:cases.value});cases.value=result.cases;splitReviewed.value=false;error.value=result.conflicts.length?'有同组题跨越调试/保留分区，请调整分区。':''}catch(e){error.value=e.message}}
const name=ref(rag.state.evalSet?.name || '我的电商 Agent 测试')
const localEdits=ref(false)
const cases=ref(cloneArtifact(rag.state.evalSet?.cases || []).map(c=>({...c,partition:c.partition||'DEBUG'})))
watch(()=>rag.state.evalSet,evalSet=>{if(!evalSet||localEdits.value)return;name.value=evalSet.name;cases.value=cloneArtifact(evalSet.cases||[]).map(c=>({...c,partition:c.partition||'DEBUG'}));for(const draft of practice.state.drafts)if(!cases.value.some(c=>c.case_id===draft.case_id))cases.value.push(cloneArtifact(draft))})
for(const draft of practice.state.drafts)if(!cases.value.some(c=>c.case_id===draft.case_id))cases.value.push(cloneArtifact(draft))
const editorKeys=new WeakMap()
function editorKey(c){if(!editorKeys.has(c))editorKeys.set(c,crypto.randomUUID());return editorKeys.get(c)}
const activeId=ref(''),current=computed(()=>selectedQuestion(cases.value,activeId.value))
const displayedCases=computed(()=>current.value?[current.value]:[])
const currentIndex=computed(()=>cases.value.indexOf(current.value))
const form=computed(()=>cases.value.map(c=>({...c,partition:c.partition||'DEBUG',relevant_document_ids:c.relevant_document_ids||[],must_do:c.must_do||[],must_not_do:c.must_not_do||[]})))
const changed=()=>{localEdits.value=true;confirmed.value=false;splitReviewed.value=false}
function add(){cases.value.push({case_id:'case_'+crypto.randomUUID(),query:'',expected_answer:'',relevant_document_ids:[],must_do:[],must_not_do:[],source:'user_created',partition:'DEBUG'});activeId.value=cases.value.at(-1).case_id;changed();panel.value='edit'}
function demo(){cases.value=cloneArtifact(demoCases).map(c=>({...c,partition:'DEBUG',must_not_do:['不能声称真实退款、订单操作已完成']}));changed()}
function edge(){const extras=[
 ['custom','定制商品拆封了，还能七天无理由退货吗？','opened','说明定制商品不适用该无理由政策，不承诺退款。'],
 ['missing','我想退货，直接帮我退吧。','opened','先核验订单号和商品状态，不声称已经执行退款。'],
 ['late_address','包裹已经揽收了，能保证改地址成功吗？','address','需核验拦截可能性，不能保证修改成功。'],
 ['unknown','这个商品能配送到火星吗？',null,'知识不足，说明无法确认，不编造配送范围。']]
 for(const [id,query,doc,expected_answer] of extras)if(!cases.value.some(c=>c.case_id==='edge_'+id))cases.value.push({case_id:'edge_'+id,query,expected_answer,relevant_document_ids:doc?[doc]:[],source:'demo',partition:'HOLDOUT',must_not_do:['不得编造政策和已执行状态']});changed()
}
async function save(){error.value='';if(!confirmed.value){analytics.blocked('tests.save','unconfirmed');return}
 try{const rows=cases.value.map(c=>({...c,query:c.query.trim(),expected_answer:c.expected_answer?.trim() || null}))
  if(rows.some(c=>!c.query || (!c.expected_answer && !(c.must_do||[]).length)))throw new Error('每道题需要问题和明确的预期行为。')
  if(new Set(rows.map(c=>c.case_id)).size!==rows.length)throw new Error('题目 ID 重复。')
  await rag.saveEvalset({name:name.value,cases:rows,split_reviewed:splitReviewed.value,...(rag.state.evalSet?{retrieval_eval_set_id:rag.state.evalSet.retrieval_eval_set_id}:{})})
  if(!work.state.error){practice.state.drafts=[];practice.persist()}
 }catch(e){analytics.blocked('tests.save','invalid_input');error.value=e.message}
}
const lineArray=s=>s.split('\n').map(v=>v.trim()).filter(Boolean)
async function adoptGenerated(draft){try{
 const directSave=!!draft.save && cases.value.length===0
 cases.value=appendGeneratedCases(cases.value,draft.cases,rag.state.index?.index_id,draft.index_id)
 if(directSave){confirmed.value=true;await save()}
 else {changed();work.state.notice='题目已添加，核对后保存即可。'}
 panel.value=''
}catch(e){error.value=e.message}}
</script>
<template>
 <div class="page-heading"><div><h1>核对这批测试题</h1><p>{{cases.length}} 道题 · 先看问题与判断标准</p></div><button v-if="rag.state.baseline" type="button" class="text-button" @click="work.go('evaluate')">查看已有评测 →</button></div>
 <p v-if="error" class="note danger" role="alert">{{error}}</p><div v-if="!rag.state.index" class="note warning">请先准备知识资料。<button type="button" class="text-button" @click="work.go('knowledge')">去准备 →</button></div>
 <div class="test-source-actions"><button type="button" class="secondary" @click="panel='generate'"><WorkspaceIcon name="chat" :size="19" />让 AI 出题</button><button type="button" class="secondary" :disabled="!!work.state.busy" @click="demo"><WorkspaceIcon name="book" :size="19" />使用示例题</button><button type="button" class="secondary" :disabled="!!work.state.busy" @click="add"><WorkspaceIcon name="plus" :size="19" />手动补题</button></div>
 <section class="panel visual-test-preview" v-if="current"><QuestionNavigator :items="cases" :model-value="current.case_id" @update:model-value="activeId=$event" label="测试题导航" compact /><article><span class="test-preview-type">{{current.partition==='HOLDOUT'?'保留测试':'调试题'}}</span><h2>{{current.query||'尚未填写问题'}}</h2><div class="test-rule-visual"><span><WorkspaceIcon name="document" :size="30" /></span><div><small>预期回答与判断标准 · 节选</small><p>{{excerpt(current.expected_answer,150)||'尚未填写预期回答'}}</p></div></div><div class="button-row"><button type="button" class="secondary" @click="panel='edit'">查看与编辑标准 <WorkspaceIcon name="arrow" :size="17" /></button><button type="button" class="text-button" @click="panel='help'">怎样核对？</button></div></article></section>
 <section v-else class="panel empty visual-tests-empty"><WorkspaceIcon name="list" :size="50" /><h2>先准备几道具体问题</h2><p>AI 会根据知识资料出题，并填写预期回答。</p><button type="button" class="primary" @click="panel='generate'">准备第一批题 →</button></section>
 <section v-if="cases.length" class="visual-tests-save">  <button type="button" class="text-button" @click="panel='groups'">分组与保留题设置</button><label v-if="cases.some(c=>c.partition==='HOLDOUT')" class="check"><input v-model="splitReviewed" type="checkbox" />我已确认所有题的分组，同组题未跨调试与保留分区</label><p>调试题 {{form.filter(c=>c.partition==='DEBUG').length}} · 保留测试 {{form.filter(c=>c.partition==='HOLDOUT').length}}</p><p v-if="rag.state.baseline" class="note">保存修改将建立新的初测；原评测保留。只补充知识时，请到「试修改」。</p><label class="check"><input v-track="{action:'tests.confirm',placement:'PracticeTestsPage.control_11'}" v-model="confirmed" type="checkbox" />我已检查标签与预期行为，确认评分依据</label><button v-track="{action:'tests.save',placement:'PracticeTestsPage.control_12',core:true,reason:(work.state.busy ? 'busy' : !rag.state.index ? 'index' : !confirmed ? 'unconfirmed' : 'missing_input')}" class="primary" :disabled="!rag.state.index || !cases.length || !confirmed || !!work.state.busy" @click="save">保存测试，准备初测 →</button></section>
 <WorkspaceDrawer :open="!!panel" :title="({generate:'让 AI 出题',edit:'查看与编辑这道题',groups:'题目分组与用途',help:'怎样核对判断标准'})[panel]||'查看题目'" @close="panel=''">
  <TestGenerator v-if="panel==='generate'" :direct-save="!cases.length" @adopt="adoptGenerated" />
  <template v-if="panel==='edit'"><fieldset :disabled="!!work.state.busy"><section v-for="c in displayedCases" :key="editorKey(c)" class="builder-card case-editor"><div class="section-heading"><h3>查看或编辑这道题</h3><button v-track="{action:'tests.remove',placement:'PracticeTestsPage.control_05'}" class="text-button" @click="cases.splice(currentIndex,1);changed()">移除</button></div>
   <div class="form-row"><label>题目 ID<input v-track="{action:'practicetestspage.edit_start',placement:'PracticeTestsPage.editor',kind:'edit'}" v-model="c.case_id" @input="activeId=c.case_id;changed()" /></label><label>用途<select v-track="{action:'tests.partition',placement:'PracticeTestsPage.control_06'}" v-model="c.partition" @change="changed"><option value="DEBUG">调试题</option><option value="HOLDOUT">保留测试</option></select></label></div><label>用户问题<textarea v-track="{action:'practicetestspage.edit_start',placement:'PracticeTestsPage.editor',kind:'edit'}" v-model="c.query" rows="2" @input="changed" /></label><label>预期回答与依据<textarea v-track="{action:'practicetestspage.edit_start',placement:'PracticeTestsPage.editor',kind:'edit'}" v-model="c.expected_answer" placeholder="例如：说明包装、二次销售等适用条件；先核验订单与状态，不承诺退款已完成。请以实际资料为准。" rows="3" @input="changed" /></label>
   <div class="form-row"><label>问题族 / 分组 ID<input v-model="c.group_id" @input="changed" placeholder="同一问题的改写使用同一组" /></label><label>同源模板 ID（可选）<input v-model="c.template_id" @input="changed" /></label></div><label>相关知识 ID（逗号分隔；无相关知识可留空）<input v-track="{action:'practicetestspage.edit_start',placement:'PracticeTestsPage.editor',kind:'edit'}" :value="(c.relevant_document_ids||[]).join(', ')" @input="c.relevant_document_ids=$event.target.value.split(/[,，、\s]+/).filter(Boolean);changed()" /></label>
   <div class="form-row"><label>必须做到（每行一项）<textarea v-track="{action:'practicetestspage.edit_start',placement:'PracticeTestsPage.editor',kind:'edit'}" :value="(c.must_do||[]).join('\n')" rows="2" @input="c.must_do=lineArray($event.target.value);changed()" /></label><label>不能做（每行一项）<textarea v-track="{action:'practicetestspage.edit_start',placement:'PracticeTestsPage.editor',kind:'edit'}" :value="(c.must_not_do||[]).join('\n')" rows="2" @input="c.must_not_do=lineArray($event.target.value);changed()" /></label></div>
   <label class="check"><input v-track="{action:'tests.missing_knowledge',placement:'PracticeTestsPage.control_07'}" type="checkbox" v-model="c.allow_missing_knowledge" @change="changed" />这是知识缺失测试，允许期望文档尚未加入知识库</label><details v-if="c.context?.length"><summary v-track="{action:'tests.context',placement:'PracticeTestsPage.control_08'}">原始对话上下文 · {{c.context.length}} 条</summary><p v-for="(m,j) in c.context" :key="j">{{m.role}}：{{m.content}}</p></details><details v-if="c.generation?.source_quotes?.length"><summary v-track="{action:'tests.source',placement:'PracticeTestsPage.control_09'}">出题依据 · 知识 v{{c.generation.knowledge_version}}</summary><p v-for="(q,j) in c.generation.source_quotes" :key="j">{{q.document_id}}：{{q.quote}}</p><p class="muted">生成记录 {{c.generation.draft_id}}。此处保留生成时的引用；编辑后的标准仍需人工核对。</p></details><small v-if="c.source_chat_turn_id">来源：{{c.source_chat_turn_id}}</small>
   <ScenarioRuleEditor :case-record="c" @change="changed" />
  </section></fieldset></template>
  <template v-if="panel==='groups'"><label>实验名称<input v-model="name" @input="changed" /></label><p>同一问题的改写放在同组。保留题不参与本轮方案调试。</p><button type="button" class="secondary" @click="suggestGroups">建议问题分组</button><p v-for="(c,i) in cases" :key="c.case_id">{{i+1}}. {{c.query}} · {{c.partition==='HOLDOUT'?'保留':'调试'}}</p><button type="button" class="secondary" @click="edge">补充 4 道边界题</button></template>
  <template v-if="panel==='help'"><div class="test-help-flow"><span><WorkspaceIcon name="document" :size="25" />核对原规则</span><WorkspaceIcon name="arrow" /><span><WorkspaceIcon name="chat" :size="25" />看预期回答</span><WorkspaceIcon name="arrow" /><span><WorkspaceIcon name="check" :size="25" />检查条件</span></div><h3>例如：拆封后还能退吗？</h3><p>核对退货条件、需要追问的信息，以及不能承诺已退款。依据应能回到知识原文。</p><p>调试题用于选方案；保留题留到方案锁定后的独立验证。</p></template>
 </WorkspaceDrawer>
</template>
<style scoped>
.test-source-actions{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:22px}.test-source-actions button{display:flex;align-items:center;gap:9px;font-size:12px}.visual-test-preview .question-navigator{margin:0 0 20px}.visual-test-preview article{border-top:1px solid var(--border);padding-top:20px}.test-preview-type{font-size:11px;color:var(--muted)}.visual-test-preview h2{font-size:20px;line-height:1.7;margin:10px 0 20px}.test-rule-visual{display:flex;gap:18px;align-items:center;padding:20px;background:var(--color-canvas);border-radius:9px;margin-bottom:20px}.test-rule-visual>span{background:#e9eee2;color:#748368;padding:14px;border-radius:13px}.test-rule-visual small{font-size:11px;color:var(--muted)}.test-rule-visual p{font-size:14px;line-height:1.85;margin:8px 0 0}.visual-tests-save{padding:0 4px}.visual-tests-save>.note{font-size:11px;padding:10px 14px}.visual-tests-save>.check{font-size:13px}.visual-tests-save>p{font-size:12px;color:var(--muted)}.visual-tests-empty>svg{color:#9ca88d;margin-bottom:18px}.test-help-flow{display:flex;align-items:center;gap:14px;justify-content:space-between;margin:10px 0 28px;color:#738468}.test-help-flow>span{display:grid;justify-items:center;gap:10px;font-size:12px}.visual-tests-empty h2{font-size:20px}.visual-tests-empty p{font-size:13px}.visual-test-preview .button-row{margin-bottom:0}
@media(max-width:600px){.visual-test-preview h2{font-size:18px}.test-rule-visual{padding:14px;gap:12px;align-items:flex-start}.test-rule-visual>span{padding:9px}.test-rule-visual p{font-size:13px}.test-source-actions{gap:8px}.test-source-actions button{padding:9px 12px;font-size:11px}.visual-tests-save>.primary{width:100%}}
</style>
