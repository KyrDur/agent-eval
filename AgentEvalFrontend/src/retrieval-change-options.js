import {evidenceState,evidenceCount} from './evidence-display.js'
export const changeGroups=[
 {id:'knowledge',label:'补资料',hint:'先确认政策本身是否缺失或需要修订。'},
 {id:'retrieval',label:'改善查找',hint:'资料在库里，检查问法、召回与排序。'},
 {id:'context',label:'补全上下文',hint:'检查规则、条件和例外是否一起送到了模型。'},
 {id:'answer',label:'改善回答',hint:'对照已提供的资料，检查回答和评分。'},
]
export const changeOptions=[
 {value:'KNOWLEDGE_UPDATE',group:'knowledge',icon:'document',label:'补充或修正资料',hint:'AI 根据本题参考答案补充资料，再用原题检查。'},
 {value:'EMBEDDING_CHANGE',group:'retrieval',icon:'search',label:'更换资料匹配模型',hint:'只更换向量模型，对比中文同义问法的召回。',added:true},
 {value:'RETRIEVAL_MODE_CHANGE',group:'retrieval',icon:'compare',label:'同时按关键词和语义查找',hint:'比较向量、BM25 或两路融合，检查型号与专有词。',added:true},
 {value:'QUERY_REWRITE_TOGGLE',group:'retrieval',icon:'search',label:'换一种问法查资料',hint:'先调整查找用语，再用改写后的问题检索。'},
 {value:'CANDIDATE_POOL_CHANGE',group:'retrieval',icon:'database',label:'扩大待筛选的资料范围',hint:'先找多少段来挑：例如 20 改为 40，最后仍只给 3 段。',added:true},
 {value:'RERANK_TOGGLE',group:'retrieval',icon:'adjust',label:'把更相关的资料排到前面',hint:'重新排列同一批候选，再选前几条供回答。'},
 {value:'TOP_K_CHANGE',group:'retrieval',icon:'list',label:'让回答参考更多资料',hint:'最后给模型看多少段：例如从 3 改为 5，先找来的候选数不变。'},
 {value:'CHUNKING_CHANGE',group:'context',icon:'document',label:'尽量让条件与例外留在一起',hint:'只改变切块方式，检查主规则与例外是否被拆开。',added:true},
 {value:'CONTEXT_STRATEGY_CHANGE',group:'context',icon:'book',label:'连同前后文一起读',hint:'把查到内容旁边的说明也给 AI，避免漏读条件和例外。',added:true},
 {value:'ANSWER_PROMPT_CHANGE',group:'answer',icon:'chat',label:'调整回答规则',hint:'调整 Agent 如何核对条件、澄清并组织回答。'},
]
export const groupedChangeOptions=changeGroups.map(group=>({...group,options:changeOptions.filter(o=>o.group===group.id)}))

export function changeEvidenceSummary(view,caseId){
 const row=view?.run?.case_results?.find(c=>c.case_id===caseId),path=row?.evidence_path||{}
 const stages=[['knowledge','库内原文'],['candidates','候选召回'],['context','实际上下文']].map(([id,label])=>({id,label,status:path[id]?.status||'UNKNOWN',text:evidenceState(path[id]?.status),count:evidenceCount(path[id])}))
 let observation='必要事实尚未审核，先核对政策与本题条件；现有片段数量不能证明资料完整。'
 if(path.knowledge?.status==='MISSING')observation='已审核的必要原文在库内缺失。先核对来源，再决定是否补资料。'
 else if(path.knowledge?.status==='CONFLICT')observation='政策或来源版本存在待核对项。先处理冲突，再判断哪种查找改法适用。'
 else if(path.candidates?.status==='FULL'&&['PARTIAL','MISSING'].includes(path.context?.status))observation='必要原文已进入候选，实际上下文仍不完整。可以比较排序、截取或上下文补全，尚不能确认唯一原因。'
 else if(path.knowledge?.status==='FULL'&&['PARTIAL','MISSING'].includes(path.candidates?.status))observation='库内包含必要原文，候选尚未包含完整条件。可以检查问法、向量与关键词召回。'
 else if(path.context?.status==='FULL')observation='实际上下文包含已标注的必要原文。还需核对是否遗漏其他条件，以及回答和评分是否正确。'
 return {stages,observation,candidateCount:row?.pre_rerank_results?.length??null,contextCount:row?.results?.length??null}
}


