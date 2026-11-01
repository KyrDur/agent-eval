import {test,expect} from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'
import {savedScoreView,savedOperationsRow} from '../fixtures/score-check.js'
const evidence=path.resolve('../output/score-check-20261022')
const session={provider_session_id:'session-check',credential_status:'PRESENT',text_connection_status:'READY',configuration:{provider:'openai-compatible',base_url:'https://example.invalid/v1',model:'saved-model',temperature:0,max_tokens:2048,max_calls:100,timeout_seconds:60}}
async function setup(page,{failure=false,respond}={}){
 const calls=[],errors=[],view=savedScoreView()
 page.on('pageerror',error=>errors.push(error.message))
 await page.addInitScript(({failure})=>{
  localStorage.setItem('agenteval.workspace.v1',JSON.stringify({step:'evaluate',session:'session-check'}))
  localStorage.setItem('agenteval.retrieval.v1',JSON.stringify({baseline:'run-check',session:'session-check'}))
  Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{if(failure)throw new Error('Clipboard disabled');window.__copiedScorePrompt=text}}})
 },{failure})
 await page.route('**/api/experiments/**',async route=>{
  const request=route.request(),name=new URL(request.url()).pathname.replace('/api/experiments',''),url=new URL(request.url())
  if(name==='/workspace')return route.fulfill({json:{isolated:false}})
  if(name.startsWith('/analytics/'))return route.fulfill({json:{excluded:true,contract_version:3}})
  calls.push({name,method:request.method()})
  const custom=await respond?.(name);if(custom)return route.fulfill(custom)
  const known={
   '/retrieval-history':[{run_id:'run-check',name:'软件验收评测',run_type:'BASELINE',status:'COMPLETE',created_at:view.run.created_at}],
   '/provider-sessions/session-check':session,
   '/retrieval-runs/run-check':view,
   '/knowledge-datasets/knowledge-check':view.run.controls.knowledge_snapshot,
   '/knowledge-indices/index-check':view.run.controls.index_snapshot,
   '/retrieval-evalsets/evalset-check':view.run.controls.eval_set_snapshot,
   '/retrieval-scoring-profiles':[{profile_id:'saved-profile',name:'保存的评分规则'}],
   '/retrieval-answer-prompt':{prompt:'只根据资料回答。'},
   '/judge-contract':{version:'fixture'},
   '/retrieval-runs/run-check/scoring-jobs':[],
  }
  if(name in known)return route.fulfill({json:known[name]})
  return route.fulfill({status:404,json:{detail:'Fixture has no route: '+url.pathname}})
 })
 await page.goto('/')
 await expect(page.getByRole('heading',{name:'这次从哪里开始？',exact:true})).toBeVisible()
 return {calls,errors}
}
async function resume(page){
 await page.getByRole('button',{name:'继续上次实验',exact:true}).click()
 await expect(page.getByRole('heading',{name:'订单实付 89 元，寄上海包邮吗？',exact:true})).toBeVisible()
}
const drawer=page=>page.getByRole('dialog',{name:'检查这次评分',exact:true})
const openCheck=async page=>{await page.getByRole('button',{name:'检查这次评分',exact:true}).click();await expect(drawer(page)).toBeVisible()}
const copied=page=>page.evaluate(()=>window.__copiedScorePrompt)

