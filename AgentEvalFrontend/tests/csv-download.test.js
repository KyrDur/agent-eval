import {test} from 'node:test'
import assert from 'node:assert/strict'
import {createApi} from '../src/api.js'

test('CSV download keeps BOM, Chinese filename and full body without a POST',async()=>{
 const bytes=new Uint8Array([239,187,191,...new TextEncoder().encode('问题,回答\r\n"如何退款？","第一行\n第二行"\r\n')])
 const calls=[]
 const api=createApi(async(url,options)=>{calls.push([url,options]);return new Response(bytes,{headers:{'Content-Type':'text/csv; charset=utf-8','Content-Disposition':`attachment; filename*=UTF-8''${encodeURIComponent('评测明细_20261017_a.csv')}`,'X-CSV-Row-Count':'1'}})})
 const result=await api.download('/retrieval-runs/a/export?format=csv')
 assert.equal(result.filename,'评测明细_20261017_a.csv');assert.equal(result.rowCount,'1')
 assert.deepEqual(new Uint8Array(await result.blob.arrayBuffer()),bytes)
 assert.equal(calls[0][1].method,undefined);assert.equal(calls[0][1].body,undefined);assert.equal(calls[0][1].cache,'no-store')
})
test('Failed or invalid downloads do not silently save JSON or empty files and can retry',async()=>{
 let calls=0
 const api=createApi(async()=>{calls++;return calls===1?new Response(JSON.stringify({detail:'CSV_EXPORT_RUN_NOT_FINISHED'}),{status:409,headers:{'Content-Type':'application/json'}}):new Response('a,b\r\n1,2',{headers:{'Content-Type':'text/csv'}})})
 await assert.rejects(api.download('/retrieval-runs/a/export'),e=>e.code==='CSV_EXPORT_RUN_NOT_FINISHED')
 assert.equal((await api.download('/retrieval-runs/a/export')).filename,'evaluation.csv');assert.equal(calls,2)
 for(const response of [new Response('{}',{headers:{'Content-Type':'application/json'}}),new Response('',{headers:{'Content-Type':'text/csv'}})]){
  await assert.rejects(createApi(async()=>response).download('/unused'),e=>e.code==='CSV_DOWNLOAD_FAILED')
 }
})
