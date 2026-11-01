export const factPrediction='检查目标题已审核要点的原文包含是否增加，并逐条核对适用性。'
export const rankingPrediction='检查候选排名、选取位置与实际上下文是否发生变化；不把排名变化当成回答改善。'
export const regressionRisk='检查其他题是否由通过变为未通过，缺少有效判定的题单列。'
export const costRisk='检查请求数、耗时、上下文长度和裁剪记录；缺少费用数据时保留未知。'
export function verificationPlan(prediction='',risk=''){return {prediction:prediction===factPrediction?'FACT_INCLUSION':prediction===rankingPrediction?'RANKING_CONTEXT':prediction?'CUSTOM':'UNSPECIFIED',risk:risk===regressionRisk?'ANSWER_REGRESSION':risk===costRisk?'COST':risk?'CUSTOM':'UNSPECIFIED'}}
export function savedCheckAssessment(change,comparison,summary){
 const line=prefix=>(change?.reason||'').split('\n').find(s=>s.startsWith(prefix))?.slice(prefix.length)||''
 const prediction=line('用户预测（待验证）：'),risk=line('用户担心的退化（待验证）：')
 const unknown=text=>({status:'无法判断',evidence:text})
 let aim=unknown('未选择可按记录核对的结构化预测；自然语言目的需要对照原文判断。'),riskResult=unknown('未选择可按记录核对的结构化风险；没有自动确认风险消失。')
 const ids=new Set(change?.selected_case_ids||[]),targets=summary.rows.filter(p=>ids.has(p.case_id))
 if(comparison?.comparable&&change?.verification_plan?.prediction==='FACT_INCLUSION'){
  if(targets.length&&targets.every(p=>p.facts&&p.baseline?.status==='SUCCESS'&&p.retest?.status==='SUCCESS')){
   const added=targets.reduce((n,p)=>n+p.facts.added.length,0),lost=targets.reduce((n,p)=>n+p.facts.lost.length,0)
   aim={status:added>0&&!lost?'本次观察支持':'本次未支持',evidence:`目标题已审核原文匹配新增 ${added} 个要点、丢失 ${lost} 个要点；仍需核对适用性，不证明回答或因果改善。`}
  }else aim=unknown('目标题缺少共同已审核的要点记录，不能确认覆盖变化。')
 }
 if(comparison?.comparable&&change?.verification_plan?.prediction==='RANKING_CONTEXT'&&targets.length&&targets.every(p=>p.baseline?.status==='SUCCESS'&&p.retest?.status==='SUCCESS')){
  const changed=targets.filter(p=>p.addedContext.length||p.lostContext.length||p.baseline.metrics?.relevant_rank!==p.retest.metrics?.relevant_rank).length
  aim={status:changed?'本次观察支持':'本次未支持',evidence:`${targets.length} 道目标题中，${changed} 道的已保存排名或实际上下文发生变化；不等于回答改善。`}
 }
 if(comparison?.comparable&&change?.verification_plan?.risk==='ANSWER_REGRESSION'){
  const others=summary.rows.filter(p=>!ids.has(p.case_id))
  if(summary.answers&&others.length&&others.every(p=>!['incomplete','notComparable'].includes(p.category))){
   const n=others.filter(p=>p.category==='regressed').length
   riskResult={status:n?'本轮观察到风险':'本轮未观察到风险',evidence:`其他 ${others.length} 道可比题中，${n} 道由通过变为未通过；一次未观察到不代表风险不存在。`}
  }else riskResult=unknown('其他题没有足够的同口径回答判定，不能判断是否发生退化。')
 }
 if(comparison?.comparable&&change?.verification_plan?.risk==='COST'){
  const a=summary.beforeCost,b=summary.afterCost
  if([a.requests,b.requests,a.elapsedMs,b.elapsedMs,a.contextChars,b.contextChars].every(Number.isFinite))riskResult={status:b.requests>a.requests||b.elapsedMs>a.elapsedMs||b.contextChars>a.contextChars?'本轮观察到代价增加':'本轮未观察到代价增加',evidence:`请求 ${a.requests} → ${b.requests}；耗时 ${(a.elapsedMs/1000).toFixed(1)} → ${(b.elapsedMs/1000).toFixed(1)} 秒；上下文字符 ${a.contextChars} → ${b.contextChars}。费用仍未知，耗时有单次波动。`}
 }
 return [{label:'修改前的预测',text:prediction||'未另外选择，使用方案的待验证目的',...aim},{label:'修改前关注的风险',text:risk||'未另外选择，保留方案的通用风险',...riskResult}]
}
