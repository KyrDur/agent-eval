import {test,expect} from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'
import {savedScoreView} from '../fixtures/score-check.js'
const evidence=path.resolve('../output/run-recovery-20261022')
const session={provider_session_id:'session-check',credential_status:'PRESENT',text_connection_status:'READY',configuration:{provider:'openai-compatible',base_url:'https://example.invalid/v1',model:'saved-model',temperature:0,max_tokens:2048,max_calls:100,timeout_seconds:60}}
async function setup(page,{lostResponse=false,missing=false}={}){
 const calls=[],errors=[],view=savedScoreView(),state={disconnected:true,missing,lostResponse,requestId:null}
 page.on('pageerror',error=>errors.push(error.message))
 await page.clock.install()
 await page.addInitScript(()=>{
  if(localStorage.getItem('recovery-fixture-seeded'))return
  localStorage.setItem('recovery-fixture-seeded','1')
  localStorage.setItem('agenteval.workspace.v1',JSON.stringify({step:'evaluate',session:'session-check'}))
  localStorage.setItem('agenteval.retrieval.v1',JSON.stringify({knowledge:'knowledge-check',index:'index-check',evalSet:'evalset-check',session:'session-check'}))
 })
 await page.route('**/api/experiments/**',async route=>{
  const request=route.request(),name=new URL(request.url()).pathname.replace('/api/experiments','')
  if(name==='/workspace')return route.fulfill({json:{isolated:false}})
  if(name.startsWith('/analytics/'))return route.fulfill({json:{excluded:true,contract_version:3}})
  calls.push({name,method:request.method()})
  if(name==='/retrieval-run-tasks'&&request.method()==='POST'){
   state.requestId=request.postDataJSON().request_id
   if(state.lostResponse)return route.abort('connectionreset')
   return route.fulfill({status:202,json:{...view.run,request_id:state.requestId}})
  }
  if(name.startsWith('/retrieval-run-tasks/')){
   expect(name).toBe('/retrieval-run-tasks/'+state.requestId)
   return state.missing?route.fulfill({status:404,json:{detail:'RUN_RECEIPT_NOT_FOUND'}}):route.fulfill({json:{...view.run,request_id:state.requestId}})
  }
  if(name==='/retrieval-runs/run-check')return state.disconnected?route.abort('connectionreset'):route.fulfill({json:{...view,run:{...view.run,request_id:state.requestId}}})
  const known={
   '/retrieval-history':[], '/provider-sessions/session-check':session,
   '/knowledge-datasets/knowledge-check':view.run.controls.knowledge_snapshot,
   '/knowledge-indices/index-check':view.run.controls.index_snapshot,
   '/retrieval-evalsets/evalset-check':view.run.controls.eval_set_snapshot,
   '/retrieval-scoring-profiles':[{profile_id:'saved-profile',name:'保存的评分规则'}],
   '/retrieval-answer-prompt':{prompt:'只根据资料回答。'},
  }
  if(name in known)return route.fulfill({json:known[name]})
  return route.fulfill({status:404,json:{detail:'No fixture for '+name}})
 })
 await page.goto('/')
 await expect(page.getByRole('heading',{name:'这次从哪里开始？',exact:true})).toBeVisible()
 expect(calls).toEqual([])
 await page.getByRole('button',{name:'继续上次实验',exact:true}).click()
 await expect(page.getByRole('button',{name:'开始评测',exact:true})).toBeEnabled()
 return {calls,errors,state}
}
const recovery=page=>page.getByRole('region',{name:'评测连接恢复',exact:true})
const posts=calls=>calls.filter(c=>c.method==='POST')
async function readSaved(page,state){
 state.disconnected=false
 await recovery(page).getByRole('button',{name:'读取这次评测',exact:true}).click()
 await expect(page.getByRole('heading',{name:'订单实付 89 元，寄上海包邮吗？',exact:true})).toBeVisible()
 await expect(recovery(page)).toHaveCount(0)
}
test('accepted submission with failed progress reads retains one task and manual read recovers it',async({page})=>{
 const {calls,errors,state}=await setup(page)
 const history=calls.filter(c=>c.name==='/retrieval-history').length
 await page.getByRole('button',{name:'开始评测',exact:true}).click()
 await expect(recovery(page)).toContainText('评测已提交')
 await expect(recovery(page).getByRole('button')).toBeEnabled()
 await expect(page.getByRole('button',{name:'开始评测',exact:true})).toHaveCount(0)
 expect(posts(calls)).toHaveLength(1)
 expect(calls.filter(c=>c.name==='/retrieval-history')).toHaveLength(history)
 await fs.mkdir(evidence,{recursive:true})
 await page.screenshot({path:path.join(evidence,'accepted-read-failure-desktop.png'),fullPage:true})
 await page.setViewportSize({width:390,height:844})
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false)
 await page.screenshot({path:path.join(evidence,'accepted-read-failure-mobile.png'),fullPage:true})
 await readSaved(page,state)
 expect(posts(calls)).toHaveLength(1);expect(errors).toEqual([])
})
test('lost POST response recovers by exact request ID without repeating the write',async({page})=>{
 const {calls,errors,state}=await setup(page,{lostResponse:true})
 state.disconnected=false
 await page.getByRole('button',{name:'开始评测',exact:true}).click()
 await expect(page.getByRole('heading',{name:'订单实付 89 元，寄上海包邮吗？',exact:true})).toBeVisible()
 expect(posts(calls)).toHaveLength(1)
 expect(calls.some(c=>c.name==='/retrieval-run-tasks/'+state.requestId&&c.method==='GET')).toBe(true)
 expect(errors).toEqual([])
})
test('refresh asks before reading history then restores the original accepted run',async({page})=>{
 const {calls,errors,state}=await setup(page)
 await page.getByRole('button',{name:'开始评测',exact:true}).click()
 await expect(recovery(page).getByRole('button')).toBeEnabled()
 const pending=await page.evaluate(()=>JSON.parse(localStorage.getItem('agenteval.retrieval.v1')))
 expect(pending.pendingRun).toBe('run-check');expect(pending.pendingRequest).toBe(state.requestId)
 const count=calls.length
 await page.reload()
 await expect(page.getByRole('heading',{name:'这次从哪里开始？',exact:true})).toBeVisible()
 expect(calls).toHaveLength(count)
 state.disconnected=false
 await page.getByRole('button',{name:'继续上次实验',exact:true}).click()
 await expect(page.getByRole('heading',{name:'订单实付 89 元，寄上海包邮吗？',exact:true})).toBeVisible()
 expect(posts(calls)).toHaveLength(1);expect(errors).toEqual([])
})
test('missing receipt permits only an explicit retry using the identical request ID',async({page})=>{
 const {calls,errors,state}=await setup(page,{lostResponse:true,missing:true})
 await page.getByRole('button',{name:'开始评测',exact:true}).click()
 await expect(page.getByRole('button',{name:'按原参数重试提交',exact:true})).toBeEnabled()
 expect(posts(calls)).toHaveLength(1)
 const original=state.requestId
 state.lostResponse=false;state.missing=false;state.disconnected=false
 await page.getByRole('button',{name:'按原参数重试提交',exact:true}).click()
 await expect(page.getByRole('heading',{name:'订单实付 89 元，寄上海包邮吗？',exact:true})).toBeVisible()
 expect(state.requestId).toBe(original);expect(posts(calls)).toHaveLength(2);expect(errors).toEqual([])
})
