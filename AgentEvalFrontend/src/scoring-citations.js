// Match frozen citations to exact retrieved chunks, never to their display order.
const positive=value=>Number.isInteger(value)&&value>0
const chunkId=row=>row?.chunk_id||row?.evidence_id
export function retrievalCitation(citation,retrieval,documents=[],topK=null){
 const reference=citation?.scope==='REFERENCE'
 const rows=Array.isArray(retrieval?.results)?retrieval.results:[]
 const matches=rows.filter(row=>chunkId(row)===citation?.evidence_id)
 const match=matches.length===1&&typeof citation?.quote==='string'&&citation.quote.length&&typeof matches[0].text==='string'&&matches[0].text.includes(citation.quote)?matches[0]:null
 const documentId=reference?citation.evidence_id:match?.document_id
 const title=documents.find(d=>d.document_id===documentId)?.title||match?.title||''
 if(reference)return {title,rank:null,label:''}
 if(match?.context_origin==='EXPANDED')return {title,rank:null,label:'补充上下文'}
 const selected=Array.isArray(retrieval?.selected_results)?retrieval.selected_results:rows
 const ranked=match?selected.filter(row=>chunkId(row)===citation.evidence_id):[]
 const rank=ranked.length===1&&positive(ranked[0].rank)?ranked[0].rank:null
 const k=positive(retrieval?.top_k)?retrieval.top_k:positive(topK)?topK:null
 const valid=rank!==null&&(k===null||rank<=k)
 return {title,rank:valid?rank:null,label:valid?`检索第 ${rank} 条`:'未记录检索排名'}
}
export function retrievalCitationSummary(retrieval,topK=null){
 if(!Array.isArray(retrieval?.results))return ''
 const provided=retrieval.results.length
 const selected=Array.isArray(retrieval.selected_results)?retrieval.selected_results.length:provided
 const k=positive(retrieval.top_k)?retrieval.top_k:positive(topK)?topK:null
 const limit=k===null?'':` · Top K = ${k}`
 return selected===provided?`本次返回 ${provided} 条资料${limit}`:`本次检索选中 ${selected} 条${limit} · 实际提供 ${provided} 条资料`
}
