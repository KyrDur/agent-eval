import {checkLabels} from './trusted-results.js'

export function questionLabel(number){
 const digits=['','一','二','三','四','五','六','七','八','九']
 const value=number<10?digits[number]:number<100?`${number>=20?digits[Math.floor(number/10)]:''}十${digits[number%10]}`:String(number)
 return `第${value}题`
}
export function selectedQuestion(items,id){return items.find(item=>item.case_id===id)||items[0]||null}
export function answerExplanation(answer){
 if(answer?.judge_status==='FAILED'||answer?.evaluation_error||answer?.evidence_evaluation?.status==='PARSE_ERROR')return '评分未完成。打开运行日志，查看评分模型的返回和具体错误。'
 if(answer?.execution_status&&answer.execution_status!=='SUCCESS')return 'Agent 的回答未完成。打开运行日志，查看失败的步骤。'
 return answer?.original_reason||'本题尚未形成判定，请查看运行日志。'
}
export function questionStatus(view,row){
 const state=view.trusted_result?.cases?.find(c=>c.case_id===row.case_id)?.evaluation_state
 if(state&&view.run.verify_answers)return checkLabels[state]||'待判断'
 if(view.run.verify_answers){
  const answer=view.effective_answer_results?.find(c=>c.case_id===row.case_id)
  return checkLabels[answer?.human_evaluation_state||answer?.final_status]||({INVALID:'执行失败',PENDING:'待判断'})[answer?.final_status]||'待判断'
 }
 return {TOP_1_HIT:'已找到',LOWER_RANK_HIT:'已找到',NOT_RETRIEVED:'未找到',UNLABELED:'未标注',INVALID:'执行失败'}[row.retrieval_status]||'待判断'
}
