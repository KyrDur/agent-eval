import test from 'node:test'
import assert from 'node:assert/strict'
import {trialMatches,trialFinished,trialUsesHistoricalReference,savedTrialComparison} from '../src/plan-trial.js'
import {createRetrievalWorkspace} from '../src/retrieval-workspace.js'
const inputs={baseline_run_id:'base',provider_session_id:'session',change_type:'CONTEXT_STRATEGY_CHANGE',selected_case_ids:['case'],after_config:{top_k:3,context_strategy:'NEIGHBORS'}}
const trial={flow:{flow_id:'trial',stage:'COMPLETE',inputs:{...inputs,execution_mode:'TRIAL'}},view:{run:{run_id:'single',status:'COMPLETE'}}}
const options={view:{run:{run_id:'base'}},caseId:'case',type:'CONTEXT_STRATEGY_CHANGE',afterConfig:{context_strategy:'NEIGHBORS',top_k:3},session:{provider_session_id:'session'}}
test('a matching completed trial enables the next step; changed configuration, case or connection does not',()=>{
 assert.equal(trialMatches(trial,options),true);assert.equal(trialFinished(trial),true)
 for(const change of [{caseId:'other'},{type:'TOP_K_CHANGE'},{afterConfig:{top_k:4,context_strategy:'NEIGHBORS'}},{session:{provider_session_id:'new'}}])assert.equal(trialMatches(trial,{...options,...change}),false)
 assert.equal(trialFinished({...trial,flow:{...trial.flow,stage:'PARTIAL'}}),false)
})
test('prepared index changes retain the actual prepared index and reject another index',()=>{
 const value={...trial,flow:{...trial.flow,index_id:'prepared',inputs:{...trial.flow.inputs,change_type:'CHUNKING_CHANGE'}}}
 assert.equal(trialMatches(value,{...options,type:'CHUNKING_CHANGE',index:{index_id:'prepared'}}),true)
 assert.equal(trialMatches(value,{...options,type:'CHUNKING_CHANGE',index:{index_id:'another'}}),false)
})
test('old programs and changed Judge protocols remain exploratory even after the trial completes',()=>{
 assert.equal(trialFinished(trial),true)
 assert.equal(trialUsesHistoricalReference(trial,{current_implementation_matches:false}),true)
 assert.equal(trialUsesHistoricalReference({...trial,view:{run:{controls:{evaluation_scope:{historical_reference_only:true}}}}},{}),true)
 assert.equal(trialUsesHistoricalReference({...trial,view:{run:{experiment_identity:{comparison_eligible:false}}}},{}),true)
 assert.equal(trialUsesHistoricalReference(trial,{current_implementation_matches:true}),false)
})
test('the changes page reads the saved single question without requiring a batch comparison',()=>{
 const baseline={current_implementation_matches:false,run:{run_id:'base',execution_order:['other','case'],case_results:[{case_id:'other',query:'另一题',results:[]},{case_id:'case',query:'本题的问题',results:[{document_id:'old',text:'旧资料'}]}]},effective_answer_results:[{case_id:'case',turn_evidence:[{response:'原回答'}]}]}
 const saved={...trial,view:{run:{run_id:'single',parent_run_id:'base',status:'COMPLETE',execution_order:['case'],case_results:[{case_id:'case',results:[{document_id:'new',text:'新资料'}]}]},effective_answer_results:[{case_id:'case',turn_evidence:[{response:'新回答'}]}]}}
 assert.deepEqual(savedTrialComparison(saved,baseline),{caseId:'case',question:'本题的问题',total:2,complete:true,historical:true,answerChanged:true,added:1,removed:1})
 assert.equal(savedTrialComparison(saved,{...baseline,run:{...baseline.run,run_id:'another'}}),null)
 assert.equal(savedTrialComparison({...saved,flow:{...saved.flow,inputs:{...saved.flow.inputs,selected_case_ids:['missing']}}},baseline),null)
 assert.equal(savedTrialComparison({...saved,view:{...saved.view,run:{...saved.view.run,execution_order:['other','case']}}},baseline),null)
 assert.equal(savedTrialComparison({...saved,view:{...saved.view,run:{...saved.view.run,parent_run_id:'another'}}},baseline),null)
 const missing={...saved,view:{...saved.view,effective_answer_results:[],run:{...saved.view.run,status:'PARTIAL'}}}
 assert.equal(savedTrialComparison(missing,baseline).answerChanged,null)
 assert.equal(savedTrialComparison(missing,baseline).complete,false)
})
test('trial receipts stay separate from the full retest, and batch execution is an explicit second submission',async()=>{
 const data=new Map(),posts=[],flows=new Map(),storage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)}
 const work={state:{session:{provider_session_id:'session'},step:'improve'},action:async(_,fn)=>fn(),go(step){this.state.step=step}}
 const client={post:async(path,body)=>{posts.push({path,body});const flow={flow_id:body.request_id,inputs:body,stage:'COMPLETE',run_id:body.execution_mode==='TRIAL'?'single':'batch'};flows.set(flow.flow_id,flow);return flow},get:async path=>{
  if(path.startsWith('/retest-flows/'))return flows.get(path.split('/').at(-1))
  if(path==='/retrieval-trial-runs/single')return {run:{run_id:'single',run_type:'RETEST',status:'COMPLETE'}}
  if(path==='/retrieval-runs/batch')return {run:{run_id:'batch',run_type:'RETEST',status:'COMPLETE'}}
  throw new Error(path)
 }}
 const rag=createRetrievalWorkspace(work,storage,client,{autoPoll:false});rag.state.baseline=options.view
 await rag.executeTrial(inputs)
 assert.equal(rag.state.trialResult.view.run.run_id,'single');assert.equal(rag.state.retest,null)
 assert.equal(posts.length,1);assert.equal(posts[0].body.execution_mode,'TRIAL')
 const id=rag.state.trialResult.flow.flow_id
 assert.equal(JSON.parse(data.get('agenteval.retrieval.v1')).trial,id)
 await rag.executePlan({...inputs,trial_flow_id:id})
 assert.equal(posts.length,2);assert.equal(posts[1].body.execution_mode,'FULL')
 assert.equal(rag.state.retest.run.run_id,'batch');assert.equal(rag.state.trialResult.view.run.run_id,'single')
 rag.dispose()
})
