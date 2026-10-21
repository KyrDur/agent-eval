import {test,expect} from '@playwright/test'
import path from 'node:path'

const evidenceDir=process.env.AGENTEVAL_TEST_EVIDENCE_DIR
test.use({actionTimeout:12000})
test('calibration blind annotation to fixed-answer final validation and pending report',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message))
  await page.goto('/')
  await expect(page.locator('#landing-title')).toBeVisible()
  if(evidenceDir)await page.screenshot({path:path.join(evidenceDir,'current-homepage.png'),fullPage:true})
  await page.getByRole('button',{name:'使用自己的模型做实验',exact:false}).first().click()
  await expect(page.getByRole('button',{name:'评测校准',exact:false})).toBeVisible()
  const post=async(url,data)=>{const response=await page.request.post('/api/experiments'+url,{data});expect(response.ok(),await response.text()).toBeTruthy();return response.json()}
  const session=await post('/provider-sessions',{provider:'openai-compatible',base_url:`http://127.0.0.1:${process.env.AGENTEVAL_TEST_PROVIDER_PORT||8124}/v1`,
    model:'calibration-browser-fixture',max_tokens:4096,max_calls:100,api_key:'scripted-fixture-only'})
  await post(`/provider-sessions/${session.provider_session_id}/test`,{})
  const questions=['电池超出保修期如何维修？','如何申请开具电子发票？','发货前能不能修改收货地址？']
  const samples=questions.map((question,index)=>({group_id:'fixture-'+index,partition:index===2?'HOLDOUT':'CALIBRATION',question,
    answer:'请提供订单号申请核验。',origin:'CONSTRUCTED',scenario:index===0?'知识缺失':'单事实',
    retrieved_evidence:[{evidence_id:'chunk-'+index,document_id:'policy',text:'请提供订单号申请核验。'}],
    reference_policy:[{evidence_id:'policy',document_id:'policy',text:'请提供订单号申请核验。'}],reference_complete:true,
    provenance:{fixture:'Browser software acceptance only; not real user feedback.'}}))
  const dataset=await post('/calibration/datasets',{name:'浏览器功能验收 · 脚本 fixture',samples,group_review_confirmed:true,
    priority_metric:'演练工作流；不声明质量改善',acceptable_cost:'本地脚本 HTTP；无付费请求'})
  const rubric=await post('/calibration/rubrics',{})
  await page.evaluate(({sid,did,rid})=>{
    localStorage.setItem('agenteval.workspace.v1',JSON.stringify({step:'calibration',session:sid}))
    localStorage.setItem('agenteval.calibration.v1',JSON.stringify({step:3,datasetId:did,rubricId:rid,actor:'Codex-browser-fixture'}))
  },{sid:session.provider_session_id,did:dataset.dataset_id,rid:rubric.rubric_id})
  await page.reload()
  await expect(page.getByRole('heading',{name:'独立标注 · 隐藏机评'})).toBeVisible()
  await page.getByRole('combobox',{name:'记录来源',exact:true}).selectOption('CODEX')
  for(const s of dataset.samples){
    await page.getByRole('combobox',{name:'选择固定样本',exact:true}).selectOption(s.sample_id)
    await page.getByRole('button',{name:'打开盲标样本',exact:true}).click()
    await expect(page.locator('.cal-blind')).toBeVisible()
    await expect(page.locator('.cal-blind')).not.toContainText('scripted local HTTP')
    for(const field of await page.getByLabel('简短理由',{exact:true}).all())await field.fill('Codex 功能验收，非独立人工参照。')
    for(const dimension of ['faithfulness','conditions','relevance','actionability']){
      const form=page.locator(`[data-dimension="${dimension}"]`)
      await form.locator('select').selectOption('2')
      const pickers=form.locator('.cal-fragment-picker')
      await pickers.nth(0).locator('summary').click()
      await pickers.nth(0).locator('.cal-fragment').first().click()
      await pickers.nth(1).locator('summary').click()
      await pickers.nth(1).locator('.cal-fragment').filter({hasText:dimension==='faithfulness'?'当时检索资料':'完整参考政策'}).first().click()
    }
    await page.getByLabel('用户问题是否解决',{exact:true}).selectOption('NO')
    await page.getByLabel('是否忠于可用证据',{exact:true}).selectOption('YES')
    await page.getByLabel('总理由',{exact:true}).fill('Codex 软件验收记录，不计入人工分母。')
    if(evidenceDir&&s===dataset.samples[0]){await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(evidenceDir,'blind-annotation.png'),fullPage:true})
      await page.setViewportSize({width:390,height:844})
      await page.locator('[data-dimension="faithfulness"]').scrollIntoViewIfNeeded()
      await page.screenshot({path:path.join(evidenceDir,'blind-annotation-mobile.png')})
      expect(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+2)).toBe(false)
      await page.setViewportSize({width:1440,height:1000})
    }
    await page.getByRole('button',{name:'提交标注',exact:true}).click()
    await expect(page.locator('.cal-blind')).toHaveCount(0)
  }
  await page.locator('.cal-steps button').filter({hasText:'AI 评分'}).click()
  await page.getByRole('button',{name:'保存评分方法版本',exact:true}).click()
  await page.getByRole('button',{name:'开始给固定回答评分',exact:true}).click()
  await expect(page.getByRole('heading',{name:'分歧与逐项证据'})).toBeVisible()
  await expect(page.locator('.cal-metrics')).toContainText('不可计算')
  await expect(page.locator('.cal-metrics')).toContainText('缺少可用人工参照')
  if(evidenceDir){await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(evidenceDir,'calibration-metrics.png'),fullPage:true});await page.screenshot({path:path.join(evidenceDir,'calibration-workspace.png')})}
  await page.getByRole('button',{name:'查看原文 →',exact:true}).first().click()
  await page.getByRole('button',{name:'建立问题修复记录 →',exact:true}).click()
  await expect(page.getByRole('heading',{name:'问题与修复记录',exact:true})).toBeVisible()
  await page.getByLabel('负责人',{exact:true}).fill('Codex fixture owner')
  await page.getByLabel('观察到的现象',{exact:true}).fill('本地脚本验收问题记录，不代表真实缺陷。')
  for(const label of ['相关证据 · 每行一条','候选原因 · 每行一个','其他解释','下一步怎样区分这些原因','怎样才算本轮修复成功','需要消除的具体错误','潜在退化与可接受范围','验证范围与限制'])await page.getByLabel(label,{exact:true}).fill('本地脚本证据与待验证条件；非真实研究。')
  await page.getByRole('button',{name:'保存问题、假设与验收条件',exact:true}).click()
  await expect(page.locator('.cal-issue')).toHaveCount(1)
  await page.locator('.cal-issue').getByLabel('判断、依据及未解决因素',{exact:true}).fill('本地脚本复现，仅验收流程。')
  await page.locator('.cal-issue').getByRole('button',{name:'追加进展与判断',exact:true}).click()
  await expect(page.locator('.cal-issue-timeline')).toContainText('已复现')
  if(evidenceDir){await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(evidenceDir,'issue-tracking.png'),fullPage:true})}
  await page.locator('.cal-steps button').filter({hasText:'修改与复测'}).click()
  await page.getByRole('button',{name:'保存评分方法版本',exact:true}).click()
  await page.getByRole('button',{name:'开始给固定回答评分',exact:true}).click()
  await expect(page.getByRole('heading',{name:'分歧与逐项证据'})).toBeVisible()
  const history=(await (await page.request.get('/api/experiments/calibration/history')).json())
  const protocols=history.protocols.filter(p=>p.dataset_id===dataset.dataset_id)
  await page.locator('.cal-steps button').filter({hasText:'保留验证'}).click()
  await page.getByRole('combobox',{name:'预先指定基线',exact:true}).selectOption(protocols[0].protocol_id)
  await page.getByRole('combobox',{name:'候选版本',exact:true}).selectOption(protocols[1].protocol_id)
  await page.getByLabel('选定候选的理由与取舍').fill('仅验收最终冻结与解封，不声称质量提升。')
  await page.getByRole('button',{name:'锁定版本、参照与预算',exact:true}).click()
  await page.getByRole('button',{name:'执行最终保留对照并解封结果',exact:true}).click()
  await expect(page.getByText(/验证状态：COMPLETE/)).toBeVisible()
  await page.getByRole('button',{name:'查看验证依据并保存结论 →',exact:true}).click()
  await expect(page.getByRole('heading',{name:'保存采用或不采用的结论'})).toBeVisible()
  await page.getByLabel('理由与证据局限').fill('保留原版。此次仅有 Codex 软件验收，没有真实独立人工标注，研究待完成。')
  await page.getByLabel(/这是本人的采用判断/).check()
  await page.getByRole('button',{name:'保存结论与冻结报告',exact:true}).click()
  await expect(page.getByText('保留原版 · 研究待完成',{exact:true})).toBeVisible()
  if(evidenceDir){await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(evidenceDir,'pending-conclusion.png'),fullPage:true})}
  const downloads=[];page.on('download',d=>downloads.push(d))
  await page.getByRole('button',{name:'导出 Markdown + JSON',exact:true}).click()
  await expect.poll(()=>downloads.length).toBe(2)
  if(evidenceDir){for(const download of downloads)await download.saveAs(path.join(evidenceDir,download.suggestedFilename()))}
  await page.setViewportSize({width:390,height:844})
  await expect(page.getByRole('heading',{name:'保存采用或不采用的结论'})).toBeVisible()
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+2)
  expect(overflow).toBe(false)
  if(evidenceDir)await page.screenshot({path:path.join(evidenceDir,'conclusion-mobile.png'),fullPage:true})
  expect(errors).toEqual([])
})

