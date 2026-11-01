import { reactive } from 'vue'
import {flowController} from './retest-flow.js'
import {indexBuildController} from './index-build.js'
import { api,ApiError } from './api.js'
import {pendingFields,pendingReceipt,runFingerprint} from './run-receipt.js'
import { analytics } from './analytics.js'
import {supplementReference,latestReferenceSupplement} from './knowledge-supplement.js'
const key = 'agenteval.retrieval.v1'
const fields = ['knowledge','index','evalSet','baseline','retest','change','comparison','session','answerSetup','supplementCase','trial',...pendingFields]
export function readRetrievalPointers(storage) {
  try { const p=JSON.parse(storage.getItem(key) || '{}');return Object.fromEntries(fields.filter(k => typeof p[k]==='string' && /^[A-Za-z0-9_-]{1,128}$/.test(p[k])).map(k=>[k,p[k]])) } catch {return {}}
}
export function createRetrievalWorkspace(work, storage = globalThis.localStorage, client = api, {pollMs=1200,autoPoll=true} = {}) {
  const state=reactive({ answerSetupSource:null,coverageReviewTarget:null,supplementCaseId:readRetrievalPointers(storage).supplementCase||null,indexJob:null,knowledge:null,index:null,evalSet:null,baseline:null,retest:null,change:null,comparison:null,preview:null,trialResult:null,trialFlowId:readRetrievalPointers(storage).trial||null,history:[],preferredChange:null,pendingSubmission:pendingReceipt(readRetrievalPointers(storage)),progressIssue:'',canRetrySubmission:false,flow:null })
  let restoring=false
  let pollTimer=null,pollGeneration=0,readFailures=0
  const readOptions={timeoutMs:10000,retryReads:true}
  async function readRun(id){
    const view=await client.get('/retrieval-runs/'+id,readOptions)
    if(view?.run?.run_id!==id)throw new ApiError('RUN_RECEIPT_INVALID',502)
    return view
  }
  function stopPolling(){clearTimeout(pollTimer);pollGeneration++}
  const writePointers=()=>storage.setItem(key,JSON.stringify(Object.fromEntries(Object.entries({knowledge:state.knowledge?.knowledge_dataset_id,
    index:state.index?.index_id,evalSet:state.evalSet?.retrieval_eval_set_id,baseline:state.baseline?.run.run_id,retest:state.retest?.run.run_id,
    change:state.change?.change_id,comparison:state.comparison?.comparison_id,session:work.state.session?.provider_session_id,
    trial:state.trialFlowId,answerSetup:state.answerSetupSource?.runId,supplementCase:state.supplementCaseId,pendingRequest:state.pendingSubmission?.request_id,pendingFingerprint:state.pendingSubmission?.fingerprint,
    pendingType:state.pendingSubmission?.run_type,pendingRun:state.pendingSubmission?.run_id}).filter(([,v])=>v))))
  const persist=()=>{if(!restoring)try{writePointers()}catch{work.state.notice='浏览器暂时无法保存入口，请保留当前页面；服务器已有任务不受影响。'}}
  const action=(label,fn)=>work.action(label,async()=>{const r=await fn();persist();return r})
  function applyView(view){
    if(view.run.run_type==='RETEST'){
      state.retest=view
      if(state.change?.target_eval_set_id&&view.run.controls?.eval_set_snapshot?.retrieval_eval_set_id===state.change.target_eval_set_id)state.evalSet=view.run.controls.eval_set_snapshot
    }else {state.baseline=view;if(state.answerSetupSource&&state.answerSetupSource.runId!==view.run.run_id)state.answerSetupSource=null}
    if(state.pendingSubmission&&(state.pendingSubmission.run_id===view.run.run_id||state.pendingSubmission.request_id===view.run.request_id)){
      state.pendingSubmission=null;state.canRetrySubmission=false
    }
    state.progressIssue='';persist()
  }
  function pollKnownRun(resetFailures=true){
    stopPolling();if(resetFailures)readFailures=0
    if(!autoPoll)return
    const generation=pollGeneration
    const id=state.pendingSubmission?.run_id||[state.retest,state.baseline].find(v=>v?.run.status==='RUNNING')?.run.run_id
    if(!id)return
    pollTimer=setTimeout(async()=>{
      try{
        const view=await readRun(id)
        if(generation!==pollGeneration)return
        applyView(view);pollKnownRun()
      }catch{
        if(generation!==pollGeneration)return
        state.progressIssue='进度暂时未读到，已保留这次任务；可以重新读取，不需要再次开始评测。'
        if(++readFailures<3)pollKnownRun(false)
      }
    },Math.max(pollMs,readFailures*2500))
    pollTimer?.unref?.()
  }
  async function resolveReceipt(){
    const pending=state.pendingSubmission
    if(!pending)return null
    if(pending.run_id)return pending.run_id
    state.canRetrySubmission=false
    try{
      const receipt=await client.get('/retrieval-run-tasks/'+pending.request_id,readOptions)
      if(state.pendingSubmission!==pending)return null
      if(receipt?.request_id!==pending.request_id||(receipt.run_id&&!/^[A-Za-z0-9_-]{1,128}$/.test(receipt.run_id)))throw new ApiError('RUN_RECEIPT_INVALID',502)
      if(receipt.run_id){pending.run_id=receipt.run_id;persist();return receipt.run_id}
      state.progressIssue='服务器正在确认这次提交，请稍后重新读取；不会自动重复提交。'
    }catch(error){
      if(state.pendingSubmission!==pending)return null
      state.canRetrySubmission=error.status===404&&error.code==='RUN_RECEIPT_NOT_FOUND'
      state.progressIssue=state.canRetrySubmission?'暂未找到这次提交的回执。可以按原参数重试，系统会沿用同一个请求编号。':'提交结果还未确认，已保存原请求编号；请重新读取，不要重复开始评测。'
    }
    return null
  }
  async function readProgress(){
    stopPolling()
    const generation=pollGeneration
    const id=state.pendingSubmission?await resolveReceipt():[state.retest,state.baseline].find(Boolean)?.run.run_id
    if(!id||generation!==pollGeneration)return
    try{
      const view=await readRun(id)
      if(generation!==pollGeneration)return
      applyView(view)
    }catch{
      if(generation!==pollGeneration)return
      state.progressIssue='评测已提交，进度暂时未读到。原任务已保留，重新读取不会再次运行评测。'
    }
    if(generation===pollGeneration)pollKnownRun()
  }
  async function writeKnowledge(body){
    state.knowledge=await client.post('/knowledge-datasets',body)
    Object.assign(state,{answerSetupSource:null,index:null,evalSet:null,retest:null,change:null,comparison:null})
    // Keep the saved version recoverable if preparing its index fails next.
    persist()
  }
  const indexBuild=indexBuildController({client,storage,onChange:job=>{state.indexJob=job},onReady:async index=>{
    // The user may have selected another dataset while the worker was running.
    if(state.knowledge?.knowledge_dataset_id!==index.knowledge_dataset_id||state.knowledge?.version!==index.knowledge_version)return
    if(state.index?.index_id!==index.index_id)state.evalSet=latestReferenceSupplement(state.knowledge,state.baseline?.run.run_id)?state.baseline.run.controls.eval_set_snapshot:null
    state.index=index
    if(latestReferenceSupplement(state.knowledge,state.baseline?.run.run_id)&&work.state.step==='knowledge')work.state.notice='已补充到知识库，可以返回本题复测。'
    persist()
  }})
  const flow=flowController({client,storage,pollMs,autoPoll,onChange:value=>{state.flow=value},onArtifacts:async value=>{
    if(value.inputs?.baseline_run_id&&state.baseline?.run.run_id!==value.inputs.baseline_run_id)return
    if(value.change_id&&state.change?.change_id!==value.change_id)state.change=await client.get('/retrieval-changes/'+value.change_id)
    if(value.run_id){
      if(value.inputs?.execution_mode==='TRIAL'){state.trialFlowId=value.flow_id;state.trialResult={flow:value,view:await client.get('/retrieval-trial-runs/'+value.run_id,readOptions)}}
      else {const view=await readRun(value.run_id);state.retest=view}
    }
    if(value.comparison_id&&state.comparison?.comparison_id!==value.comparison_id){
      state.comparison=await client.get('/retrieval-comparisons/'+value.comparison_id)
      if(['improve','evaluate'].includes(work.state.step))work.go('compare')
    }
    persist()
  }})
  async function supplementFromReference({view,caseId}){
    return action('AI 整理并补充资料',async()=>{
      try{
        const assertCurrent=()=>{if(state.baseline?.run.run_id!==view?.run.run_id||state.retest)throw new Error('当前实验已变化，请返回本题结果后再补充。')}
        assertCurrent()
        if(state.indexJob&&['SUBMITTING','SUBMITTED','BUILDING','UNKNOWN'].includes(state.indexJob.status))throw new Error('资料仍在准备中，请先读取当前准备进度。')
        const result=await supplementReference({view,caseId,session:work.state.session,client,assertCurrent})
        assertCurrent()
        const previousIndex=state.index
        Object.assign(state,{knowledge:result.knowledge,index:previousIndex?.knowledge_version===result.knowledge.version&&previousIndex?.knowledge_dataset_id===result.knowledge.knowledge_dataset_id?previousIndex:null,
          evalSet:view.run.controls.eval_set_snapshot,change:null,comparison:null,preferredChange:'KNOWLEDGE_UPDATE',supplementCaseId:caseId})
        persist();work.go('knowledge')
        work.state.notice=result.alreadyAdded?'这题的参考答案已在知识库中，没有重复添加。':'已补充到知识库，正在准备资料查找。'
        if(!state.index)await indexBuild.start(result.knowledge,result.source.index.chunk_config,result.source.index.embedding_snapshot.model)
        return result
      }catch(error){
        if(error instanceof ApiError)throw error
        const failure=new ApiError('KNOWLEDGE_SUPPLEMENT_FAILED',400)
        failure.title='资料补充未完成';failure.message=error.message||'请保留本题记录后重试。'
        throw failure
      }
    })
  }
  async function writeIndex(chunk_config,embedding_model){return indexBuild.start(state.knowledge,chunk_config,embedding_model)}
  async function open(id,{persistSelection=true,includeLatestRetest=true,useFrozenControls=false}={}) {
    stopPolling()
    const v=await readRun(id)
    if(useFrozenControls){
      const [base,session,change]=await Promise.all([
        v.run.run_type==='BASELINE'?v:readRun(v.run.parent_run_id),
        client.get('/provider-sessions/'+v.run.provider_session_id,readOptions),
        v.run.change_id?client.get('/retrieval-changes/'+v.run.change_id,readOptions):null,
      ])
      const controls=v.run.controls
      Object.assign(state,{baseline:base,retest:v.run.run_type==='RETEST'?v:null,
        knowledge:controls.knowledge_snapshot,index:controls.index_snapshot,evalSet:controls.eval_set_snapshot,
        change,comparison:null})
      work.state.session=session
      if(persistSelection)persist()
      pollKnownRun();return
    }
    state.baseline=v.run.run_type==='BASELINE'?v:await readRun(v.run.parent_run_id)
    const other=includeLatestRetest?state.history.filter(r=>r.parent_run_id===state.baseline.run.run_id).sort((a,b)=>a.created_at.localeCompare(b.created_at)).at(-1):null
    state.retest=v.run.run_type==='RETEST'?v:other?await client.get('/retrieval-runs/'+other.run_id):null
    const controls=(state.retest || state.baseline).run.controls
    state.knowledge=await client.get(`/knowledge-datasets/${controls.knowledge_snapshot.knowledge_dataset_id}?version=${controls.knowledge_snapshot.version}`)
    state.index=await client.get('/knowledge-indices/'+controls.index_snapshot.index_id)
    state.evalSet=await client.get(`/retrieval-evalsets/${controls.eval_set_snapshot.retrieval_eval_set_id}?version=${controls.eval_set_snapshot.version}`)
    state.change=state.retest?.run.change_id?await client.get('/retrieval-changes/'+state.retest.run.change_id):null
    state.comparison=null
    work.state.session=await client.get('/provider-sessions/'+v.run.provider_session_id)
    if(persistSelection)persist()
    pollKnownRun()
  }
  async function restoreState({resultsOnly=false}={}) {
    const p=readRetrievalPointers(storage)
    if(p.answerSetup&&!state.pendingSubmission&&!p.baseline&&!p.retest){
      const source=await readRun(p.answerSetup),controls=source.run.controls
      if(p.index===controls.index_snapshot.index_id&&p.evalSet===controls.eval_set_snapshot.retrieval_eval_set_id&&p.knowledge===controls.knowledge_snapshot.knowledge_dataset_id){
        Object.assign(state,{evalSet:controls.eval_set_snapshot,index:controls.index_snapshot,knowledge:controls.knowledge_snapshot,answerSetupSource:{runId:p.answerSetup,config:source.run.retrieval_config}})
        work.state.session=await client.get('/provider-sessions/'+(p.session||source.run.provider_session_id));persist();return
      }
    }
    if(resultsOnly){
      const receiptId=state.pendingSubmission?await resolveReceipt():null
      const id=receiptId||(!state.pendingSubmission&&(p.retest||p.baseline))
      if(id){
        await open(id,{persistSelection:false,includeLatestRetest:false,useFrozenControls:true})
        if(state.pendingSubmission?.run_id===id){state.pendingSubmission=null;state.canRetrySubmission=false;state.progressIssue=''}
        persist();return
      }
    }
    if(state.pendingSubmission){try{state.history=await client.get('/retrieval-history')}catch{state.history=[]}}
    else state.history=await client.get('/retrieval-history')
    const pendingType=state.pendingSubmission?.run_type,receiptId=state.pendingSubmission?await resolveReceipt():null
    if(p.session) work.state.session=await client.get('/provider-sessions/'+p.session)
    if(p.index) state.index=await client.get('/knowledge-indices/'+p.index)
    if(p.knowledge) state.knowledge=await client.get('/knowledge-datasets/'+p.knowledge+(state.index?.knowledge_dataset_id===p.knowledge?`?version=${state.index.knowledge_version}`:''))
    if(p.evalSet) {
      state.evalSet=await client.get('/retrieval-evalsets/'+p.evalSet)
      state.index=await client.get('/knowledge-indices/'+state.evalSet.index_id)
      state.knowledge=await client.get(`/knowledge-datasets/${state.index.knowledge_dataset_id}?version=${state.index.knowledge_version}`)
    }
    const baseline=(pendingType==='BASELINE'&&receiptId?receiptId:p.baseline) || (!state.pendingSubmission&&!p.answerSetup?state.history.filter(r=>r.run_type==='BASELINE' && r.retrieval_eval_set_id===state.evalSet?.retrieval_eval_set_id && r.version===state.evalSet?.version)
      .sort((a,b)=>a.created_at.localeCompare(b.created_at)).at(-1)?.run_id:null)
    if(receiptId||baseline) await open(receiptId||p.retest||baseline,{persistSelection:false,includeLatestRetest:!receiptId})
    // A recovered receipt owns its frozen controls. Old pointers may belong to
    // an earlier experiment if the original POST response never reached us.
    if(!receiptId){
      if(p.change) state.change=await client.get('/retrieval-changes/'+p.change)
      if(p.comparison) state.comparison=await client.get('/retrieval-comparisons/'+p.comparison)
      if(p.knowledge) state.knowledge=await client.get('/knowledge-datasets/'+p.knowledge)
      if(p.index){state.index=await client.get('/knowledge-indices/'+p.index);state.knowledge=await client.get(`/knowledge-datasets/${state.index.knowledge_dataset_id}?version=${state.index.knowledge_version}`)}
      else if(p.knowledge)state.index=null
      if(p.evalSet)state.evalSet=await client.get('/retrieval-evalsets/'+p.evalSet)
      if(p.session) work.state.session=await client.get('/provider-sessions/'+p.session)
    }
    if(p.answerSetup&&!state.baseline){const source=await readRun(p.answerSetup);if(source.run.controls.eval_set_snapshot.retrieval_eval_set_id===state.evalSet?.retrieval_eval_set_id&&source.run.controls.eval_set_snapshot.version===state.evalSet?.version&&source.run.controls.index_snapshot.index_id===state.index?.index_id)state.answerSetupSource={runId:p.answerSetup,config:source.run.retrieval_config}}
    if(state.pendingSubmission?.run_id&&(state.pendingSubmission.run_id===state.baseline?.run.run_id||state.pendingSubmission.run_id===state.retest?.run.run_id)){state.pendingSubmission=null;state.canRetrySubmission=false;state.progressIssue=''}
    persist()
  }
  async function restore(options){stopPolling();restoring=true;try{await restoreState(options)}finally{restoring=false}persist();pollKnownRun();await indexBuild.resume();await flow.restore();const saved=readRetrievalPointers(storage).trial;if(saved&&saved!==state.flow?.flow_id){const value=await client.get('/retest-flows/'+saved,readOptions);if(value.inputs?.baseline_run_id===state.baseline?.run.run_id&&value.run_id){state.trialFlowId=saved;state.trialResult={flow:value,view:await client.get('/retrieval-trial-runs/'+value.run_id,readOptions)}}}}
  return {state,action,persist,restore,open,supplementFromReference,resumePolling:()=>{pollKnownRun();flow.restore()},
    syncProgress:()=>action('读取本次评测进度',readProgress),
    dispose:()=>{stopPolling();indexBuild.dispose();flow.dispose()},
    executePlan:body=>action('复测全部原题',()=>flow.start({...body,execution_mode:'FULL'})),
    executeTrial:body=>action('快速试当前这一题',()=>flow.start({...body,execution_mode:'TRIAL'})),
    syncFlow:()=>action('读取方案执行回执',flow.sync),resumeFlow:()=>action('核对回执后继续',flow.resume),cancelFlow:()=>action('停止后续任务',flow.cancel),
    syncIndex:indexBuild.resume,cancelIndex:()=>action('停止索引构建',indexBuild.cancel),retryIndex:()=>action('按原请求重试索引',indexBuild.retry),
    reset(){stopPolling();flow.clear();Object.assign(state,{trialResult:null,trialFlowId:null,answerSetupSource:null,coverageReviewTarget:null,supplementCaseId:null,knowledge:null,index:null,evalSet:null,baseline:null,retest:null,change:null,comparison:null,preview:null,scoreCheckSelection:null,pendingSubmission:null,progressIssue:'',canRetrySubmission:false});persist()},
    saveKnowledge:(body)=>action('保存知识版本',()=>writeKnowledge(body)),
    buildIndexFor:(dataset,chunk_config,embedding_model)=>action('建立单变量对照索引',()=>indexBuild.start(dataset,chunk_config,embedding_model)),
    buildIndex:(chunk_config, embedding_model='all-MiniLM-L6-v2')=>action('建立冻结索引',()=>writeIndex(chunk_config,embedding_model)),
    prepareKnowledge:(body,chunk_config,embedding_model='all-MiniLM-L6-v2')=>analytics.withPreparation(()=>action('保存资料并准备评测',async()=>{
      if(body)await writeKnowledge(body)
      await writeIndex(chunk_config,embedding_model)
    })),
    saveCoverageReview:(body,source)=>action('保存本题核对后的新题集',async()=>{
      const ev=await client.post('/retrieval-evalsets',{...body,index_id:source.index.index_id})
      Object.assign(state,{answerSetupSource:null,evalSet:ev,index:source.index,knowledge:source.knowledge,baseline:null,retest:null,change:null,comparison:null,coverageReviewTarget:null})
      work.go('evaluate');work.state.notice='已另存核对后的题集。原运行和其他题的审核状态保留；请重新初测。';return ev
    }),
    saveEvalset:(body)=>action('保存检索测试题',async()=>{state.evalSet=await client.post('/retrieval-evalsets',{...body,index_id:state.index.index_id});state.baseline=null;state.retest=null;state.change=null;state.comparison=null;work.go('evaluate')}),
    run:(type,config,verifyAnswers,scoringProfileId=null)=>action(type==='BASELINE'?'运行检索 Baseline':'运行检索 Retest',async()=>{
      stopPolling();const generation=pollGeneration
      const body={provider_session_id:work.state.session.provider_session_id,retrieval_eval_set_id:type==='RETEST'&&state.change.target_eval_set_id?state.change.target_eval_set_id:state.evalSet.retrieval_eval_set_id,
        version:type==='RETEST'&&state.change.target_eval_set_id?1:state.evalSet.version,run_type:type,verify_answers:verifyAnswers}
      if(type==='RETEST')Object.assign(body,{parent_run_id:state.baseline.run.run_id,change_id:state.change.change_id,
        verify_answers:state.baseline.run.verify_answers})
      else {body.retrieval_config=config;if(verifyAnswers&&scoringProfileId)body.scoring_profile_id=scoringProfileId}
      const fingerprint=await runFingerprint(body)
      if(generation!==pollGeneration)return
      if(state.pendingSubmission&&state.pendingSubmission.fingerprint!==fingerprint)throw new ApiError('PENDING_EVALUATION_EXISTS',409)
      if(state.pendingSubmission&&!state.canRetrySubmission){work.go('evaluate');await readProgress();return}
      if(!state.pendingSubmission)state.pendingSubmission={fingerprint,request_id:crypto.randomUUID(),run_type:type,run_id:null}
      const pending=state.pendingSubmission
      state.canRetrySubmission=false;state.progressIssue='';persist()
      let receipt
      try{receipt=await client.post('/retrieval-run-tasks',{...body,request_id:pending.request_id},{timeoutMs:15000})}
      catch(error){
        if(state.pendingSubmission!==pending)return
        if(error instanceof ApiError&&[400,401,403,404,409,422].includes(error.status)){
          state.pendingSubmission=null;persist();throw error
        }
        state.progressIssue='提交结果还未确认，已保存原请求编号；正在读取回执，不会自动重复提交。'
        work.go('evaluate');await readProgress();return
      }
      if(state.pendingSubmission!==pending)return
      if(typeof receipt?.run_id!=='string'||!/^[A-Za-z0-9_-]{1,128}$/.test(receipt.run_id)||(receipt.request_id&&receipt.request_id!==pending.request_id)){
        state.progressIssue='提交回执暂时无法核对，正在按原请求编号读取。';work.go('evaluate');await readProgress();return
      }
      pending.run_id=receipt.run_id;persist()
      // Save the receipt before any follow-up read; a failed GET is not a failed submission.
      try{storage.setItem(key,JSON.stringify({...readRetrievalPointers(storage),[type==='BASELINE'?'baseline':'retest']:receipt.run_id}))}catch{}
      if(type==='BASELINE'){state.baseline=null;state.retest=null;state.change=null;state.comparison=null;state.trialResult=null;state.trialFlowId=null}
      work.go('evaluate')
      await readProgress()
      if(type==='RETEST'&&state.retest?.run.run_id===receipt.run_id&&state.change?.target_eval_set_id&&state.evalSet?.retrieval_eval_set_id!==state.change.target_eval_set_id){
        try{
          const target=await client.get(`/retrieval-evalsets/${body.retrieval_eval_set_id}?version=${body.version}`,readOptions)
          if(state.retest?.run.run_id===receipt.run_id)state.evalSet=target
        }catch{state.progressIssue='评测已读取，但题目版本暂未读全。请重新读取；原评测不会再次执行。'}
      }
    }),
    preview:(query)=>action('预览模型查询改写',async()=>{state.preview=await client.post('/retrieval-rewrite-preview',{provider_session_id:work.state.session.provider_session_id,query})}),
    propose:(body)=>action('记录已确认的单变量修改',async()=>{state.change=await client.post('/retrieval-changes',{...body,baseline_run_id:state.baseline.run.run_id});state.preview=null}),
    apply:()=>action(state.change?.change_type==='KNOWLEDGE_UPDATE'?'应用新知识索引':'应用检索配置',async()=>{state.change=await client.post(`/retrieval-changes/${state.change.change_id}/apply`)}),
    compare:()=>action('计算检索前后变化',async()=>{state.comparison=await client.post('/retrieval-comparisons',{baseline_run_id:state.baseline.run.run_id,retest_run_id:state.retest.run.run_id});work.go('compare')}),
    review:(runId,body)=>action('保存回答人工复核',async()=>{await client.post(`/retrieval-runs/${runId}/reviews`,body);
      const view=await client.get('/retrieval-runs/'+runId);if(state.baseline?.run.run_id===runId)state.baseline=view;else state.retest=view;
      work.state.notice='人工复核已保存，原机器证据和已有比较保留。请重新生成比较以采用最新人工结果。'}),
  }
}
