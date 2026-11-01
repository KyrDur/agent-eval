// Keep retrieval, answer judgements, and missing evidence separate.
export function comparisonSummary(comparison,baseline,retest,change){
 const pairs=comparison?.case_pairs||[],answers=!!baseline?.run?.verify_answers
 const counts={improved:0,regressed:0,unchanged:0,incomplete:0,notComparable:0}
 const retrieval={improved:0,regressed:0,unchanged:0,notComparable:0}
 const classify=p=>{
  if(!p.baseline||!p.retest||p.baseline.status!=='SUCCESS'||p.retest.status!=='SUCCESS')return 'incomplete'
  if(!comparison?.comparable)return 'notComparable'
  if(answers){
   if(p.baseline_answer?.execution_status!=='SUCCESS'||p.retest_answer?.execution_status!=='SUCCESS')return 'incomplete'
   return p.answer_transition==='FAIL→PASS'?'improved':p.answer_transition==='PASS→FAIL'?'regressed':['PASS→PASS','FAIL→FAIL'].includes(p.answer_transition)?'unchanged':'notComparable'
  }
  return ({RETRIEVAL_IMPROVED:'improved',RETRIEVAL_REGRESSED:'regressed',RETRIEVAL_UNCHANGED:'unchanged'})[p.transition]||'notComparable'
 }
 const rows=pairs.map(p=>{
  counts[classify(p)]++
  retrieval[({RETRIEVAL_IMPROVED:'improved',RETRIEVAL_REGRESSED:'regressed',RETRIEVAL_UNCHANGED:'unchanged'})[p.transition]||'notComparable']++
  const a=p.baseline?.evidence_path?.context,b=p.retest?.evidence_path?.context
  const facts=a?.review_status==='CONFIRMED'&&b?.review_status==='CONFIRMED'?{added:(b.facts||[]).filter(f=>f.included&&(a.facts||[]).some(x=>x.fact_id===f.fact_id&&!x.included)),lost:(a.facts||[]).filter(f=>f.included&&(b.facts||[]).some(x=>x.fact_id===f.fact_id&&!x.included))}:null
  const left=p.baseline?.results||[],right=p.retest?.results||[],same=(x,y)=>x.document_id===y.document_id&&x.text===y.text
  return {...p,category:classify(p),facts,addedContext:right.filter(x=>!left.some(y=>same(x,y))),lostContext:left.filter(x=>!right.some(y=>same(x,y)))}
 })
 const targets=new Set(change?.selected_case_ids||[])
 rows.sort((a,b)=>(a.category==='regressed'?0:targets.has(a.case_id)?1:2)-(b.category==='regressed'?0:targets.has(b.case_id)?1:2))
 const cost=view=>{
  const run=view?.run,flow=run?.sample_flow||view?.trusted_result?.sample_flow,stored=flow?.cost
  const duration=run?.created_at&&run?.finished_at?Date.parse(run.finished_at)-Date.parse(run.created_at):null
  return {requests:run?.provider_call_count??stored?.actual_requests??null,tokens:stored?.known_total_tokens??null,unknownUsage:stored?.unknown_usage_requests??null,elapsedMs:Number.isFinite(duration)?duration:null,contextChars:run?.case_results?run.case_results.reduce((n,c)=>n+(c.results||[]).reduce((s,x)=>s+(x.text?.length||0),0),0):null,fee:'未知'}
 }
 const label=answers?'回答判定':'检索结果'
 const text=`${label}：改善 ${counts.improved} 题，退化 ${counts.regressed} 题，未变 ${counts.unchanged} 题；未完成 ${counts.incomplete} 题，不可比较 ${counts.notComparable} 题。仅描述已保存的一次对照，不证明生产效果或唯一根因。`
 const reasons=[...(counts.regressed?[{id:'regression',text:`有 ${counts.regressed} 题退化，需要检查影响。`}]:[]),...(counts.improved?[{id:'improvement',text:`有 ${counts.improved} 题改善，继续核对目标问题与代价。`}]:[]),...(counts.incomplete+counts.notComparable?[{id:'limited',text:'存在未完成或不可比题，只记录局部观察。'}]:[]),{id:'repeat',text:'一次对照还不足以判断稳定性，需要进一步验证。'}]
 return {answers,label,counts,retrieval,rows,text,reasons,beforeCost:cost(baseline),afterCost:cost(retest)}
}
