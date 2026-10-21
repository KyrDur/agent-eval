import { reactive } from 'vue'
import { api } from './api.js'

const key='agenteval.calibration.v1'
export function createCalibrationWorkspace(work,storage=globalThis.localStorage,client=api){
  const state=reactive({step:1,history:{datasets:[],rubrics:[],protocols:[],runs:[],validations:[],conclusions:[]},
    dataset:null,rubric:null,protocol:null,run:null,comparison:null,validation:null,conclusion:null,
    blind:null,annotationRecords:null,selections:[],actor:'workspace-user',pendingRun:null,issues:[],issueDraft:null})
  function persist(){storage.setItem(key,JSON.stringify({step:state.step,datasetId:state.dataset?.dataset_id,
    rubricId:state.rubric?.rubric_id,actor:state.actor,pendingRun:state.pendingRun}))}
  async function refresh(){state.history=await client.get('/calibration/history')}
  async function restore(){
    await refresh();let saved={};try{saved=JSON.parse(storage.getItem(key)||'{}')}catch{/* Empty workspace. */}
    state.step=Number.isInteger(saved.step)&&saved.step>=1&&saved.step<=9?saved.step:1
    state.actor=typeof saved.actor==='string'&&saved.actor.length<=100?saved.actor:'workspace-user'
    if(saved.datasetId)state.dataset=await client.get('/calibration/datasets/'+saved.datasetId)
    state.rubric=state.history.rubrics.find(r=>r.rubric_id===saved.rubricId)||null
    state.pendingRun=saved.pendingRun||null
    state.validation=state.history.validations.find(v=>v.dataset_id===state.dataset?.dataset_id)||null
  }
  function go(step){state.step=step;state.blind=null;persist()}
  async function act(label,fn){return work.action(label,async()=>{const value=await fn();persist();return value})}
  async function openDataset(id){
    state.dataset=await client.get('/calibration/datasets/'+id)
    state.run=null;state.comparison=null;state.blind=null;state.annotationRecords=null;state.protocol=null;state.conclusion=null;state.issues=[];state.issueDraft=null
    state.validation=state.history.validations.find(v=>v.dataset_id===id)||null
    persist()
  }
  async function loadAnnotations(){
    state.annotationRecords=await client.get(`/calibration/annotations/${state.dataset.dataset_id}?rubric_id=${state.rubric.rubric_id}&actor=${encodeURIComponent(state.actor)}`)
  }
  async function loadIssues(){state.issues=await client.get(`/calibration/issues?dataset_id=${state.dataset.dataset_id}&actor=${encodeURIComponent(state.actor)}`)}
  async function loadRun(id){state.run=await client.get(`/calibration/runs/${id}?actor=${encodeURIComponent(state.actor)}`)}
  return {state,persist,restore,refresh,go,act,loadAnnotations,loadIssues,openDataset,loadRun,
    queue(runId,caseId){
      if(!state.selections.some(s=>s.run_id===runId&&s.case_id===caseId))state.selections.push({run_id:runId,case_id:caseId,
        group_id:'question-'+caseId,partition:'CALIBRATION',origin:'UNKNOWN',scenario:'',diagnostic:false,source_viewer:state.actor})
      go(1);work.go('calibration');work.state.notice='已加入待冻结选择。请确认来源、同源分组和用途后建立样本集。历史机评曝光会保留。'
    },
    createDataset:body=>act('冻结问题、回答与双层证据',async()=>{
      state.dataset=await client.post('/calibration/datasets',body);state.selections=[];state.run=null;state.validation=null;state.comparison=null
      await refresh();go(2)
    }),
    saveRubric:body=>act('保存新的评分细则版本',async()=>{
      state.rubric=await client.post('/calibration/rubrics',body);state.blind=null;state.protocol=null;await refresh()
    }),
    openBlind:sampleId=>act('打开隐藏机评的标注页',async()=>{
      state.blind=await client.post('/calibration/blind-sessions',{dataset_id:state.dataset.dataset_id,sample_id:sampleId,
        rubric_id:state.rubric.rubric_id,annotator_id:state.actor});return state.blind
    }),
    annotate:body=>act('保存标注及曝光记录',async()=>{
      const result=await client.post('/calibration/annotations',{dataset_id:state.dataset.dataset_id,
        sample_id:state.blind.sample_id,rubric_id:state.rubric.rubric_id,annotator_id:state.actor,
        mode:'BLIND',blind_access_id:state.blind.blind_access_id,...body});state.blind=null;return result
    }),
    importAnnotations:rows=>act('导入独立标注',async()=>{
      const result=await client.post('/calibration/annotation-imports',{annotations:rows});await loadAnnotations();return result
    }),
    adjudicate:body=>act('保存分歧裁决',async()=>{await client.post('/calibration/adjudications',body);await loadAnnotations()}),
    createProtocol:body=>act('保存 AI 评分方法',async()=>{
      state.protocol=await client.post('/calibration/protocols',{dataset_id:state.dataset.dataset_id,
        rubric_id:state.rubric.rubric_id,provider_session_id:work.state.session.provider_session_id,...body});await refresh();return state.protocol
    }),
    run:body=>act('仅重评固定回答',async()=>{
      const request={dataset_id:state.dataset.dataset_id,rubric_id:state.rubric.rubric_id,
        provider_session_id:work.state.session.provider_session_id,...body}
      const fingerprint=JSON.stringify(request)
      if(!state.pendingRun||state.pendingRun.fingerprint!==fingerprint){state.pendingRun={fingerprint,request_id:crypto.randomUUID()};persist()}
      const result=await client.post('/calibration/runs',{...request,request_id:state.pendingRun.request_id})
      if(result.status!=='RUNNING')state.pendingRun=null
      await refresh();await loadRun(result.run_id);return result
    }),
    compare:(baselineId,candidateId)=>act('冻结协议对照与人工参照',async()=>{
      state.comparison=await client.post('/calibration/comparisons',{baseline_run_id:baselineId,candidate_run_id:candidateId,actor:state.actor})
      return state.comparison
    }),
    lock:body=>act('锁定候选和最终验证预算',async()=>{
      state.validation=await client.post('/calibration/validations/lock',{dataset_id:state.dataset.dataset_id,
        rubric_id:state.rubric.rubric_id,actor:state.actor,...body});await refresh();return state.validation
    }),
    validate:(baselineSessionId,candidateSessionId)=>act('执行保留对照并记录解封',async()=>{
      state.validation=await client.post(`/calibration/validations/${state.validation.validation_id}/execute`,{
        baseline_session_id:baselineSessionId,candidate_session_id:candidateSessionId,actor:state.actor})
      await refresh()
      if(state.validation.comparison_id)state.comparison=await client.get(`/calibration/comparisons/${state.validation.comparison_id}?actor=${encodeURIComponent(state.actor)}`)
      return state.validation
    }),
    conclude:body=>act('保存校准决策与报告',async()=>{
      state.conclusion=await client.post('/calibration/conclusions',{comparison_id:state.comparison.comparison_id,
        actor:state.actor,validation_id:state.validation?.comparison_id===state.comparison.comparison_id?state.validation.validation_id:null,...body})
      await refresh();return state.conclusion
    }),
    export:async id=>client.get(`/calibration/conclusions/${id}/export?actor=${encodeURIComponent(state.actor)}`),
    createIssue:body=>act('建立问题修复记录',async()=>{
      const result=await client.post('/calibration/issues',{dataset_id:state.dataset.dataset_id,actor:state.actor,...body})
      state.issueDraft=null;await loadIssues();return result
    }),
    updateIssue:(id,body)=>act('追加修复进展与证据',async()=>{
      const result=await client.post(`/calibration/issues/${id}/events`,{actor:state.actor,...body})
      await loadIssues();return result
    }),
  }
}
