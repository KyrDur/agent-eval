import {questionStatus,answerExplanation} from './question-navigation.js'
export const resultTones={通过:'pass',不通过:'fail',执行失败:'error',证据不足:'unknown',未检查:'unknown',本题不适用:'neutral',尚未执行:'unknown',已找到:'pass',未找到:'fail'}
// These are excerpts of saved records, never newly generated diagnoses.
export function excerpt(text,max=90){const value=String(text||'').replace(/\*\*/g,'').replace(/`/g,'').replace(/\s+/g,' ').trim();return value.length>max?value.slice(0,max)+'…':value}
export function visualRows(view){
 if(!view?.run)return []
 const records=view.run.case_results||[],snapshot=view.run.controls?.eval_set_snapshot?.cases||[]
 const ids=[...new Set([...(view.run.execution_order||[]),...records.map(c=>c.case_id)])]
 return ids.map((id,index)=>{
  const actual=records.find(c=>c.case_id===id),saved=snapshot.find(c=>c.case_id===id)
  const row=actual||{case_id:id,query:saved?.query||'原问题未记录',results:[],retrieval_status:'INVALID',missing:true}
  const status=actual?questionStatus(view,row):'尚未执行'
  return {...row,number:index+1,status,tone:resultTones[status]||'unknown'}
 })
}
export function visualSummary(view){
 const rows=visualRows(view),flow=view?.trusted_result?.sample_flow||view?.run?.sample_flow
 const counts=Object.fromEntries(['pass','fail','error','unknown','neutral'].map(t=>[t,rows.filter(c=>c.tone===t).length]))
 const verified=!!view?.run?.verify_answers
 const denominator=verified?(flow?.coverage?.denominator??rows.length):rows.length
 const decided=verified?(flow?.coverage?.numerator??counts.pass+counts.fail):counts.pass+counts.fail
 const rate=verified?flow?.partial_pass_rate:null
 const passed=rate?.numerator??counts.pass,binary=rate?.denominator??decided
 let title=verified?(counts.fail?`${counts.fail} 题没答好，先看这里`:counts.error?`${counts.error} 题未完成，先查运行`:counts.unknown?'有些题还不能判断':rows.length?'这批题的判定已保存':'等待评测结果'):'资料找得怎么样？'
 return {rows,counts,total:denominator,decided,passed,binary,title,verified,historical:verified&&!flow}
}
export function caseExcerpt(view,row){
 const answer=view?.effective_answer_results?.find(a=>a.case_id===row?.case_id)
 const text=answer?.turn_evidence?.[0]?.response
 const reason=answer?answerExplanation(answer):row?.error||(!view?.run?.verify_answers?'仅检查资料查找，未评判回答。':'本题尚未形成判定。')
 return {answer,answerText:text||'',reason,answerExcerpt:excerpt(text,84)||'本题没有保存回答',reasonExcerpt:excerpt(reason,76)}
}
