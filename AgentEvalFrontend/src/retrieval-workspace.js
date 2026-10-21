import { reactive } from 'vue'
import { api } from './api.js'
import { analytics } from './analytics.js'
const key = 'agenteval.retrieval.v1'
const fields = ['knowledge','index','evalSet','baseline','retest','change','comparison','session']
export function readRetrievalPointers(storage) {
  try { const p=JSON.parse(storage.getItem(key) || '{}');return Object.fromEntries(fields.filter(k => typeof p[k]==='string' && /^[A-Za-z0-9_-]{1,128}$/.test(p[k])).map(k=>[k,p[k]])) } catch {return {}}
}
export function createRetrievalWorkspace(work, storage = globalThis.localStorage, client = api, {pollMs=1200} = {}) {
  const state=reactive({ knowledge:null,index:null,evalSet:null,baseline:null,retest:null,change:null,comparison:null,preview:null,history:[],preferredChange:null })
  let restoring=false
  let pollTimer=null,pollGeneration=0
  function stopPolling(){clearTimeout(pollTimer);pollGeneration++}
  function pollKnownRun(){
    stopPolling()
    const generation=pollGeneration
    const pending=[state.retest,state.baseline].find(v=>v?.run.status==='RUNNING')
    if(!pending)return
    pollTimer=setTimeout(async()=>{
      try{
        const view=await client.get('/retrieval-runs/'+pending.run.run_id)
        if(generation!==pollGeneration)return
        if(view.run.run_type==='RETEST')state.retest=view;else state.baseline=view
        persist()
        if(view.run.status!=='RUNNING')state.history=await client.get('/retrieval-history')
        if(generation===pollGeneration)pollKnownRun()
      }catch{
        if(generation===pollGeneration)work.state.error={title:'评测进度暂时无法读取',message:'请点击“同步状态”。后台任务继续执行，不要重复开始评测。'}
      }
    },pollMs)
    pollTimer?.unref?.()
  }
  const writePointers=()=>storage.setItem(key,JSON.stringify(Object.fromEntries(Object.entries({knowledge:state.knowledge?.knowledge_dataset_id,
    index:state.index?.index_id,evalSet:state.evalSet?.retrieval_eval_set_id,baseline:state.baseline?.run.run_id,retest:state.retest?.run.run_id,
    change:state.change?.change_id,comparison:state.comparison?.comparison_id,session:work.state.session?.provider_session_id}).filter(([,v])=>v))))
  const persist=()=>{if(!restoring)writePointers()}
  const action=(label,fn)=>work.action(label,async()=>{const r=await fn();persist();return r})
  async function writeKnowledge(body){
    state.knowledge=await client.post('/knowledge-datasets',body)
    Object.assign(state,{index:null,evalSet:null,retest:null,change:null,comparison:null})
    // Keep the saved version recoverable if preparing its index fails next.
    persist()
  }
  async function writeIndex(chunk_config,embedding_model){
    const index=await client.post(`/knowledge-datasets/${state.knowledge.knowledge_dataset_id}/index`,{version:state.knowledge.version,chunk_config,embedding_model})
    if(state.index?.index_id!==index.index_id)state.evalSet=null
    state.index=index
  }
  async function open(id,{persistSelection=true}={}) {
    stopPolling()
    const v=await client.get('/retrieval-runs/'+id)
    state.baseline=v.run.run_type==='BASELINE'?v:await client.get('/retrieval-runs/'+v.run.parent_run_id)
    const other=state.history.filter(r=>r.parent_run_id===state.baseline.run.run_id).sort((a,b)=>a.created_at.localeCompare(b.created_at)).at(-1)
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
  async function restoreState() {
    const p=readRetrievalPointers(storage)
    state.history=await client.get('/retrieval-history')
    if(p.session) work.state.session=await client.get('/provider-sessions/'+p.session)
    if(p.index) state.index=await client.get('/knowledge-indices/'+p.index)
    if(p.knowledge) state.knowledge=await client.get('/knowledge-datasets/'+p.knowledge+(state.index?.knowledge_dataset_id===p.knowledge?`?version=${state.index.knowledge_version}`:''))
    if(p.evalSet) {
      state.evalSet=await client.get('/retrieval-evalsets/'+p.evalSet)
      state.index=await client.get('/knowledge-indices/'+state.evalSet.index_id)
      state.knowledge=await client.get(`/knowledge-datasets/${state.index.knowledge_dataset_id}?version=${state.index.knowledge_version}`)
    }
    const baseline=p.baseline || state.history.filter(r=>r.run_type==='BASELINE' && r.retrieval_eval_set_id===state.evalSet?.retrieval_eval_set_id && r.version===state.evalSet?.version)
      .sort((a,b)=>a.created_at.localeCompare(b.created_at)).at(-1)?.run_id
    if(baseline) await open(p.retest || baseline,{persistSelection:false})
    if(p.change) state.change=await client.get('/retrieval-changes/'+p.change)
    if(p.comparison) state.comparison=await client.get('/retrieval-comparisons/'+p.comparison)
    if(p.knowledge) state.knowledge=await client.get('/knowledge-datasets/'+p.knowledge)
    if(p.index){state.index=await client.get('/knowledge-indices/'+p.index);state.knowledge=await client.get(`/knowledge-datasets/${state.index.knowledge_dataset_id}?version=${state.index.knowledge_version}`)}
    else if(p.knowledge)state.index=null
    if(p.evalSet)state.evalSet=await client.get('/retrieval-evalsets/'+p.evalSet)
    if(p.session) work.state.session=await client.get('/provider-sessions/'+p.session)
    persist()
  }
  async function restore(){stopPolling();restoring=true;try{await restoreState()}finally{restoring=false}persist();pollKnownRun()}
  return {state,action,persist,restore,open,
    dispose:stopPolling,
    reset(){stopPolling();Object.assign(state,{knowledge:null,index:null,evalSet:null,baseline:null,retest:null,change:null,comparison:null,preview:null});persist()},
    saveKnowledge:(body)=>action('保存知识版本',()=>writeKnowledge(body)),
    buildIndex:(chunk_config, embedding_model='all-MiniLM-L6-v2')=>action('建立冻结索引',()=>writeIndex(chunk_config,embedding_model)),
    prepareKnowledge:(body,chunk_config,embedding_model='all-MiniLM-L6-v2')=>analytics.withPreparation(()=>action('保存资料并准备评测',async()=>{
      if(body)await writeKnowledge(body)
      await writeIndex(chunk_config,embedding_model)
    })),
    saveEvalset:(body)=>action('保存检索测试题',async()=>{state.evalSet=await client.post('/retrieval-evalsets',{...body,index_id:state.index.index_id});state.baseline=null;state.retest=null;state.change=null;state.comparison=null;work.go('evaluate')}),
    run:(type,config,verifyAnswers,scoringProfileId=null)=>action(type==='BASELINE'?'运行检索 Baseline':'运行检索 Retest',async()=>{
      const body={provider_session_id:work.state.session.provider_session_id,retrieval_eval_set_id:type==='RETEST'&&state.change.target_eval_set_id?state.change.target_eval_set_id:state.evalSet.retrieval_eval_set_id,
        version:type==='RETEST'&&state.change.target_eval_set_id?1:state.evalSet.version,run_type:type,verify_answers:verifyAnswers}
      if(type==='RETEST')Object.assign(body,{parent_run_id:state.baseline.run.run_id,change_id:state.change.change_id,
        verify_answers:state.baseline.run.verify_answers})
      else {body.retrieval_config=config;if(verifyAnswers&&scoringProfileId)body.scoring_profile_id=scoringProfileId}
      const fingerprint=JSON.stringify(body)
      if(!state.runRequest||state.runRequest.fingerprint!==fingerprint)state.runRequest={fingerprint,request_id:crypto.randomUUID()}
      const r=await client.post('/retrieval-run-tasks',{...body,request_id:state.runRequest.request_id})
      try{storage.setItem(key,JSON.stringify({...readRetrievalPointers(storage),[type==='BASELINE'?'baseline':'retest']:r.run_id,session:work.state.session.provider_session_id}))}catch{}
      const view=await client.get('/retrieval-runs/'+r.run_id)
      if(type==='BASELINE'){state.baseline=view;state.retest=null;state.change=null;state.comparison=null}else {state.retest=view;if(state.change.target_eval_set_id)state.evalSet=await client.get(`/retrieval-evalsets/${body.retrieval_eval_set_id}?version=${body.version}`)}
      state.runRequest=null;persist();pollKnownRun()
      state.history=await client.get('/retrieval-history');work.go('evaluate')
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
