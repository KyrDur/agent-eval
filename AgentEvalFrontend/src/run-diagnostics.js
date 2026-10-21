export const operationNames = {
  QUERY_REWRITE:'查询改写', RETRIEVAL:'检索候选', RERANK:'重排候选', ANSWER:'生成回答', JUDGE:'评测回答',
  GENERAL:'客服模型', TECHNICAL:'技术客服', BILLING:'账单客服', INTENT:'识别意图', COMPOSER:'整理回答', ESCALATION:'升级处理',
}
export const statusNames = {SUCCESS:'完成',FAILED:'失败',SKIPPED:'未开启',NOT_RUN:'未执行',UNKNOWN:'未记录',RUNNING:'进行中'}
const number = value => typeof value === 'number' && Number.isFinite(value) && value >= 0
export function elapsed(value){return number(value) ? `${(value/1000).toFixed(value>=1000 ? 2 : 3)} 秒` : '未记录'}
export function callOperation(call){return call.operation || (call.stage === 'judge' ? 'JUDGE' : (call.stage || 'MODEL').toUpperCase())}
export function callUsage(call){
  const usage=call.usage
  return usage && number(usage.input_tokens) && number(usage.output_tokens)
    ? {input:usage.input_tokens,output:usage.output_tokens,total:usage.input_tokens+usage.output_tokens} : null
}
export function tokenSummary(calls, recorded=false){
  if(!calls.length)return recorded ? {text:'未调用模型',known:0,missing:0} : {text:'历史未记录',known:0,missing:null}
  const known=calls.map(callUsage).filter(Boolean),missing=calls.length-known.length,total=known.reduce((n,u)=>n+u.total,0)
  return {text:known.length ? `${total.toLocaleString()}${missing ? ` · ${missing} 次用量缺失` : ''}` : calls.every(c=>!c.trace_version)?'历史未记录':'提供商未提供',known:total,missing}
}
export function diagnoseCase(row={}, answer=null, verifyAnswers=false, mode='evaluation'){
  const error=row.error || answer?.turn_evidence?.find(t=>t.execution_error)?.execution_error
  if(row.status && row.status!=='SUCCESS'){
    const stage=row.steps?.find(s=>s.status==='FAILED')?.operation || (row.rewrite_status==='FAILED'?'QUERY_REWRITE':row.rerank_status==='FAILED'?'RERANK':'RETRIEVAL')
    const local=stage==='RETRIEVAL'
    return {kind:'execution',tone:'danger',title:`${operationNames[stage]}未完成`,detail:`本题没有有效检索结果${error ? `：${error}` : '。'}`,
      next:local?'先检查本地检索模型、索引和知识版本，再重新运行这题。':'先查看失败调用的输入与错误码，核对模型配置、连接或限流状态。'}
  }
  if(answer?.execution_status && answer.execution_status!=='SUCCESS')return {kind:'answer_error',tone:'danger',title:'回答生成未完成',detail:'检索结束后，Agent 没有形成有效回答。',next:'展开生成回答的模型调用，先检查错误码、模型输入输出与连接状态。'}
  if(answer?.judge_status==='FAILED' || answer?.evaluation_error)return {kind:'judge_error',tone:'danger',title:'评分未形成有效结论',detail:answer.execution_status==='SUCCESS'?'回答已生成，但 Judge 或评分解析失败；这不代表回答质量未通过。':'Judge 或评分解析未完成，无法使用这次质量判定。',next:'核对 Judge 的实际输入、原始输出和错误码，再判断是否需要重新评测。'}
  if(answer?.evidence_evaluation?.judgment?.verdict==='PENDING')return {kind:'evidence_pending',tone:'warning',title:'评分所需证据不足',detail:'Judge 已返回，但冻结规则要求保留待判断状态。',next:'查看各维度列出的证据不足项，补充依据或进行人工核对。'}
  if(mode==='evaluation' && (row.metrics?.unavailable_reason==='NO_RELEVANCE_LABELS' || row.retrieval_status==='UNLABELED'))return {kind:'labels',tone:'warning',title:'缺少正确知识标签',detail:'目前无法判断检索是否找对了资料。',next:'先在测试题中确认相关文档或片段标签，再运行检索评测。'}
  if(mode==='evaluation' && row.metrics?.recall_at_k===0){
    const inPool=row.metrics?.relevant_rank!=null
    return {kind:inPool?'outside_k':'not_retrieved',tone:'warning',title:inPool?'正确知识未进入返回结果':'候选池未找到正确知识',
      detail:inPool?`正确知识在候选池第 ${row.metrics.relevant_rank} 位，本次只返回前 ${row.top_k} 条。`:'按这题的现有标签，检索候选没有命中正确知识。',
      next:inPool?'先对照重排前后的顺序；选择重排或 Top K 中一个变量，固定题目后复测。':'先核对政策是否存在、标签是否正确，再检查查询表达和检索模型。'}
  }
  if(mode==='evaluation' && number(row.metrics?.recall_at_k) && row.metrics.recall_at_k<1)return {kind:'partial_retrieval',tone:'warning',title:'只找到部分正确知识',detail:'返回资料未覆盖这题标注的全部相关知识。',next:'查看遗漏的是哪条政策或条件，再选择一个检索变量验证。'}
  if(answer?.hard_rule_violations?.length)return {kind:'rule',tone:'warning',title:'回答触发禁止行为',detail:answer.hard_rule_violations.join('；'),next:'对照实际回答和禁止行为规则，先核验违规证据，再决定修改或人工复核。'}
  if(answer?.final_status==='FAIL' || answer?.original_status==='FAIL')return {kind:'quality',tone:'warning',title:'回答质量判定未通过',detail:answer.original_reason || '相关资料已经返回，仍需核对回答与评分依据。',next:'对照回答、检索片段与 Judge 原始输出，区分回答遗漏和评分标准问题。'}
  if(!verifyAnswers && !answer)return {kind:'retrieval_only',tone:'neutral',title:'本轮只检查了检索',detail:'没有生成最终回答，也没有调用 Judge。',next:'要排查回答质量，请在新运行中开启“同时验证最终回答”。'}
  if(answer?.final_status==='PASS')return {kind:'pass',tone:'positive',title:'本题当前判定通过',detail:'检索与回答结果仍可展开核对。',next:'检查政策条件与例外是否覆盖，并保留这题用于后续回归。'}
  return {kind:'ungraded',tone:'neutral',title:'回答已生成，质量尚待核验',detail:'运行成功不代表回答已经通过质量评测。',next:'对照实际检索片段核验回答；有问题时加入测试，确认预期行为。'}
}
export function diagnosticSteps(row={},answer=null,calls=[],verifyAnswers=false){
  const byName=new Map((row.steps || []).map(step=>[step.operation,step]))
  const callStep=name=>{
    const found=calls.filter(call=>callOperation(call)===name)
    return found.length ? {operation:name,status:found.some(c=>c.status==='FAILED')?'FAILED':'SUCCESS',
      latency_ms:found.every(c=>number(c.latency_ms))?found.reduce((n,c)=>n+c.latency_ms,0):null,
      timing_scope:'MODEL_CALLS',error:found.find(c=>c.error)?.error} : null
  }
  return ['QUERY_REWRITE','RETRIEVAL','RERANK','ANSWER','JUDGE'].map(name=>{
    if(byName.has(name))return byName.get(name)
    const call=callStep(name)
    if(name==='JUDGE' && (answer?.judge_status==='FAILED' || answer?.evaluation_error))return {
      ...(call || {}),operation:name,status:'FAILED',latency_ms:call?.latency_ms ?? null,
      error:call?.error || answer.judge_error || answer.evaluation_error || '评分未形成有效结论'}
    if(name==='ANSWER' && answer?.execution_status && answer.execution_status!=='SUCCESS')return {
      ...(call || {}),operation:name,status:'FAILED',latency_ms:call?.latency_ms ?? null,
      error:answer.turn_evidence?.find(t=>t.execution_error)?.execution_error || '回答未形成有效结果'}
    if(call)return call
    let status='UNKNOWN'
    if(name==='QUERY_REWRITE')status=row.rewrite_status==='NOT_REQUIRED'?'SKIPPED':row.rewrite_status || 'UNKNOWN'
    if(name==='RETRIEVAL')status=row.status==='SUCCESS'?'SUCCESS':row.status?'NOT_RUN':'UNKNOWN'
    if(name==='RERANK')status=row.rerank_status==='NOT_REQUIRED'?(row.rerank_enabled?'NOT_RUN':'SKIPPED'):row.rerank_status || 'NOT_RUN'
    if(name==='ANSWER')status=answer?.execution_status==='SUCCESS'?'SUCCESS':answer?.execution_status?'FAILED':verifyAnswers?'NOT_RUN':'SKIPPED'
    if(name==='JUDGE')status=answer?.judge_status==='NOT_REQUIRED'?'SKIPPED':answer?.judge_status==='SUCCESS'?'SUCCESS':answer?.judge_status==='FAILED'?'FAILED':verifyAnswers?'NOT_RUN':'SKIPPED'
    return {operation:name,status,latency_ms:null,error:null}
  })
}
