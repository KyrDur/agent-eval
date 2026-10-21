import {test,expect} from '@playwright/test'
import path from 'node:path'
import {demoDocuments,demoCases} from '../../src/rag-demo.js'

test('Accepted evaluation survives reload and polls one original run without another POST',async({page})=>{
 const posts=[],errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/retrieval-run-tasks'))posts.push(r.postDataJSON())})
 await page.goto('/')
 await expect(page.getByRole('button',{name:'使用自己的模型做实验',exact:true})).toBeEnabled()
 const post=async(url,data)=>{const r=await page.request.post('/api/experiments'+url,{data});expect(r.ok(),await r.text()).toBeTruthy();return r.json()}
 const session=await post('/provider-sessions',{provider:'openai-compatible',base_url:`http://127.0.0.1:${process.env.AGENTEVAL_TEST_PROVIDER_PORT||8124}/v1`,model:'background-slow-fixture',api_key:'background-software-fixture-only',max_tokens:4096,max_calls:50})
 await post(`/provider-sessions/${session.provider_session_id}/test`,{})
 const knowledge=await post('/knowledge-datasets',{name:'Background run software acceptance',documents:demoDocuments})
 const index=await post(`/knowledge-datasets/${knowledge.knowledge_dataset_id}/index`,{version:1,embedding_model:'sha256-lexical-bigram-v1'})
 const dataset=await post('/retrieval-evalsets',{index_id:index.index_id,name:'Background evaluation',cases:demoCases})
 await page.evaluate(({sid,kid,iid,eid})=>{localStorage.setItem('agenteval.workspace.v1',JSON.stringify({step:'evaluate',session:sid}));localStorage.setItem('agenteval.retrieval.v1',JSON.stringify({knowledge:kid,index:iid,evalSet:eid,session:sid}))},{sid:session.provider_session_id,kid:knowledge.knowledge_dataset_id,iid:index.index_id,eid:dataset.retrieval_eval_set_id})
 await page.reload()
 const response=page.waitForResponse(r=>r.url().endsWith('/retrieval-run-tasks')&&r.request().method()==='POST')
 await page.locator('[data-analytics-action="run.baseline"]').click()
 const accepted=await response;expect(accepted.status()).toBe(202)
 const original=await accepted.json();expect(original.status).toBe('RUNNING')
 await expect(page.getByRole('heading',{name:'首次评测 · 运行中',exact:true})).toBeVisible()
 await expect(page.getByText(/后台正在继续评测/)).toBeVisible()
 await page.reload()
 await expect(page.getByRole('heading',{name:'首次评测 · 已完成',exact:true})).toBeVisible({timeout:30000})
 const ids=await page.evaluate(()=>JSON.parse(localStorage.getItem('agenteval.retrieval.v1')))
 expect(ids.baseline).toBe(original.run_id);expect(posts).toHaveLength(1)
 const saved=await (await page.request.get('/api/experiments/retrieval-runs/'+original.run_id)).json()
 expect(saved.run.provider_call_count).toBe(16);expect(saved.run.answer_results).toHaveLength(8)
 if(process.env.AGENTEVAL_TEST_EVIDENCE_DIR)await page.screenshot({path:path.join(process.env.AGENTEVAL_TEST_EVIDENCE_DIR,'background-run-completed.png'),fullPage:true})
 expect(errors).toEqual([])
})
