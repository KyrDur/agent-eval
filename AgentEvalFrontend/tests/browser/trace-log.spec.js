import {test,expect} from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'
const evidence=process.env.AGENTEVAL_TEST_EVIDENCE_DIR
async function fixture(page,model='trace-null-score-fixture',config={top_k:1}){
 await page.goto('/');await expect(page.getByRole('button',{name:'使用自己的模型做实验',exact:true})).toBeEnabled()
 const post=async(url,data)=>{const r=await page.request.post('/api/experiments'+url,{data});expect(r.ok(),await r.text()).toBeTruthy();return r.json()}
 const session=await post('/provider-sessions',{provider:'openai-compatible',base_url:`http://127.0.0.1:${process.env.AGENTEVAL_TEST_PROVIDER_PORT||8124}/v1`,model,max_tokens:4096,max_calls:50,api_key:'trace-browser-fixture-only'})
 await post(`/provider-sessions/${session.provider_session_id}/test`,{})
 const knowledge=await post('/knowledge-datasets',{name:'运行日志软件验收',documents:[{document_id:'spec',text:'书桌材质为贴面刨花板，承重30公斤。'},{document_id:'return',text:'定制商品不支持七天无理由退货。'}]})
 const index=await post(`/knowledge-datasets/${knowledge.knowledge_dataset_id}/index`,{version:1,embedding_model:'sha256-lexical-bigram-v1'})
 const dataset=await post('/retrieval-evalsets',{name:'运行日志软件验收',index_id:index.index_id,cases:[{case_id:'trace-spec',query:'书桌是什么材质，承重多少？',reference_complete:true,relevant_document_ids:['spec'],expected_answer:'贴面刨花板，承重30公斤。'},{case_id:'trace-return',query:'定制商品能无理由退货吗？',reference_complete:true,relevant_document_ids:['return'],expected_answer:'不支持七天无理由退货。'}]})
 const baseline=await post('/retrieval-runs',{provider_session_id:session.provider_session_id,retrieval_eval_set_id:dataset.retrieval_eval_set_id,verify_answers:true,scoring_profile_id:'initial-evidence-v1',retrieval_config:config})
 await page.evaluate(({sid,kid,iid,eid,bid})=>{localStorage.setItem('agenteval.workspace.v1',JSON.stringify({step:'evaluate',session:sid}));localStorage.setItem('agenteval.retrieval.v1',JSON.stringify({knowledge:kid,index:iid,evalSet:eid,baseline:bid,session:sid}))},{sid:session.provider_session_id,kid:knowledge.knowledge_dataset_id,iid:index.index_id,eid:dataset.retrieval_eval_set_id,bid:baseline.run_id})
 await page.reload();await page.getByRole('button',{name:'查看运行日志',exact:true}).click()
 return {baseline,logs:page.getByRole('region',{name:'本题运行日志',exact:true})}
}

test('Trace identifies an actual schema error, shows saved inputs and candidates, and exports without a new model request',async({page})=>{
 const errors=[],posts=[];page.on('pageerror',e=>errors.push(e.message))
 const {baseline,logs}=await fixture(page)
 page.on('request',r=>{if(r.method()==='POST'&&/retrieval-runs|\/ai\/|provider-sessions/.test(r.url()))posts.push(r.url())})
 const stages=logs.getByRole('navigation',{name:'日志步骤'}),output=logs.getByRole('region',{name:'模型输出',exact:true})
 await expect(stages.getByRole('button',{name:'评测回答',exact:true})).toHaveAttribute('aria-pressed','true')
 await expect(logs.getByText('请求已返回',{exact:true})).toBeVisible()
 await expect(output.getByText('dimensions.actionability.score',{exact:true})).toBeVisible()
 await expect(output.getByText(/“下一步可用性”返回了 null/)).toBeVisible()
 await expect(logs.getByText('JUDGMENT_SCHEMA_INVALID',{exact:true})).toBeVisible()
 await logs.getByRole('group',{name:'调用内容'}).getByRole('button',{name:'输入',exact:true}).click()
 const input=logs.getByRole('region',{name:'模型输入',exact:true})
 await expect(input.getByText(baseline.case_results[0].query,{exact:true})).toBeVisible()
 await expect(input.getByText('Agent 查到的资料 · 1 段',{exact:true})).toBeVisible()
 await input.getByText('系统提示词',{exact:true}).click()
 await expect(input.locator('pre').filter({visible:true})).toContainText('AGENT_EVAL_LANGSMITH_JUDGE_V1')
 await stages.getByRole('button',{name:'检索候选',exact:true}).click()
 await expect(logs.locator('.trace-candidates>li')).toHaveCount(1)
 await logs.getByRole('group',{name:'检索资料范围'}).getByRole('button',{name:'全部检索候选',exact:true}).click()
 await expect(logs.locator('.trace-candidates>li')).toHaveCount(2)
 await expect(logs.getByText(/检索相似度/).first()).toBeVisible()
 const pending=page.waitForEvent('download');await logs.getByRole('button',{name:'下载日志 JSON',exact:true}).click();const file=await pending
 const exported=JSON.parse(await fs.readFile(await file.path(),'utf8'))
 expect(exported.model_calls).toHaveLength(2)
 expect(JSON.parse(exported.model_calls[1].model_outputs.content[0].text).dimensions.actionability.score).toBeNull()
 expect(JSON.stringify(exported)).not.toContain('trace-browser-fixture-only')
 if(evidence)await file.saveAs(path.join(evidence,'trace-saved-log.json'))
 await page.setViewportSize({width:390,height:844})
 await stages.getByRole('button',{name:'评测回答',exact:true}).click()
 await expect(logs.getByText('dimensions.actionability.score',{exact:true})).toBeVisible()
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2)).toBe(false)
 if(evidence)await logs.screenshot({path:path.join(evidence,'trace-log-mobile.png')})
 await page.getByRole('navigation',{name:'题目导航',exact:true}).getByRole('button',{name:'第二题',exact:true}).click()
 await expect(logs.getByText('dimensions.actionability.score',{exact:true})).toBeVisible()
 const saved=await (await page.request.get('/api/experiments/retrieval-runs/'+baseline.run_id)).json()
 expect(saved.run.answer_results).toEqual(baseline.answer_results)
 expect(saved.run.provider_call_count).toBe(baseline.provider_call_count)
 expect(posts).toEqual([]);expect(errors).toEqual([])
})

test('Failed rewrite and downstream not-run stages stay distinct in the trace',async({page})=>{
 const {logs}=await fixture(page,'rag-rewrite-failed',{top_k:1,query_rewrite:true,rerank:true})
 const stages=logs.getByRole('navigation',{name:'日志步骤'})
 await expect(stages.getByRole('button',{name:'查询改写',exact:true})).toHaveAttribute('aria-pressed','true')
 await expect(logs.getByText('请求失败',{exact:true})).toBeVisible()
 await expect(logs.getByText('请求失败，没有返回正文。',{exact:true})).toBeVisible()
 await stages.getByRole('button',{name:'重排候选',exact:true}).click()
 await expect(logs.getByText('本步骤没有执行，可查看前面失败的步骤。',{exact:true})).toBeVisible()
 await expect(logs.getByRole('region',{name:'模型调用详情'})).toHaveCount(0)
})