test('optional tools are outside the five workflow steps and make no automatic history reads',async({page})=>{
 const {calls,errors}=await setup(page)
 const nav=page.getByRole('navigation',{name:'主导航',exact:true})
 await expect(nav.getByRole('button')).toHaveCount(5)
 await expect(nav.getByRole('button',{name:'整理项目',exact:true})).toBeVisible()
 await page.getByRole('button',{name:'检查 AI 打分 进阶',exact:true}).click()
 await expect(page.getByRole('heading',{name:'这道题可能判错了',exact:true})).toBeVisible()
 await expect(page.getByRole('heading',{name:'想检查打分是否可靠',exact:true})).toBeVisible()
 await expect(page.getByRole('button',{name:'选择已完成的评测',exact:true})).toBeVisible()
 await expect(page.getByLabel('当前操作人',{exact:true})).toHaveCount(0)
 await expect(page.getByLabel('评测分类（业务域）',{exact:true})).toHaveCount(0)
 expect(calls).toEqual([])
 await fs.mkdir(evidence,{recursive:true})
 await page.screenshot({path:path.join(evidence,'scoring-tools-desktop.png'),fullPage:true})
 await page.setViewportSize({width:390,height:844})
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false)
 await page.screenshot({path:path.join(evidence,'scoring-tools-mobile.png'),fullPage:true})
 expect(errors).toEqual([])
})
test('direct button copies only the selected saved question and opens no grading requests',async({page})=>{
 const {calls,errors}=await setup(page);await resume(page)
 const before=structuredClone(calls)
 await openCheck(page)
 await expect(drawer(page).getByText('原判：不通过',{exact:true})).toBeVisible()
 await drawer(page).getByRole('button',{name:'复制提问给 AI',exact:true}).click()
 await expect(drawer(page).getByRole('status')).toHaveText('已复制，直接粘贴到你常用的 AI 即可。')
 const first=await copied(page)
 expect(first).toContain('订单实付 89 元，寄上海包邮吗？')
 expect(first).toContain('可以，您的订单可以包邮。');expect(first).toContain('ref-1');expect(first).toContain('保存的评分规则')
 expect(first).not.toContain('SVALKA');expect(first).not.toContain('SECRET_MUST_NOT_COPY')
 expect(calls).toEqual(before)
 await page.screenshot({path:path.join(evidence,'score-check-desktop.png'),fullPage:true})
 await drawer(page).getByRole('button',{name:'关闭查看区',exact:true}).click()
 await page.getByRole('button',{name:'第2题，通过',exact:true}).click()
 await openCheck(page)
 await drawer(page).getByRole('button',{name:'复制提问给 AI',exact:true}).click()
 expect(await copied(page)).toContain('300 毫升');expect(await copied(page)).not.toContain('89 元')
 expect(calls.every(c=>c.method==='GET')).toBe(true)
 expect(errors).toEqual([])
})
test('copy failure reveals selected readonly prompt for manual copying and works on mobile',async({page})=>{
 const {calls,errors}=await setup(page,{failure:true});await resume(page)
 await page.setViewportSize({width:390,height:844});await openCheck(page)
 await drawer(page).getByRole('button',{name:'复制提问给 AI',exact:true}).click()
 await expect(drawer(page).getByRole('status')).toHaveText('未能自动复制，请在下方选中提问后复制。')
 const text=drawer(page).getByRole('textbox')
 await expect(text).toBeVisible();await expect(text).toHaveAttribute('readonly','')
 expect(await text.inputValue()).toContain('订单实付 89 元，寄上海包邮吗？')
 await text.focus()
 expect(await text.evaluate(el=>el.selectionEnd-el.selectionStart)).toBe((await text.inputValue()).length)
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1)).toBe(false)
 await drawer(page).screenshot({path:path.join(evidence,'score-check-mobile.png')})
 expect(calls.every(c=>c.method==='GET')).toBe(true);expect(errors).toEqual([])
})
test('current-question shortcut remembers the question already selected without finding another run',async({page})=>{
 const {calls,errors}=await setup(page);await resume(page)
 await page.getByRole('button',{name:'第2题，通过',exact:true}).click()
 await page.getByRole('button',{name:'检查 AI 打分 进阶',exact:true}).click()
 const before=structuredClone(calls)
 await page.getByRole('button',{name:'检查当前这道题',exact:true}).click()
 await expect(page.getByRole('heading',{name:'SVALKA 玻璃杯容量是多少？',exact:true})).toBeVisible()
 await page.getByRole('button',{name:'复制提问给 AI',exact:true}).click()
 expect(await copied(page)).toContain('case-2');expect(await copied(page)).not.toContain('89 元')
 expect(calls).toEqual(before);expect(errors).toEqual([])
})
test('history is an explicit choice and a run is not fetched until selected',async({page})=>{
 const {calls,errors}=await setup(page)
 await page.getByRole('button',{name:'检查 AI 打分 进阶',exact:true}).click()
 expect(calls).toEqual([])
 await page.getByRole('button',{name:'选择已完成的评测',exact:true}).click()
 await expect(page.getByRole('heading',{name:'选择已保存的评测',exact:true})).toBeVisible()
 await expect(page.getByRole('button',{name:'使用这次评测',exact:true})).toBeDisabled()
 expect(calls).toEqual([{name:'/retrieval-history',method:'GET'}])
 await page.getByLabel('选择评测',{exact:true}).selectOption('run-check')
 await page.getByRole('button',{name:'使用这次评测',exact:true}).click()
 await expect(page.getByRole('heading',{name:'订单实付 89 元，寄上海包邮吗？',exact:true})).toBeVisible()
 expect(calls).toEqual([{name:'/retrieval-history',method:'GET'},{name:'/retrieval-runs/run-check',method:'GET'}])
 expect(errors).toEqual([])
})
test('onsite regrading remains optional and merely opening it makes only read calls',async({page})=>{
 const {calls,errors}=await setup(page);await resume(page);await openCheck(page)
 expect(calls.some(c=>c.name==='/judge-contract')).toBe(false)
 await drawer(page).getByRole('button',{name:'在本站重新打分',exact:true}).click()
 await expect(drawer(page).getByRole('region',{name:'单题评分恢复',exact:true})).toBeVisible()
 await expect(drawer(page).getByRole('button',{name:'仅重评这一题',exact:true})).toBeEnabled()
 expect(calls.some(c=>c.name==='/judge-contract')).toBe(true)
 expect(calls.some(c=>c.name==='/retrieval-runs/run-check/scoring-jobs')).toBe(true)
 expect(calls.every(c=>c.method==='GET')).toBe(true);expect(errors).toEqual([])
})
test('manual review stays separate and does not receive an AI-generated decision',async({page})=>{
 const {calls,errors}=await setup(page);await resume(page);await openCheck(page)
 await drawer(page).getByRole('button',{name:'我来复核这题',exact:true}).click()
 const review=page.getByRole('dialog',{name:'人工复核与问题记录',exact:true})
 await expect(review).toBeVisible()
 await review.getByRole('button',{name:'人工复核回答',exact:true}).click()
 await expect(review.getByLabel('回答复核理由',{exact:true})).toHaveValue('')
 await expect(review.getByRole('button',{name:'保存回答复核',exact:true})).toBeDisabled()
 expect(calls.every(c=>c.method==='GET')).toBe(true);expect(errors).toEqual([])
})
test('advanced batch checks preserve the frozen machine verdict and separate the human review',async({page})=>{
 const {job,row}=savedOperationsRow()
 Object.assign(job,{domain_id:'store_qa',created_at:'2026-10-22T01:00:00Z',attempt:1,window:{}})
 Object.assign(job.rule_snapshot,{max_attempts:2,version:1})
 row.evaluation_state='PASS'
 const domain={domain_id:'store_qa',name:'已保存的店铺规则',version:1,business_scope:'软件验收范围'}
 const detail={job,rows:[row],sampling_plans:[],summary:{coverage:{numerator:1,denominator:1},pass_rate:{numerator:1,denominator:1},complete:true,actual_requests:1,known_request_minimum:1,independent_samples:1,human_review_count:1,request_accounting_complete:true,excluded:[],missing_ids:[],duplicate_ids:[]}}
 const {calls,errors}=await setup(page,{respond:async name=>name==='/operations/overview'?{json:{domains:[domain],jobs:[job],batches:[],schedules:[],sampling_plans:[]}}:name==='/operations/jobs/job-check'?{json:detail}:null})
 await page.getByRole('button',{name:'检查 AI 打分 进阶',exact:true}).click()
 expect(calls).toEqual([])
 await page.getByRole('button',{name:'批量重评与定期检查 →',exact:true}).click()
 await expect(page.getByRole('heading',{name:'检查一批已保存的回答',exact:true})).toBeVisible()
 await page.getByRole('button',{name:'2. 评分与人工复核',exact:true}).click()
 await page.getByRole('button',{name:/第 1 次执行/}).click()
 await openCheck(page)
 await expect(drawer(page).getByText('原判：不通过 · 当前人评：通过',{exact:true})).toBeVisible()
 await drawer(page).getByRole('button',{name:'复制提问给 AI',exact:true}).click()
 const prompt=await copied(page)
 expect(prompt).toContain('批次冻结规则');expect(prompt).toContain('批次保存的机器原判');expect(prompt).toContain('人评单独保留')
 await expect(drawer(page).getByRole('button',{name:'在本站重新打分',exact:true})).toHaveCount(0)
 expect(calls.every(c=>c.method==='GET')).toBe(true);expect(errors).toEqual([])
})
