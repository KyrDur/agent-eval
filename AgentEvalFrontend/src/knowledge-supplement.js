// A reference-answer supplement is debug material, never an independent test result.
const clone=value=>JSON.parse(JSON.stringify(value))
export function supplementSource(view,caseId){
 const run=view?.run,row=run?.case_results?.find(c=>c.case_id===caseId)
 const sample=run?.controls?.eval_set_snapshot?.cases?.find(c=>c.case_id===caseId)
 if(!row||!sample||run.status==='RUNNING'||sample.partition==='HOLDOUT')throw new Error('请从已完成的调试题中选择要补充的题目。')
 const reference=sample.expected_answer?.trim()
 if(!reference)throw new Error('这道题还没有参考答案，请先在测试题中补充。')
 return {runId:run.run_id,caseId,question:sample.query||row.query,reference,knowledge:run.controls.knowledge_snapshot,index:run.controls.index_snapshot}
}
export function latestReferenceSupplement(knowledge,runId,caseId){
 if(!runId)return null
 const documents= (knowledge?.documents||[]).filter(d=>d.metadata?.reference_supplement?.source_run_id===runId)
  .sort((a,b)=>String(b.metadata.reference_supplement.created_at).localeCompare(String(a.metadata.reference_supplement.created_at)))
 return (caseId&&documents.find(d=>d.metadata.reference_supplement.source_case_id===caseId))||documents[0]||null
}
const hash=async text=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text))),b=>b.toString(16).padStart(2,'0')).join('')
export async function supplementReference({view,caseId,session,client,assertCurrent=()=>{}}){
 const source=supplementSource(view,caseId)
 if(session?.credential_status!=='PRESENT'||session?.text_connection_status!=='READY')throw new Error('请先恢复模型连接，再让 AI 帮你补充。')
 const signature=await hash(JSON.stringify([source.runId,caseId,source.reference]))
 const documentId='reference_'+signature.slice(0,28),datasetId=source.knowledge.knowledge_dataset_id
 const path='/knowledge-datasets/'+datasetId
 let latest=await client.get(path)
 const existing=()=>latest.documents.find(d=>d.document_id===documentId)
 assertCurrent()
 if(existing())return {knowledge:latest,document:existing(),alreadyAdded:true,source}
 if(latest.documents.length>=100)throw new Error('资料已达到 100 份，请先合并部分资料再补充。')
 const requestId='supplement_'+(await hash(signature+session.provider_session_id)).slice(0,36)
 const turn=await client.post('/ai/evaluation-chat',{
  request_id:requestId,provider_session_id:session.provider_session_id,run_id:source.runId,case_id:caseId,
  question:'请核对本题已保存的预期回答和实际资料，用不超过100字说明：把这份预期回答原文补成知识库问答条目，能帮助补充哪些信息，哪些信息仍然不能确定。不要新增业务规则、日期、金额或承诺，不要根据错误回答补政策。不要声称已经保存或已经提升；页面随后会原样保存参考答案，并通过原题复测。',parent_turn_id:null,
 })
 assertCurrent()
 // Re-read after the model call so intervening edits are retained. A retry also
 // discovers an already-saved document after a lost POST response.
 latest=await client.get(path)
 if(existing())return {knowledge:latest,document:existing(),alreadyAdded:true,source}
 if(latest.documents.length>=100)throw new Error('资料已达到 100 份，请先合并部分资料再补充。')
 const document={document_id:documentId,title:'本题补充：'+source.question.slice(0,44),
  text:`问题：${source.question}\n参考答案：\n${source.reference}`,
  metadata:{source:'REFERENCE_ANSWER_SUPPLEMENT',reference_supplement:{source_run_id:source.runId,source_case_id:caseId,
   reference_hash:signature,source_knowledge_version:source.knowledge.version,question:source.question,created_at:turn.created_at||new Date().toISOString(),
   ai_turn_id:turn.turn_id,ai_explanation:turn.answer,provider_call_count:turn.provider_call_count,usage:turn.usage,
   interpretation:'Derived from the debug reference answer. This retest is not independent validation; AI explanation is not added as policy text.'}}}
 assertCurrent()
 const knowledge=await client.post('/knowledge-datasets',{knowledge_dataset_id:datasetId,name:latest.name,
  documents:[...latest.documents.map(({document_id,title,text,metadata})=>({document_id,title,text,metadata})),document],metadata:clone(latest.metadata||{})})
 return {knowledge,document:knowledge.documents.find(d=>d.document_id===documentId),alreadyAdded:false,source}
}
