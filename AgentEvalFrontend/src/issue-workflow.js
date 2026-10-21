export const issueLayers={DATA:'数据与取证',PROMPT:'Judge 提示词',RUBRIC:'业务评分标准',AGENT:'Agent'}
export const issueStatuses={OPEN:'待确认',REPRODUCED:'已复现',CHANGED:'已修改',RETESTED:'已复测',UNRESOLVED:'未解决',CLOSED:'已关闭'}
export const issueClosures={FIXED:'问题已修复',FALSE_ALARM:'误报已澄清',DEFERRED:'暂不修复'}
export const evidenceLevels={UNVERIFIED:'尚未验证修复',SAME_CASE:'原题验证',REGRESSION:'同类回归验证',UNSEEN:'未见新题验证'}
export const issueRoutes={DATA:'检查原始记录、解析与关联，保留父版本并重评固定回答。',PROMPT:'固定回答、业务标准与人工参照，进入 Judge 校准。',RUBRIC:'建立新标准研究，重新标注相关题，保留旧口径。',AGENT:'进入主实验的单项修改，固定评分条件后重新运行 Agent。'}
export const issueTransitions={OPEN:['REPRODUCED','UNRESOLVED','CLOSED'],REPRODUCED:['CHANGED','UNRESOLVED','CLOSED'],CHANGED:['RETESTED','UNRESOLVED','CLOSED'],RETESTED:['CLOSED','UNRESOLVED'],UNRESOLVED:['REPRODUCED','CLOSED'],CLOSED:[]}
export const lines=value=>String(value||'').split('\n').map(s=>s.trim()).filter(Boolean)
export function newRepairPlan(sampleId=''){
  return {success_criteria:'',target_error:'',potential_regressions:'',validation_scope:'',verification_sample_ids:sampleId?[sampleId]:[],expected_verdict:null}
}
export function repairPlan(body,sampleIds){
  return {...body,verification_sample_ids:lines(sampleIds),expected_verdict:body.expected_verdict||null}
}
