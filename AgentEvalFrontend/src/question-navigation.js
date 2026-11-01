import {checkLabels} from './trusted-results.js'
import {readableScoringReason} from './scoring-language.js'

export function questionLabel(number){
 const digits=['','一','二','三','四','五','六','七','八','九']
 const value=number<10?digits[number]:number<100?`${number>=20?digits[Math.floor(number/10)]:''}十${digits[number%10]}`:String(number)
 return `第${value}题`
}
export function selectedQuestion(items,id){return items.find(item=>item.case_id===id)||items[0]||null}
export function scoringFailure(answer){
 return answer?.execution_status==='SUCCESS'&&(answer.judge_status==='FAILED'||!!answer.evaluation_error||['PARSE_ERROR','CONTENT_INVALID','INTERFACE_ERROR'].includes(answer.evidence_evaluation?.status))
}
export function answerExplanation(answer){
 if(answer?.execution_status&&answer.execution_status!=='SUCCESS')return 'Agent 的回答未完成。打开运行日志，查看失败的步骤。'
 const issue=answer?.evidence_evaluation?.validation_issues?.find(i=>i.code==='NA_NOT_ALLOWED')
 if(scoringFailure(answer)&&issue){
  const name=issue.field_path?.split('.')[1],label={faithfulness:'事实与依据',conditions:'条件覆盖',relevance:'意图与相关性',actionability:'下一步可用性'}[name]||'评分项'
  return `回答已生成，评分未完成：评分模型把“${label}”写成了本题不允许的“不适用”。请仅重评本题，原记录保留。`
 }
 if(answer?.judge_status==='FAILED'||answer?.evaluation_error||answer?.evidence_evaluation?.status==='PARSE_ERROR')return '评分未完成。打开运行日志，查看评分模型的返回和具体错误。'
 return readableScoringReason(answer?.original_reason,answer?.evidence_evaluation)||'本题尚未形成判定，请查看运行日志。'
}
export function questionStatus(view,row){
 const state=view.trusted_result?.cases?.find(c=>c.case_id===row.case_id)?.evaluation_state
 const answer=view.effective_answer_results?.find(c=>c.case_id===row.case_id)
 if(view.run.verify_answers&&(!state||state==='EXECUTION_FAILED')&&scoringFailure(answer))return '评分失败'
 if(state&&view.run.verify_answers)return checkLabels[state]||'待判断'
 if(view.run.verify_answers){
  return checkLabels[answer?.human_evaluation_state||answer?.final_status]||({INVALID:'执行失败',PENDING:'待判断'})[answer?.final_status]||'待判断'
 }
 return {TOP_1_HIT:'已找到',LOWER_RANK_HIT:'已找到',NOT_RETRIEVED:'未找到',UNLABELED:'未标注',INVALID:'执行失败'}[row.retrieval_status]||'待判断'
}

// Answer outcomes are distinct from retrieval success and execution success.
export function questionAnswerOutcome(view,row){
 if(!view?.run)return {status:'尚未评测',tone:'unknown'}
 if(!view.run.verify_answers)return {status:'未检查回答',tone:'unknown'}
 const actual=view.run.case_results?.find(c=>c.case_id===row.case_id)
 if(!actual)return {status:'尚未执行',tone:'unknown'}
 const trusted=view.trusted_result?.cases?.find(c=>c.case_id===row.case_id)?.evaluation_state
 const answer=view.effective_answer_results?.find(c=>c.case_id===row.case_id)
 if(!trusted){
  if(answer?.execution_status&&answer.execution_status!=='SUCCESS')return {status:'执行失败',tone:'unknown'}
  if(answer?.judge_status==='FAILED'||answer?.evaluation_error)return {status:'评分未完成',tone:'unknown'}
 }
 const status=questionStatus(view,actual)
 if(status==='通过')return {status:'答对',tone:'pass'}
 if(status==='不通过')return {status:'答错',tone:'fail'}
 return {status:status==='未检查'?'未检查回答':status,tone:'unknown'}
}
