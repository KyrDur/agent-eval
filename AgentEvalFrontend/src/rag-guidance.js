export const factNote='必要事实，就是这道题答对时不能漏掉的政策要点。例如问退款超时，至少要说明“正常到账期限”和“超过期限怎么办”。'
export const coverageNote='2/2 只表示当前清单列出的两条原文都被找到，不代表清单没有漏项。“待审核”表示还需要人核对这些要点、适用条件和例外。'
export const friendlyStages=[
 ['knowledge','知识库原文','需要的政策是否在这版资料中'],
 ['chunks','拆分后的段落','政策拆成小段后，要点是否保留'],
 ['candidates','查到的候选资料','查找时有没有找到相关段落'],
 ['selected','最后选中的资料','排序和数量限制之后是否还保留'],
 ['context','模型实际看到的资料','拼接、补全和长度处理后是否真正交给模型'],
]
export function caseGuidance(view,caseId){
 const run=view?.run,row=run?.case_results?.find(c=>c.case_id===caseId)
 const answer=view?.effective_answer_results?.find(a=>a.case_id===caseId)||run?.answer_results?.find(a=>a.case_id===caseId)
 const spec=run?.controls?.eval_set_snapshot?.cases?.find(c=>c.case_id===caseId)
 const hasAnswer=answer?.execution_status==='SUCCESS'&&!!answer.turn_evidence?.some(t=>t.response?.trim())
 const retrievalOnly=run?.verify_answers===false
 const facts=row?.evidence_path?.knowledge?.facts||[]
 const reviewed=row?.evidence_path?.knowledge?.review_status==='CONFIRMED'
 return {retrievalOnly,hasAnswer,canCompareAnswer:!!hasAnswer&&!retrievalOnly,reviewed,facts,spec,
  firstStep:reviewed?'清单已有审核记录，接下来核对实际提供的资料是否包含完整条件。':'先核对这道题不能漏掉的政策要点，再看系统有没有找到它们。',
  missingAnswer:retrievalOnly?'本轮只检查了资料查找，没有生成客服回答，所以这里还不能判断回答对错。':'本题没有成功保存回答。先查看运行日志并解决执行问题，再检查回答。'}
}
export function candidateGuidance(view,caseId,type,nextK,candidatePool){
 const run=view?.run,row=run?.case_results?.find(c=>c.case_id===caseId),config=run?.retrieval_config||{}
 const pool=config.candidate_pool_size??20,k=config.top_k??3,mode=config.retrieval_mode||'VECTOR'
 const direct=!config.rerank&&mode!=='HYBRID'
 const candidates=row?.pre_rerank_results?.length??null,total=run?.controls?.index_snapshot?.chunks?.length??null
 return {pool,k,mode,actual:candidates,rerank:!!config.rerank,nextPool:type==='CANDIDATE_POOL_CHANGE'?candidatePool:pool,nextK:type==='TOP_K_CHANGE'?nextK:k,
  explanation:type==='CANDIDATE_POOL_CHANGE'?`先从知识库找 ${pool} 段来挑，再选 ${k} 段给回答模型。这次只改“先找多少”，最后仍给 ${k} 段。`:`先找来的候选仍是 ${pool} 段。这次只改“最后给多少”，从 ${k} 段改为 ${Number.isInteger(nextK)?nextK:'待填写'} 段。`,
  limitedByCorpus:type==='CANDIDATE_POOL_CHANGE'&&total!=null&&candidates===total&&pool>=total?`当前索引一共 ${total} 段，本题已经找来了全部 ${candidates} 段。继续增大上限不会多出新片段；先检查资料是否正确、排序和最终条数。`:null,
  caution:type==='CANDIDATE_POOL_CHANGE'&&direct?'这轮没有开启重排，使用的也是单路检索。扩大候选池通常不会改变最终给模型的前几段；若想让模型看到更多资料，应比较“最终提供条数（Top K）”。':null,
  observed:candidates==null?'这份历史记录没有保存候选数量。':`本题上次实际找来了 ${candidates} 段；配置是上限，知识库较小时不一定找满。`}
}
