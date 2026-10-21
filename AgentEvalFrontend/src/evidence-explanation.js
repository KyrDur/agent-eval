import labels from '../../AgentEval/experiments/evidence_reason_labels.json'

// Display-only projection. The backend's frozen decision and metric inputs stay intact.
export function evidenceReasons(result,pack,state){
 if(state!=='EVIDENCE_INSUFFICIENT')return []
 if(!pack)return [{code:'FROZEN_INPUT_MISSING',message:'这份记录没有保存本题评分所需的证据包',next_step:'核对历史记录；不能由这份结果判断答案是否正确。'}]
 const codes=[...(pack.missing_items||[]),...(pack.check?.issues||[]).map(v=>v.reason),...(pack.item_checks||[]).filter(v=>v.status===state).map(v=>v.reason),...(pack.truncated_items||[]).map(v=>v.reason),...(result?.evidence_evaluation?.judgment?.insufficient_items||[])]
 const reasons=new Map()
 for(const raw of codes){const code=String(raw||'');if(!code)continue;const known=Object.keys(labels).find(k=>code.includes(k));if(known)reasons.set(known,{code:known,message:labels[known][0],next_step:labels[known][1]});else{const key=code.split(':')[0];if(!reasons.has(key))reasons.set(key,{code,message:'本题仍有需要核对的证据项',next_step:'展开本题的评分资料，核对列出的不足项和原文。'})}}
 return reasons.size?[...reasons.values()]:[{code:'INSUFFICIENT_REASON_UNRECORDED',message:'当前记录未说明具体缺口，暂时无法确定原因',next_step:'核对这道题的原始资料与评分结果，不能据此推断是知识库或模型出错。'}]
}
