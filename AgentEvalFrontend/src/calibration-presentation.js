export const dimensionLabels = {faithfulness:'事实与依据',conditions:'条件覆盖',relevance:'意图与相关性',actionability:'下一步可用性'}
export const protocolLabels = {J1:'基础评分',J2:'增加证据核对',J3:'加入人工边界示例'}
export const statusLabels = {
  PASS:'合格',FAIL:'不合格',PENDING:'资料不足，待判断',SUCCESS:'评分有效',COMPLETE:'已完成',PARTIAL:'部分完成',FAILED:'执行失败',RUNNING:'正在执行',
  INTERFACE_ERROR:'模型接口失败',PARSE_ERROR:'评分格式无法解析',CONTENT_INVALID:'评分依据校验失败',NOT_RUN:'尚未评分',
  EVIDENCE_INSUFFICIENT:'判断所需资料不足',HUMAN_UNRESOLVED:'缺少可用人工参照',HUMAN_DISAGREEMENT:'人工分歧待裁决',
  AGREE:'人机判断一致',FALSE_PASS:'AI 错误放行',FALSE_FAIL:'AI 错误拒绝',UNPAIRED:'暂时无法比较',
  SINGLE:'一位独立人工参照',AGREED:'多人判断一致',ADJUDICATED:'已人工裁决',DISAGREEMENT:'人工分歧待裁决',MISSING:'尚无独立人工参照',
  CALIBRATION:'调试与校准',HOLDOUT:'最终验证题',CONSTRUCTED:'构造样本',ACTUAL:'实际使用样本',AI_GENERATED:'AI 生成样本',
  HUMAN:'真实人工',AI:'AI 建议',CODEX:'Codex 功能验收',KEEP_BASELINE:'保留原版',REVISE:'继续调整',ADOPT:'采用候选',
  COMPLETED_WITH_SINGLE_ANNOTATOR:'已验证 · 单人参照',COMPLETED_WITH_ADJUDICATED_REFERENCE:'已验证 · 多人参照',
  OPEN:'待确认',REPRODUCED:'已复现',CHANGED:'已修改',RETESTED:'已复测',UNRESOLVED:'未解决',CLOSED:'已记录修复结论',
  DATA:'数据与取证',PROMPT:'AI 评分说明',RUBRIC:'评分细则',AGENT:'Agent 本身',
  FIXED:'本轮复测支持改善',NOT_FIXED:'仍未解决',INCONCLUSIVE:'证据不足，暂不确定',
  ANSWER_QUOTE_INVALID:'引用的回答文字与原文不符',EVIDENCE_QUOTE_INVALID:'引用的政策文字与原文不符',
  FRAGMENT_ID_INVALID:'引用了本题不存在的片段',FRAGMENT_SCOPE_INVALID:'回答与政策片段范围混用',FRAGMENT_ID_DUPLICATED:'重复引用相同片段',
  FRAGMENT_SCHEMA_INVALID:'片段引用格式不正确',DUPLICATE_RESULT:'同一样本出现重复结果',
}
export function labelFor(value){return statusLabels[value]||value||'尚无结果'}
export function newJudgment(){return {
  dimensions:Object.fromEntries(Object.keys(dimensionLabels).map(k=>[k,{score:'INSUFFICIENT',answer_quotes:[],citations:[],reason:''}])),
  critical_errors:[],error_tags:[],verdict:'PENDING',task_resolved:'INSUFFICIENT',faithful_to_available:'INSUFFICIENT',
  task_failure_reasons:[],insufficient_items:[],reason:'',
}}
export function verdictFor(value,rubric){
  if(value.critical_errors.length)return 'FAIL'
  const rows=Object.entries(value.dimensions)
  if(rows.length!==4||rows.some(([key,d])=>d.score==='INSUFFICIENT'||d.score==='NA'&&!rubric.rules.na_allowed.includes(key)))return 'PENDING'
  return rows.every(([key,d])=>d.score==='NA'||d.score>=rubric.rules.minimum_scores[key])?'PASS':'FAIL'
}
export function judgmentProblems(value,sample,rubric){
  const problems=[]
  if(!value.reason.trim())problems.push('填写总理由。')
  for(const [key,label] of Object.entries(dimensionLabels)){
    const d=value.dimensions[key]
    if(!d?.reason?.trim())problems.push(`${label}：填写简短理由。`)
    if(Number.isInteger(d?.score)){
      if(!d.answer_quotes.length)problems.push(`${label}：点选至少一段回答原文。`)
      if(key==='faithfulness'&&sample.retrieved_evidence.length&&!d.citations.some(c=>c.scope==='RETRIEVED'))problems.push(`${label}：点选当时检索资料。`)
      if(key==='conditions'&&sample.reference_complete&&!d.citations.some(c=>c.scope==='REFERENCE'))problems.push(`${label}：点选完整参考政策。`)
    }
    if(d?.score==='NA'&&!rubric.rules.na_allowed.includes(key))problems.push(`${label}：本项不能选择不适用。`)
  }
  if(Object.values(value.dimensions).some(d=>d.score==='INSUFFICIENT')&&!value.insufficient_items.some(s=>s.trim()))problems.push('填写具体缺少什么资料。')
  return problems
}
export function localFragments(sample){
  const sources=[{scope:'ANSWER',evidence_id:null,text:sample.answer},
    ...sample.retrieved_evidence.map(e=>({...e,scope:'RETRIEVED'})),...sample.reference_policy.map(e=>({...e,scope:'REFERENCE'}))]
  return sources.flatMap((source,index)=>(source.text.match(/[\s\S]{1,500}/g)||[]).filter(t=>t.trim()).map((text,part)=>({
    fragment_id:`local-${index}-${part}`,scope:source.scope,evidence_id:source.evidence_id,text,
  })))
}
