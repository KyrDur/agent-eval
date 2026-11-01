import {test,expect} from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'
const evidence=path.resolve('../output/experiment-entry-20261022')
const savedWorkspace={step:'setup',session:'entry-saved-session'}
const savedRetrieval={session:'entry-saved-session'}
const session={provider_session_id:'entry-saved-session',credential_status:'UNAVAILABLE',text_connection_status:'UNKNOWN',configuration:{provider:'openai-compatible',base_url:'https://api.deepseek.com',model:'entry-saved-model',temperature:0,max_tokens:1024,max_calls:100,timeout_seconds:60}}
async function setup(page,respond=async()=>null){
 const calls=[],errors=[]
 page.on('pageerror',error=>errors.push(error.message))
 await page.addInitScript(({workspace,retrieval})=>{
  if(!localStorage.getItem('entry-fixture-seeded')){
   localStorage.setItem('agenteval.workspace.v1',JSON.stringify(workspace))
   localStorage.setItem('agenteval.retrieval.v1',JSON.stringify(retrieval))
   localStorage.setItem('entry-fixture-seeded','1')
  }
 },{workspace:savedWorkspace,retrieval:savedRetrieval})
 await page.route('**/api/experiments/**',async route=>{
  const name=new URL(route.request().url()).pathname.replace('/api/experiments','')
  if(name==='/workspace')return route.fulfill({json:{isolated:false}})
  if(name.startsWith('/analytics/'))return route.fulfill({json:{excluded:true,contract_version:3}})
  calls.push(name)
  const custom=await respond(name)
  await route.fulfill(custom||{json:name==='/retrieval-history'?[]:session}).catch(()=>{})
 })
 await page.goto('/')
 await expect(page.getByRole('heading',{name:'这次从哪里开始？',exact:true})).toBeVisible()
 await expect(page.getByRole('button',{name:'开始新实验',exact:true})).toBeEnabled()
 return {calls,errors}
}
const pointers=page=>page.evaluate(()=>({workspace:JSON.parse(localStorage.getItem('agenteval.workspace.v1')),retrieval:JSON.parse(localStorage.getItem('agenteval.retrieval.v1'))}))

test('opening and refreshing with old pointers makes no historical requests',async({page})=>{
 const {calls,errors}=await setup(page)
 await expect.poll(()=>calls.length).toBe(0)
 expect(await pointers(page)).toEqual({workspace:savedWorkspace,retrieval:savedRetrieval})
 await page.reload()
 await expect(page.getByRole('heading',{name:'这次从哪里开始？',exact:true})).toBeVisible()
 expect(calls).toEqual([])
 await fs.mkdir(evidence,{recursive:true})
 await page.screenshot({path:path.join(evidence,'entry-desktop.png'),fullPage:true})
 await page.setViewportSize({width:390,height:844})
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false)
 await page.screenshot({path:path.join(evidence,'entry-mobile.png'),fullPage:true})
 expect(errors).toEqual([])
})
test('new experiment bypasses old reads and leaves saved history on the server untouched',async({page})=>{
 const {calls,errors}=await setup(page)
 await page.getByRole('button',{name:'开始新实验',exact:true}).click()
 await expect(page.getByRole('heading',{name:'连接自己的模型',exact:true})).toBeVisible()
 expect(calls).toEqual([])
 expect((await pointers(page)).retrieval).toEqual({})
 expect(errors).toEqual([])
})
test('last experiment is fetched only after clicking continue',async({page})=>{
 const {calls,errors}=await setup(page)
 expect(calls).toEqual([])
 await page.getByRole('button',{name:'继续上次实验',exact:true}).click()
 await expect(page.getByRole('heading',{name:'连接自己的模型',exact:true})).toBeVisible()
 await expect(page.getByLabel('Model',{exact:true})).toHaveValue('entry-saved-model')
 expect(calls).toContain('/provider-sessions/entry-saved-session')
 expect(calls.some(name=>/ai\/drafts|chat-conversations|calibration|artifacts/.test(name))).toBe(false)
 expect(errors).toEqual([])
})
test('cancel and new experiment remain usable while an old history request is stuck',async({page})=>{
 let release
 const held=new Promise(resolve=>{release=resolve})
 const {calls,errors}=await setup(page,async name=>name==='/retrieval-history'?held:null)
 await page.getByRole('button',{name:'继续上次实验',exact:true}).click()
 await expect(page.getByText('正在读取你选择的实验',{exact:true})).toBeVisible()
 await page.getByRole('button',{name:'取消读取',exact:true}).click()
 await expect(page.getByText('正在读取你选择的实验',{exact:true})).toHaveCount(0)
 expect(await pointers(page)).toEqual({workspace:savedWorkspace,retrieval:savedRetrieval})
 await page.getByRole('button',{name:'开始新实验',exact:true}).click()
 release({json:[]})
 await expect(page.getByRole('heading',{name:'连接自己的模型',exact:true})).toBeVisible()
 await expect(page.getByLabel('Model',{exact:true})).not.toHaveValue('entry-saved-model')
 expect(calls).toEqual(['/retrieval-history'])
 expect(errors).toEqual([])
})
test('expired records return to the choice instead of locking the workspace',async({page})=>{
 const {errors}=await setup(page,async()=>({status:404,json:{detail:'not_found'}}))
 await page.getByRole('button',{name:'继续上次实验',exact:true}).click()
 await expect(page.getByText('记录无法找到',{exact:true})).toBeVisible()
 expect(await pointers(page)).toEqual({workspace:savedWorkspace,retrieval:savedRetrieval})
 await page.getByRole('button',{name:'开始新实验',exact:true}).click()
 await expect(page.getByRole('heading',{name:'连接自己的模型',exact:true})).toBeVisible()
 expect(errors).toEqual([])
})
test('history selection reads a list first and a run only after choosing a row',async({page})=>{
 const {calls,errors}=await setup(page,async name=>name==='/retrieval-history'?{json:[{run_id:'selected-run',name:'手动选择的历史实验',run_type:'BASELINE',status:'COMPLETE',created_at:'2026-10-21T10:00:00Z'}]}:{status:404,json:{detail:'not_found'}})
 await page.getByRole('button',{name:'从历史实验中选择 →',exact:true}).click()
 await expect(page.getByRole('heading',{name:'我的实验记录',exact:true})).toBeVisible()
 expect(calls).toEqual(['/retrieval-history'])
 await page.getByRole('button',{name:/手动选择的历史实验/}).click()
 await expect(page.getByText('记录无法找到',{exact:true})).toBeVisible()
 expect(calls).toContain('/retrieval-runs/selected-run')
 expect(errors).toEqual([])
})
test('twenty-second recovery deadline releases the chooser and permits retry',async({page})=>{
 await page.clock.install()
 let release,stuck=true
 const held=new Promise(resolve=>{release=resolve})
 const {errors}=await setup(page,async name=>stuck&&name==='/retrieval-history'?held:null)
 await page.getByRole('button',{name:'继续上次实验',exact:true}).click()
 await expect(page.getByText('正在读取你选择的实验',{exact:true})).toBeVisible()
 await page.clock.fastForward(21000)
 await expect(page.getByText('读取记录超时',{exact:true})).toBeVisible()
 expect(await pointers(page)).toEqual({workspace:savedWorkspace,retrieval:savedRetrieval})
 stuck=false;release({json:[]})
 await page.getByRole('button',{name:'继续上次实验',exact:true}).click()
 await expect(page.getByRole('heading',{name:'连接自己的模型',exact:true})).toBeVisible()
 expect(errors).toEqual([])
})
