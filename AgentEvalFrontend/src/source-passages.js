// Unicode codepoint offsets match Python source slicing, including emoji.
export function sourcePassages(documents=[]){
 return documents.flatMap(doc=>{
  const chars=Array.from(doc.text||''),rows=[];let start=0
  function append(end){for(let a=start;a<end;a+=1800){const b=Math.min(end,a+1800),quote=chars.slice(a,b).join('');if(quote.trim())rows.push({document_id:doc.document_id,title:doc.title||doc.document_id,quote,source_start:a,source_end:b,offset_unit:'UNICODE_CODEPOINT',source_hash:doc.content_hash||null})}}
  for(let i=0;i<=chars.length;i++)if(i===chars.length||chars[i]==='\n'){append(i);start=i+1}
  return rows
 })
}
export function samePassage(a,b){return a.document_id===b.document_id&&a.quote===b.quote}
export function passageValid(q,documents){
 const doc=documents.find(d=>d.document_id===q.document_id)
 if(!doc||!q.quote||!doc.text.includes(q.quote)||q.source_hash&&doc.content_hash&&q.source_hash!==doc.content_hash)return false
 if(q.source_start!=null&&q.source_end!=null)return Array.from(doc.text).slice(q.source_start,q.source_end).join('')===q.quote
 return true
}
export function referenceDraft(spec,documents){
 // Exact source excerpts only. No model, no invented missing policy.
 const answer=spec?.expected_answer?.trim();if(!answer)return []
 return answer.split(/[。！？\n]/u).map(x=>x.trim()).filter(Boolean).flatMap((sentence,i)=>{
  const doc=documents.find(d=>d.text.includes(sentence));if(!doc)return []
  const utf16=doc.text.indexOf(sentence),start=Array.from(doc.text.slice(0,utf16)).length
  return [{fact_id:'draft_'+i,description:sentence,alternatives:[[{document_id:doc.document_id,quote:sentence,source_hash:doc.content_hash||null,source_start:start,source_end:start+Array.from(sentence).length,offset_unit:'UNICODE_CODEPOINT'}]],draft_origin:'EXACT_REFERENCE_SOURCE_MATCH'}]
 })
}
