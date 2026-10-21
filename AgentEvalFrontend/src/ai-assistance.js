import {reactive} from 'vue'
export const questionTypes=['常规','口语','边界','多条件','知识范围外']
export const copy=value=>JSON.parse(JSON.stringify(value))
export const estimateTestCalls=count=>Math.ceil(count/4)
export function requiresPolicyReference(c){return !['MISSING_KNOWLEDGE','CLARIFICATION'].includes(c.scenario_rules?.template_id)&&!['CLARIFY','HANDOFF','REFUSE'].includes(c.scenario_rules?.expected_behavior)}
export function confirmGeneratedEvidence(cases,confirmed){
 if(!confirmed)throw new Error('请先逐题核对标准、原文和政策覆盖，再确认保存。')
 return cases.map(original=>{const c=copy(original)
  if(c.generation?.question_type==='知识范围外'){c.scenario_rules={...c.scenario_rules,template_id:'MISSING_KNOWLEDGE',expected_behavior:'HANDOFF'};return c}
  if(requiresPolicyReference(c)){
   if(c.reference_complete===false)throw new Error('选中题仍有已知的政策缺口，请先移除该题或补齐资料，再确认保存。')
   c.reference_complete=true;c.reference_completeness={...c.reference_completeness,confirmed_by:'工作区用户',method:'USER_CONFIRMED_POLICY_COVERAGE',reason:'用户保存 AI 测试草稿时确认：已逐题核对资料覆盖本题所需政策条件。此声明不是独立人工标注。'}
  }
  return c
 })
}
export function appendGeneratedCases(current,incoming,indexId,draftIndexId){
 if(indexId!==draftIndexId)throw new Error('知识索引已变化，请按当前版本重新生成测试。')
 const ids=new Set(current.map(c=>c.case_id))
 return [...current,...incoming.filter(c=>!ids.has(c.case_id)).map(copy)]
}
export function createAiAssistance(){return reactive({knowledge:{scenario:'一家面向国内消费者的模拟电商店铺，提供商品咨询与售后客服。',facts:'',draft:null,documents:[],name:'',selected:[],confirmed:false},tests:{count:8,types:[...questionTypes],draft:null,cases:[],selected:[],confirmed:false},analyses:{},evaluationChats:{},providerOptions:[],modelSession:''})}
export async function restoreAiDrafts(ai,client){
 const history=await client.get('/ai/drafts')
 for(const kind of ['KNOWLEDGE','TESTS']){
  const record=history.find(d=>d.kind===kind);if(!record)continue
  const draft=await client.get('/ai/drafts/'+record.draft_id)
  if(kind==='KNOWLEDGE')Object.assign(ai.knowledge,{draft,scenario:draft.content.scenario,facts:draft.sources.facts||'',name:draft.content.name,documents:copy(draft.content.documents),selected:draft.content.documents.map(d=>d.document_id),confirmed:false})
  else Object.assign(ai.tests,{draft,cases:copy(draft.content.cases),selected:draft.content.cases.map(c=>c.case_id),confirmed:false})
 }
 for(const record of history.filter(d=>d.kind==='TRACE').slice(0,5)){
  const draft=await client.get('/ai/drafts/'+record.draft_id)
  const source=draft.sources.comparison||draft.sources.run
  const id=source?.comparison_id||source?.run_id,caseId=source?.pair?.case_id||source?.case?.case_id
  if(id&&caseId&&!ai.analyses[`${id}:${caseId}`])ai.analyses[`${id}:${caseId}`]=draft
 }
}