export function recommendedNextStep(view,caseId){
 const run=view?.run,row=run?.case_results?.find(c=>c.case_id===caseId),path=row?.evidence_path||{},config=run?.retrieval_config||{}
 const answer=(view?.effective_answer_results||run?.answer_results||[]).find(c=>c.case_id===caseId)
 const result=(title,reason,action,label,method=null,alternatives=[])=>({title,reason,action,label,method,alternatives})
 if(!row)return result('还没有本题记录','先读取已保存的运行，再判断下一步。','logs','读取运行日志')
 if(path.knowledge?.review_status!=='CONFIRMED')return result('先核对本题政策','文本匹配不能证明政策适用。先确认要点、条件与例外。','review','核对本题政策')
 if(row.status!=='SUCCESS')return result('先确认执行问题','本题未取得有效检索结果，不能据此判断回答质量。','logs','查看失败记录')
 if(!run.verify_answers||answer?.execution_status!=='SUCCESS'||!answer?.turn_evidence?.some(t=>t.response?.trim()))return result('本题还没有成功回答','现在只能检查检索；完成包含回答的初测后再判断答得好不好。','answer-setup','准备包含回答的初测')
 if(answer?.judge_status==='FAILED'||answer?.evaluation_error)return result('先核对评分执行问题','回答已保存，但评分未完成；先处理执行错误，不能据此推荐回答优化。','logs','查看评分失败记录')
 if(path.knowledge?.status==='CONFLICT')return result('先处理来源与版本冲突','当前记录不足以确认适用政策。','review','核对来源版本')
 if(['PARTIAL','MISSING'].includes(path.knowledge?.status))return result('核对资料缺口','已核对清单中的必要原文没有完整留在这版资料里。','method','查看补资料方案','KNOWLEDGE_UPDATE')
 if(path.knowledge?.status==='FULL'&&['PARTIAL','MISSING'].includes(path.candidates?.status)){
  const total=run.controls?.index_snapshot?.chunks?.length,actual=row.pre_rerank_results?.length
  const canExpand=(config.rerank||config.retrieval_mode==='HYBRID')&&total!=null&&actual!=null&&actual<total
  return result('检查为什么没有查到原文','库内有必要原文，候选没有完整包含；这是召回线索，还不是根因。','method','查看查找方案','RETRIEVAL_MODE_CHANGE',canExpand?['QUERY_REWRITE_TOGGLE','CANDIDATE_POOL_CHANGE']:['QUERY_REWRITE_TOGGLE'])
 }
 if(path.candidates?.status==='FULL'&&['PARTIAL','MISSING'].includes(path.selected?.status))return result('资料查到了，但没有选中',`相关资料在候选中，最后只选 ${config.top_k??'未记录'} 条。先核对排名与截取。`,'method','查看排序方案',config.rerank?'TOP_K_CHANGE':'RERANK_TOGGLE',config.rerank?[]:['TOP_K_CHANGE'])
 if(path.selected?.status==='FULL'&&['PARTIAL','MISSING'].includes(path.context?.status))return result('选中的资料没有完整交给模型','先看上下文拼装与长度裁剪记录；补全也可能因预算再次丢失。','source','核对实际上下文')
 if(['PARTIAL','MISSING'].includes(path.context?.status))return result('检查条件和例外是否分开','当前资料不完整；查看同版本相邻原文后，再决定是否尝试补全。','source','查看命中与相邻原文')
 if(path.context?.status==='FULL'){
  const status=view?.trusted_result?.cases?.find(c=>c.case_id===caseId)?.evaluation_state||answer?.final_status||answer?.original_status
  if(status==='FAIL')return result('资料已提供，再核对回答','已标注原文包含在上下文中，回答仍未通过。可试回答规则；尚不能确认它是根因。','method','查看回答规则方案','ANSWER_PROMPT_CHANGE')
  return result('本题还没有确定的回答改进依据',status==='PASS'?'已保存判定为通过。可检查原文和回答，或用新题继续验证。':'当前缺少可用的回答判定，先核对依据与评分。','source','核对原文与回答')
 }
 return result('证据还不足以推荐改法','本次没有保存完整路径。先核对原文与运行记录。','logs','查看完整运行日志')
}
