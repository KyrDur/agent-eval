import test from 'node:test'
import assert from 'node:assert/strict'
import {createCalibrationWorkspace} from '../src/calibration-workspace.js'
const storage=()=>{const data=new Map();return {getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),data}}
const work=()=>({state:{session:{provider_session_id:'session'}},action:async(_,fn)=>fn(),go:()=>{}})
test('lost run response retries the same request identity without retaining answer or credentials',async()=>{
  const s=storage(),bodies=[];let fail=true
  const client={get:async path=>path==='/calibration/history'?{datasets:[],rubrics:[],protocols:[],runs:[],validations:[],conclusions:[]}: {run:{},results:[]},
    post:async(_,body)=>{bodies.push(body);if(fail){fail=false;throw Error('lost response')}return {run_id:'run',status:'COMPLETE'}}}
  const cal=createCalibrationWorkspace(work(),s,client);cal.state.dataset={dataset_id:'dataset',samples:[{answer:'private answer'}]};cal.state.rubric={rubric_id:'rubric'}
  await assert.rejects(cal.run({protocol_id:'protocol',repetitions:1,budget:2}))
  assert.equal(JSON.stringify([...s.data.values()]).includes('private answer'),false)
  await cal.run({protocol_id:'protocol',repetitions:1,budget:2})
  assert.equal(bodies[0].request_id,bodies[1].request_id)
  assert.equal(cal.state.pendingRun,null)
})
test('annotation submit retains source and exposure and never receives a machine result in its request',async()=>{
  let body
  const client={post:async(_,b)=>{body=b;return {annotation_id:'a'}}}
  const cal=createCalibrationWorkspace(work(),storage(),client)
  cal.state.dataset={dataset_id:'d'};cal.state.rubric={rubric_id:'r'};cal.state.blind={sample_id:'s',blind_access_id:'blind'}
  await cal.annotate({source:'CODEX',seen_machine:true,judgment:{verdict:'PENDING'}})
  assert.equal(body.source,'CODEX');assert.equal(body.seen_machine,true);assert.equal(body.blind_access_id,'blind')
  assert.equal(cal.state.blind,null)
})
test('historical source keeps the actual exposed actor when a different annotator opens it later',()=>{
  const cal=createCalibrationWorkspace(work(),storage(),{})
  cal.state.actor='original-viewer';cal.queue('source-run','case')
  cal.state.actor='new-annotator'
  assert.equal(cal.state.selections[0].source_viewer,'original-viewer')
})
test('annotation progress is scoped to actor and issue events retain concurrency identity without persisting notes',async()=>{
  const requests=[],s=storage()
  const client={get:async path=>{requests.push({path});return []},post:async(path,body)=>{requests.push({path,body});return {event_id:'event'}}}
  const cal=createCalibrationWorkspace(work(),s,client)
  cal.state.dataset={dataset_id:'d'};cal.state.rubric={rubric_id:'r'};cal.state.actor='reviewer b'
  await cal.loadAnnotations()
  assert.ok(requests[0].path.includes('actor=reviewer%20b'))
  await cal.updateIssue('issue',{previous_event_id:'previous',to_status:'REPRODUCED',note:'Private fixture note'})
  assert.equal(requests[1].body.previous_event_id,'previous')
  assert.equal(requests[1].body.actor,'reviewer b')
  assert.equal(JSON.stringify([...s.data.values()]).includes('Private fixture note'),false)
})
