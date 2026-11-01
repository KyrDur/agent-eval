// Display names only: saved judgments, quoted text and exported logs stay intact.
export function readableScoringReason(text,evaluation,dimension){
 const original=String(text||'')
 let raw
 try{raw=JSON.parse(String(evaluation?.raw_output||'').trim().replace(/^```json\s*([\s\S]*?)\s*```$/,'$1'))}catch{return original}
 const rows=dimension?[raw?.dimensions?.[dimension]]:Object.values(raw?.dimensions||{})
 const selected=new Set(rows.flatMap(row=>[...(Array.isArray(row?.answer_fragment_ids)?row.answer_fragment_ids:[]),...(Array.isArray(row?.evidence_fragment_ids)?row.evidence_fragment_ids:[])])
  .filter(id=>typeof id==='string'&&/^[ARP][1-9]\d*$/.test(id)))
 let display=original
 for(const [prefix,label] of [['A','这段回答'],['R','检索资料'],['P','评分参考资料']]){
  const aliases=new RegExp('(?<![A-Za-z0-9_-])'+prefix+'[1-9]\\d*(?:\\s*(?:[-–—~～、,，]|至|到|和|与|及)\\s*'+prefix+'[1-9]\\d*)*(?![A-Za-z0-9_-])','g')
  display=display.replace(aliases,match=>{
   const ids=match.match(/[ARP][1-9]\d*/g)||[]
   return ids.every(id=>selected.has(id))?(prefix==='A'&&ids.length>1?'回答片段':label):match
  })
 }
 return display.replace(/([\u3400-\u9fff，。；：、]) +(?=这段回答|回答片段|检索资料|评分参考资料)/g,'$1')
  .replace(/(这段回答|回答片段|检索资料|评分参考资料) +(?=[\u3400-\u9fff，。；：、])/g,'$1')
}
