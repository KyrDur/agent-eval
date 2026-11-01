import test from 'node:test'
import assert from 'node:assert/strict'
import {completeCaseGroups} from '../src/test-case-preparation.js'

test('automatic grouping fills missing IDs and preserves existing provenance and purposes',async()=>{
 const rows=[{case_id:'a',group_id:'original',partition:'DEBUG',template_id:'source'}, {case_id:'b',partition:'HOLDOUT',query:'another question'}]
 const original=structuredClone(rows)
 const result=await completeCaseGroups(rows,{post:async(path,{cases})=>{
  assert.equal(path,'/retrieval-case-groups');assert.deepEqual(cases,rows)
  return {cases:[{case_id:'a',group_id:'suggested-a'},{case_id:'b',group_id:'suggested-b'}],conflicts:[]}
 }})
 assert.deepEqual(result,[rows[0],{...rows[1],group_id:'suggested-b'}])
 assert.deepEqual(rows,original)
 assert.equal(result[0].template_id,'source')
})
test('existing IDs require no request and grouping never silently changes conflicting purposes',async()=>{
 const existing=[{case_id:'a',group_id:'saved',partition:'DEBUG'}]
 assert.equal(await completeCaseGroups(existing,{post:()=>assert.fail('no request needed')}),existing)
 const rows=[{case_id:'a',partition:'DEBUG'},{case_id:'b',partition:'HOLDOUT'}]
 const original=structuredClone(rows)
 await assert.rejects(()=>completeCaseGroups(rows,{post:async()=>({cases:[],conflicts:['similar']})}),/相似题被分到了两种用途/)
 assert.deepEqual(rows,original)
})
test('an incomplete grouping response is not saved as a successful preparation',async()=>{
 await assert.rejects(()=>completeCaseGroups([{case_id:'a'}],{post:async()=>({cases:[],conflicts:[]})}),/未能整理题目记录/)
})
