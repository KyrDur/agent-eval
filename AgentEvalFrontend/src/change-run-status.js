import {indexChangeTypes} from './change-analysis-prompt.js'
// The button and the explanation share this result, so a disabled state always
// has a visible reason and a useful next step.
export function changeRunBlocker({type,plan={},session,busy,locked,index,indexJob,indexLoading,chunkBound}={}){
 const warning=(title,detail,action='',label='')=>({title,detail,action,label,tone:'warning'})
 const info=(title,detail)=>({title,detail,tone:'info'})
 if(busy)return info('正在处理当前任务，请稍候','完成后会自动更新这里，暂时不用重复点击。')
 if(locked)return warning('本轮已有复测任务','先返回结果页查看进度，再继续下一步。','return','查看本轮结果')
 if(session?.credential_status!=='PRESENT'||session?.text_connection_status!=='READY'||session?.judge_connection?.available===false)
  return warning('模型连接还没准备好','先恢复模型连接，成功后回到这里复测。','connect','恢复模型连接')
 const autoPrepare=['CHUNKING_CHANGE','EMBEDDING_CHANGE'].includes(type)&&!index
 if(autoPrepare&&['SUBMITTING','SUBMITTED','BUILDING','UNKNOWN'].includes(indexJob?.status))
  return warning('资料还在准备，暂时不能复测','先读取准备进度；资料就绪后就能继续。','read-index','读取准备进度')
 if(indexLoading&&indexChangeTypes.includes(type))return info('正在读取补充后的资料','读取完成后，复测按钮会自动更新。')
 if(chunkBound&&indexChangeTypes.includes(type))return warning('这批题还绑定着旧资料片段','先为题目勾选对应文档，再保存题目并重新初测。','tests','去检查测试题')
 if(plan.valid||autoPrepare)return null
 if(type==='KNOWLEDGE_UPDATE'&&!index)return warning('先补充资料，再复测','点击上方「AI 整理并补充到知识库」，完成后返回这道题。','settings','去补充资料')
 if(type==='ANSWER_PROMPT_CHANGE')return warning('还没有改动回答规则','勾选上方至少一条要追加的规则，或编辑回答规则，再复测。','settings','去选择回答规则')
 if(type==='TOP_K_CHANGE')return warning('参考条数还需要调整',plan.problem||'把「最终参考」改为与原来不同的条数。','settings','去调整条数')
 if(type==='CANDIDATE_POOL_CHANGE')return warning('候选范围还需要调整',plan.problem||'把候选范围改为与原来不同的数量。','settings','去调整范围')
 return warning('当前方案还不能复测',plan.problem||'先完成上方的方案设置，再继续。','settings','去检查设置')
}
