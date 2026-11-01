const canonical=value=>JSON.stringify(value&&typeof value==='object'&&!Array.isArray(value)?Object.fromEntries(Object.keys(value).sort().map(k=>[k,JSON.parse(canonical(value[k]))])):value??null)
const config=value=>({retrieval_mode:'VECTOR',context_strategy:'SELECTED',...value})
export function trialMatches(trial,{view,caseId,type,afterConfig,index,session}={}){
 const inputs=trial?.flow?.inputs
 if(!inputs||inputs.execution_mode!=='TRIAL'||inputs.baseline_run_id!==view?.run.run_id||inputs.change_type!==type||inputs.selected_case_ids?.length!==1||inputs.selected_case_ids[0]!==caseId)return false
 if(session&&inputs.provider_session_id!==session.provider_session_id)return false
 if(canonical(config(inputs.after_config))!==canonical(config(afterConfig)))return false
 if(index&&['KNOWLEDGE_UPDATE','CHUNKING_CHANGE','EMBEDDING_CHANGE'].includes(type)&&![inputs.target_index_id,trial.flow.index_id].includes(index.index_id))return false
 return true
}
export function trialFinished(trial){return trial?.flow?.stage==='COMPLETE'&&trial?.view?.run.status==='COMPLETE'}
export function trialUsesHistoricalReference(trial,baseline){return baseline?.current_implementation_matches===false||trial?.view?.run.controls?.evaluation_scope?.historical_reference_only===true||trial?.view?.run.experiment_identity?.comparison_eligible===false}

// A saved single-case observation is readable independently of draft parameters.
// Never attach another experiment's trial, or silently substitute another case.
export function savedTrialComparison(trial,baseline){
 const inputs=trial?.flow?.inputs,run=trial?.view?.run,base=baseline?.run,ids=inputs?.selected_case_ids
 if(!run||!base||inputs?.execution_mode!=='TRIAL'||inputs.baseline_run_id!==base.run_id||ids?.length!==1)return null
 const caseId=ids[0]
 if(run.parent_run_id&&run.parent_run_id!==base.run_id)return null
 if(run.execution_order?.length!==1||run.execution_order[0]!==caseId)return null
 const before=base.case_results?.find(c=>c.case_id===caseId),after=run.case_results?.find(c=>c.case_id===caseId)
 if(!before||!after)return null
 const beforeAnswer=baseline.effective_answer_results?.find(a=>a.case_id===caseId)?.turn_evidence?.map(t=>t.response||'').join('\n\n')
 const afterAnswer=trial.view.effective_answer_results?.find(a=>a.case_id===caseId)?.turn_evidence?.map(t=>t.response||'').join('\n\n')
 const left=before.results||[],right=after.results||[],same=(a,b)=>a.document_id===b.document_id&&a.text===b.text
 return {caseId,question:before.query,total:base.execution_order?.length??base.case_results.length,
  complete:trialFinished(trial),historical:trialUsesHistoricalReference(trial,baseline),
  answerChanged:beforeAnswer&&afterAnswer?beforeAnswer!==afterAnswer:null,
  added:right.filter(x=>!left.some(y=>same(x,y))).length,removed:left.filter(x=>!right.some(y=>same(x,y))).length}
}
