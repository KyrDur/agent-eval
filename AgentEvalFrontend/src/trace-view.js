import {callOperation,diagnosticSteps} from './run-diagnostics.js'

export const traceDimensionNames={faithfulness:'事实与依据',conditions:'条件覆盖',relevance:'意图与相关性',actionability:'下一步可用性'}
export function responseText(call={}){
 const output=call.model_outputs
 if(typeof output==='string')return output
 if(typeof output?.content==='string')return output.content
 return (Array.isArray(output?.content)?output.content:[]).filter(block=>block?.type==='text'&&typeof block.text==='string').map(block=>block.text).join('\n')
}
export function parseSavedJson(text){
 if(typeof text!=='string')return null
 const stripped=text.trim().replace(/^```json\s*([\s\S]*?)\s*```$/,'$1')
 try{return JSON.parse(stripped)}catch{return null}
}
export function requestPayload(call={}){
 const messages=Array.isArray(call.model_inputs?.messages)?call.model_inputs.messages:[]
 const user=messages.filter(message=>message.role==='user').at(-1)
 const content=user?.content
 return parseSavedJson(typeof content==='string'?content:Array.isArray(content)?content.filter(b=>b.type==='text').map(b=>b.text).join('\n'):'')
}
export function judgeFormatIssues(call={}){
 if(Array.isArray(call.validation_issues))return call.validation_issues.map(i=>({path:i.field_path,message:i.field_path?.endsWith('.score')?`“${traceDimensionNames[i.field_path.split('.')[1]]||'分数'}”返回了 ${JSON.stringify(i.actual)??'未填写'}；要求 ${i.expected}`:`${i.code}；要求 ${i.expected??'符合评分规则'}，实际 ${JSON.stringify(i.actual)??'未填写'}`,source:'BACKEND'}))
 if(call.output_truncated)return []
 const data=parseSavedJson(responseText(call))
 if(!data||typeof data!=='object'||Array.isArray(data)||!data.dimensions||typeof data.dimensions!=='object')return []
 const issues=[]
 for(const [key,name] of Object.entries(traceDimensionNames)){
  const dimension=data.dimensions[key]
  if(!dimension||typeof dimension!=='object'){issues.push({path:`dimensions.${key}`,message:`缺少“${name}”的评分对象`});continue}
  const score=dimension.score
  if(!([0,1,2].some(value=>value===score)||score==='NA'||score==='INSUFFICIENT'))issues.push({path:`dimensions.${key}.score`,message:`“${name}”返回了 ${JSON.stringify(score)??'未填写'}；要求 0、1、2、NA 或 INSUFFICIENT`})
 }
 return issues.map(i=>({...i,source:'READ_ONLY_LEGACY_CHECK'}))
}
export function traceSteps(row={},answer=null,calls=[],verifyAnswers=false){
 const base=diagnosticSteps(row,answer,calls,verifyAnswers)
 const operations=new Set(base.map(step=>step.operation))
 for(const call of calls){const operation=callOperation(call);if(!operations.has(operation)){operations.add(operation);base.push({operation,status:'UNKNOWN',latency_ms:null})}}
 return base.map(step=>{
  const attempts=calls.map((call,index)=>({...call,request_number:index+1})).filter(call=>callOperation(call)===step.operation)
  if(step.status==='UNKNOWN'&&attempts.length)return {...step,calls:attempts,status:attempts.some(c=>c.status==='FAILED')?'FAILED':'SUCCESS'}
  return {...step,calls:attempts}
 })
}
export function preferredTraceStep(steps){return steps.find(step=>step.status==='FAILED')?.operation||steps.find(step=>step.status==='SUCCESS')?.operation||steps[0]?.operation||''}
export function traceErrorText(code){return {
 JUDGMENT_SCHEMA_INVALID:'模型返回的评分格式不符合要求',JUDGMENT_PARSE_FAILED:'评分正文未能解析为 JSON',
 FRAGMENT_ID_INVALID:'评分引用了本题不存在的片段',FRAGMENT_SCOPE_INVALID:'评分混用了回答与政策的片段编号',
 FRAGMENT_ID_DUPLICATED:'评分重复引用了同一个片段',TIMEOUT:'模型请求超时',NETWORK_ERROR:'模型连接失败',
 RATE_LIMITED:'模型服务限流',CALL_BUDGET_EXCEEDED:'已达到本次调用上限',AUTH_FAILED:'模型凭据验证失败',
 }[code]||code||'本步骤未完成'}
