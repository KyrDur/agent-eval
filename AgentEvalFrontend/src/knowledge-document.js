// Viewing a document changes its presentation, never its retrieval evidence.
export function knowledgeSections(document) {
 const text=document.text||'',metadata=document.metadata||{}
 let body=text,applicability=metadata.applicability||'',exceptions=metadata.exceptions||''
 if(metadata.source==='AI_GENERATED_SIMULATION'){
  const suffix=`\n适用条件：${applicability}\n例外：${exceptions}`
  if(text.endsWith(suffix))body=text.slice(0,-suffix.length)
  else {
   // Older editors allowed whole-text edits; prefer the actual trailing sections.
   const start=text.lastIndexOf('\n适用条件：'),end=text.lastIndexOf('\n例外：')
   if(start>=0 && end>start){body=text.slice(0,start);applicability=text.slice(start+6,end);exceptions=text.slice(end+4)}
  }
 }
 return {body,applicability,exceptions}
}
export function editKnowledgeSection(document,section,value){
 const sections={...knowledgeSections(document),[section]:value}
 document.metadata ||= {}
 if(document.metadata.source==='AI_GENERATED_SIMULATION'){
  document.metadata.applicability=sections.applicability
  document.metadata.exceptions=sections.exceptions
  document.text=`${sections.body}\n适用条件：${sections.applicability}\n例外：${sections.exceptions}`
 } else if(section==='body')document.text=value
 else document.metadata[section]=value
}
export function knowledgeSource(document){
 const metadata=document.metadata||{}
 if(metadata.source==='AI_GENERATED_SIMULATION')return 'AI 生成的模拟资料'
 if(metadata.purpose==='DEMO_POLICY_NOT_BUSINESS_COMMITMENT')return '示例资料'
 if(metadata.source==='USER_UPLOADED')return '用户上传'
 return '手动添加'
}