test('form adjudication preserves two synthetic human-source contract fixtures',async({page})=>{
  // HUMAN here exercises the reference contract only. These are scripted software
  // fixtures, never actual human annotations or evidence of evaluation accuracy.
  const errors=[];page.on('pageerror',e=>errors.push(e.message))
  const post=async(url,data)=>{
    const response=await page.request.post('/api/experiments/calibration'+url,{data})
    expect(response.ok(),await response.text()).toBeTruthy();return response.json()
  }
  const quote='六个月保修，超期可申请付费维修。'
  const dataset=await post('/datasets',{name:'裁决表单软件 fixture · 非真实人工研究',samples:[{
    group_id:'adjudication-fixture',partition:'CALIBRATION',question:'保修期过了如何维修？',answer:quote,
    retrieved_evidence:[{evidence_id:'r',document_id:'p',text:quote}],
    reference_policy:[{evidence_id:'p',document_id:'p',text:quote}],reference_complete:true,origin:'CONSTRUCTED',
    provenance:{fixture:'Scripted contract validation only; HUMAN fields below are synthetic fixtures.'},
  }],group_review_confirmed:true,priority_metric:'测试表单裁决保存',acceptable_cost:'不调用模型'})
  const rubric=await post('/rubrics',{})
  const sample=dataset.samples[0]
  for(const [actor,score] of [['synthetic-contract-a',2],['synthetic-contract-b',0]]){
    const blind=await post('/blind-sessions',{dataset_id:dataset.dataset_id,sample_id:sample.sample_id,rubric_id:rubric.rubric_id,annotator_id:actor})
    await post('/annotations',{dataset_id:dataset.dataset_id,sample_id:sample.sample_id,rubric_id:rubric.rubric_id,annotator_id:actor,
      source:'HUMAN',mode:'BLIND',seen_machine:false,blind_access_id:blind.blind_access_id,
      judgment:{dimensions:Object.fromEntries(['faithfulness','conditions','relevance','actionability'].map(key=>[key,{
        score,answer_quotes:[quote],citations:[{scope:key==='faithfulness'?'RETRIEVED':'REFERENCE',evidence_id:key==='faithfulness'?'r':'p',quote}],
        reason:'Synthetic contract fixture only.',
      }])),critical_errors:[],error_tags:[],verdict:score===2?'PASS':'FAIL',task_resolved:'YES',faithful_to_available:'YES',
      task_failure_reasons:[],insufficient_items:[],reason:'Scripted fixture; not independent human research.'},
    })
  }
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await page.evaluate(({did,rid})=>{
    localStorage.setItem('agenteval.workspace.v1',JSON.stringify({step:'calibration'}))
    localStorage.setItem('agenteval.calibration.v1',JSON.stringify({step:3,datasetId:did,rubricId:rid,actor:'synthetic-contract-a'}))
  },{did:dataset.dataset_id,rid:rubric.rubric_id})
  await page.reload()
  await page.getByRole('button',{name:'查看标注进度与分歧',exact:true}).click()
  await page.getByRole('button',{name:'打开表单裁决',exact:true}).first().click()
  await page.getByLabel('裁决理由',{exact:true}).fill('本地软件 fixture 裁决，只验证原记录保留和表单提交。')
  if(evidenceDir){await page.locator('.cal-adjudication').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(evidenceDir,'adjudication-form.png')})}
  await page.getByRole('button',{name:'保存人工分歧裁决',exact:true}).click()
  await expect(page.locator('.cal-adjudication')).toHaveCount(0)
  const response=await page.request.get(`/api/experiments/calibration/annotations/${dataset.dataset_id}?rubric_id=${rubric.rubric_id}&actor=synthetic-contract-a`)
  const records=await response.json()
  expect(records.annotations).toHaveLength(2)
  expect(records.references[sample.sample_id].state).toBe('ADJUDICATED')
  expect(records.human_agreement.binary_agreement_before_adjudication.value).toBe(0)
  expect(errors).toEqual([])
})
