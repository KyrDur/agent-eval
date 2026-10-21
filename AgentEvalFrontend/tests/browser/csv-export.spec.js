import {test,expect} from '@playwright/test'
import fs from 'node:fs/promises'
import path from 'node:path'

const evidence=process.env.AGENTEVAL_TEST_EVIDENCE_DIR
test('CSV downloads include all tested cases, preserve frozen comparisons and retry without evaluation',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('/')
 const post=async(url,data)=>{const r=await page.request.post('/api/experiments'+url,{data});expect(r.ok(),await r.text()).toBeTruthy();return r.json()}
 const session=await post('/provider-sessions',{provider:'openai-compatible',base_url:`http://127.0.0.1:${process.env.AGENTEVAL_TEST_PROVIDER_PORT||8124}/v1`,model:'csv-local-fixture',max_tokens:4096,max_calls:50,api_key:'csv-scripted-fixture-only'})
 await post(`/provider-sessions/${session.provider_session_id}/test`,{})
 const knowledge=await post('/knowledge-datasets',{name:'CSV 功能验收（构造数据）',documents:[{document_id:'opened',text:'拆封商品先核验订单，保持包装完整；定制商品不支持无理由退货。'},{document_id:'invoice',text:'发票需订单号和抬头。'}]})
 const index=await post(`/knowledge-datasets/${knowledge.knowledge_dataset_id}/index`,{version:1,embedding_model:'sha256-lexical-bigram-v1'})
 const cases=[{case_id:'csv-a',query:'拆了还能退吗？',group_id:'return',relevant_document_ids:['opened']},{case_id:'csv-b',query:'发票需要哪些信息？',group_id:'invoice',relevant_document_ids:['invoice']},{case_id:'csv-private',query:'尚未解封的优惠券题，不能导出',group_id:'coupon',partition:'HOLDOUT',relevant_document_ids:['invoice']}].map(c=>({partition:'DEBUG',source:'demo',expected_answer:'参考答案，保留 "引号"。\n第二行。',reference_complete:true,...c}))
 const dataset=await post('/retrieval-evalsets',{name:'CSV 功能验收（构造数据）',index_id:index.index_id,cases,split_reviewed:true})
 const baseline=await post('/retrieval-runs',{provider_session_id:session.provider_session_id,retrieval_eval_set_id:dataset.retrieval_eval_set_id,verify_answers:true,scoring_profile_id:'initial-evidence-v1',retrieval_config:{top_k:1}})
 const change=await post('/retrieval-changes',{baseline_run_id:baseline.run_id,change_type:'TOP_K_CHANGE',after_config:{top_k:2},selected_case_ids:['csv-a'],reason:'CSV 功能验收，扩大返回条数；不作为质量研究。',user_confirmed:true})
 await post(`/retrieval-changes/${change.change_id}/apply`,{})
 const retest=await post('/retrieval-runs',{provider_session_id:session.provider_session_id,retrieval_eval_set_id:dataset.retrieval_eval_set_id,run_type:'RETEST',parent_run_id:baseline.run_id,change_id:change.change_id,verify_answers:true})
 const comparison=await post('/retrieval-comparisons',{baseline_run_id:baseline.run_id,retest_run_id:retest.run_id})
 await page.evaluate(({sid,kid,iid,eid,bid,rid,cid})=>{localStorage.setItem('agenteval.workspace.v1',JSON.stringify({step:'evaluate',session:sid}));localStorage.setItem('agenteval.retrieval.v1',JSON.stringify({knowledge:kid,index:iid,evalSet:eid,baseline:bid,retest:rid,comparison:cid,session:sid}))},{sid:session.provider_session_id,kid:knowledge.knowledge_dataset_id,iid:index.index_id,eid:dataset.retrieval_eval_set_id,bid:baseline.run_id,rid:retest.run_id,cid:comparison.comparison_id})
 await page.reload()
 const button=page.getByRole('button',{name:'导出本次结果 CSV',exact:true});await expect(button).toBeEnabled()
 await expect(page.getByText('包含本次全部题目，不受页面筛选影响',{exact:true})).toBeVisible()
 // Fail one download to verify a plain retry, not another model run.
 const route='**/retrieval-runs/*/export?format=csv'
 await page.route(route,r=>r.fulfill({status:503,contentType:'application/json',body:'{"detail":"CSV_EXPORT_UNAVAILABLE"}'}),{times:1})
 await button.click();await expect(page.getByRole('alert').filter({hasText:'请重新读取这次结果后重试'})).toBeVisible();await expect(button).toBeEnabled()
 async function download(button,filename){const pending=page.waitForEvent('download');await button.click();const file=await pending;expect(file.suggestedFilename()).toMatch(/\.csv$/);const p=await file.path();const data=await fs.readFile(p);expect(data.subarray(0,3)).toEqual(Buffer.from([239,187,191]));const text=data.toString('utf8');expect(text).toContain('csv-a');expect(text).toContain('csv-b');expect(text).not.toContain('csv-private');expect(text).not.toContain('尚未解封');expect(text).not.toContain('csv-scripted-fixture-only');if(evidence)await file.saveAs(path.join(evidence,filename));return text}
 const single=await download(button,'actual-browser-run.csv');expect(single).toContain(retest.run_id);expect(single).toContain('评分明细与引用')
 if(evidence)await page.screenshot({path:path.join(evidence,'csv-run-desktop.png')})
 await page.getByRole('button',{name:/复测比较/}).click()
 const compareButton=page.getByRole('button',{name:'导出前后对比 CSV',exact:true});await expect(compareButton).toBeEnabled()
 const paired=await download(compareButton,'actual-browser-comparison.csv');expect(paired).toContain('修改前·实际回答');expect(paired).toContain('修改后·实际回答');expect(paired).toContain(comparison.comparison_id)
 if(evidence)await page.screenshot({path:path.join(evidence,'csv-comparison-desktop.png')})
 await page.setViewportSize({width:390,height:844});await compareButton.scrollIntoViewIfNeeded();await expect(compareButton).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2)).toBe(false)
 if(evidence)await page.screenshot({path:path.join(evidence,'csv-comparison-mobile.png')})
 for(const run of [baseline,retest]){const reread=await page.request.get('/api/experiments/retrieval-runs/'+run.run_id);expect((await reread.json()).run.provider_call_count).toBe(run.provider_call_count)}
 expect(errors).toEqual([])
})
