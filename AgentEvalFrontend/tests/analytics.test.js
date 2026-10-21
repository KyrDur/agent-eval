import test from 'node:test'
import assert from 'node:assert/strict'
import {createAnalytics} from '../src/analytics.js'
import {webcrypto} from 'node:crypto'
const storage=()=>{const values=new Map();return {getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)}}
test('fixed page tracking strips referrer query; unknown events never transmit',async()=>{
  const requests=[]
  const a=createAnalytics({storage:storage(),sessionStorage:storage(),crypto:webcrypto,referrer:'https://example.com/path?key=secret',fetcher:async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>({excluded:false})}}})
  await a.start('welcome');await a.event('chat');await a.event('page_view','private title');await a.event('export_copy','career')
  const events=requests.filter(r=>r.options.method==='POST').map(r=>JSON.parse(r.options.body))
  assert.equal(events.length,2);assert.equal(events[0].referrer,'https://example.com')
  assert.equal(events[0].session,events[1].session);assert.notEqual(events[0].event_id,events[1].event_id)
  assert.ok(!JSON.stringify(events).includes('secret'))
})
test('DNT and transport failures do not block the product',async()=>{
  let calls=0;const a=createAnalytics({storage:storage(),sessionStorage:storage(),crypto:webcrypto,doNotTrack:true,fetcher:async()=>{calls++;throw Error('offline')}})
  await a.start();await a.event('export_copy');assert.equal(calls,1)
  const b=createAnalytics({storage:storage(),sessionStorage:storage(),crypto:webcrypto,fetcher:async()=>{throw Error('offline')}})
  await b.start();await b.event('export_copy')
})
test('visit rolls over after inactivity and exclusion is stored only after server acceptance',async()=>{
  let clock=1000000;let fail=false;const requests=[],local=storage();const a=createAnalytics({storage:local,sessionStorage:storage(),crypto:webcrypto,now:()=>clock,fetcher:async(url,options)=>{requests.push({url,options});return {ok:!fail,json:async()=>({excluded:false})}}})
  await a.start();clock+=31*60*1000;await a.event('export_copy','career')
  const events=requests.filter(r=>r.url.endsWith('/events')).map(r=>JSON.parse(r.options.body));assert.notEqual(events[0].session,events[1].session)
  await a.preference(true);assert.equal(local.getItem('agenteval.analytics.excluded'),'1')
  fail=true;await assert.rejects(a.preference(false));assert.equal(local.getItem('agenteval.analytics.excluded'),'1')
})
import {operationFor} from '../src/analytics-operations.js'
import {contract} from '../src/analytics-contract.js'
test('operation metadata never contains payload content; transport loss is unknown, not success',async()=>{
 const requests=[];const a=createAnalytics({storage:storage(),sessionStorage:storage(),crypto:webcrypto,fetcher:async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>({excluded:false})}}})
 await a.start('chat');a.activate({action:'chat.send',placement:'ChatPage.control_10',core:true})
 const specification=operationFor('/chat-turns',{message:'PRIVATE MESSAGE',api_key:'PRIVATE KEY'})
 const op=a.begin(specification);a.end(op,true);await a.flush()
 const rows=requests.filter(r=>r.url.endsWith('/interactions')).flatMap(r=>JSON.parse(r.options.body).events)
 assert.equal(rows.filter(r=>r.stage==='interaction').length,1);assert.equal(rows.find(r=>r.stage==='interaction').operation,op.operation)
 assert.ok(rows.some(r=>r.stage==='submitted'));assert.ok(rows.some(r=>r.stage==='transport_error'));assert.ok(!rows.some(r=>r.stage==='result'))
 assert.ok(!JSON.stringify({specification,rows}).includes('PRIVATE'))
 const retry=a.begin(specification);assert.equal(retry.headers['X-AE-Retry'],op.operation);await a.flush()
})
test('exposure and first-edit dedup reset on page entry; page and paths are fixed',async()=>{
 const batches=[];const a=createAnalytics({storage:storage(),sessionStorage:storage(),crypto:webcrypto,fetcher:async(url,options)=>{if(url.endsWith('/interactions'))batches.push(...JSON.parse(options.body).events);return {ok:true,json:async()=>({excluded:false})}}})
 await a.start('knowledge');const meta={action:'knowledge.save',placement:'KnowledgePage.control_08'}
 a.onceRecord('exposure',meta);a.onceRecord('exposure',meta);a.setPath('PRIVATE PATH');a.page('chat');a.page('knowledge');a.onceRecord('exposure',meta);await a.flush()
 const rows=batches.filter(r=>r.stage==='exposure');assert.equal(rows.length,2);assert.notEqual(rows[0].page_visit,rows[1].page_visit);assert.equal(rows[1].path,'RETRIEVAL')
})
test('client stage whitelist rejects outcomes and unrestricted labels',async()=>{
 let events=[];const a=createAnalytics({storage:storage(),sessionStorage:storage(),crypto:webcrypto,fetcher:async(url,options)=>{if(url.endsWith('/interactions'))events.push(...JSON.parse(options.body).events);return {ok:true,json:async()=>({excluded:false})}}})
 await a.start();a.record('result',{action:'chat.send'});a.record('interaction',{action:'PRIVATE ACTION'});await a.flush()
 assert.equal(events.length,1);assert.equal(events[0].stage,'page_enter')
 assert.equal(operationFor('/ai/trace',{comparison_id:'private'}).context,'unknown')
 assert.equal(operationFor('/ai/trace',{}, {context:'comparison'}).context,'comparison')
 assert.equal(operationFor('/retrieval-runs',{run_type:'RETEST'}).action,'run.retest')
 assert.ok(contract.actions.includes('career.regenerate'))
 assert.equal(operationFor('/ai/knowledge',{}, {regenerate:true}).role,'auxiliary')
})
test('busy batching drains newly queued events; normal and leave-page requests respect separate budgets',async()=>{
 const batches=[];let unblock;const gate=new Promise(resolve=>{unblock=resolve});let pause=true
 const a=createAnalytics({storage:storage(),sessionStorage:storage(),crypto:webcrypto,fetcher:async(url,options)=>{
  if(url.endsWith('/interactions')){batches.push({events:JSON.parse(options.body).events,keepalive:options.keepalive});if(pause){pause=false;await gate}}
  return {ok:true,json:async()=>({excluded:false})}
 }})
 await a.start();for(let i=0;i<60;i++)a.activate({action:'site.home',placement:'App.control_01'})
 const first=a.flush();for(let i=0;i<20;i++)a.activate({action:'site.home',placement:'App.control_01'})
 const joined=a.flush();unblock();await joined;await first
 assert.equal(batches.flatMap(b=>b.events).length,81);assert.ok(batches.every(b=>!b.keepalive&&b.events.length<=32))
 batches.length=0;for(let i=0;i<20;i++)a.activate({action:'site.home',placement:'App.control_01'});await a.flush({keepalive:true})
 assert.equal(batches.flatMap(b=>b.events).length,20);assert.ok(batches.every(b=>b.keepalive&&b.events.length<=8))
})
test('v3 teaching categories deduplicate independently; dimensions stay fixed per page entry',async()=>{
 const events=[];let width='compact'
 const a=createAnalytics({layout:()=>width,storage:storage(),sessionStorage:storage(),crypto:webcrypto,fetcher:async(url,options)=>{
  if(url.endsWith('/interactions'))events.push(...JSON.parse(options.body).events)
  return {ok:true,json:async()=>({excluded:false,contract_version:3})}
 }})
 await a.start('evaluate')
 for(const kind of contract.issue_kinds.filter(k=>k!=='unknown')){
  const meta={action:'guide.issue',placement:'JourneyGuide.issue',issue_kind:kind,reveal:'manual'}
  a.onceRecord('exposure',meta);a.onceRecord('exposure',meta)
 }
 width='wide';a.activate({action:'site.home',placement:'App.control_01'});await a.flush()
 assert.equal(events.filter(r=>r.action==='guide.issue').length,6)
 assert.ok(events.every(r=>r.layout==='compact'&&r.ui_variant==='muji_20261012'))
 a.page('welcome');await a.flush();assert.equal(events.at(-1).layout,'wide')
})
test('composite preparation propagates one random flow across save, index and retry only',async()=>{
 const events=[];const a=createAnalytics({storage:storage(),sessionStorage:storage(),crypto:webcrypto,fetcher:async(url,options)=>{
  if(url.endsWith('/interactions'))events.push(...JSON.parse(options.body).events)
  return {ok:true,json:async()=>({excluded:false,contract_version:3})}
 }})
 await a.start('knowledge');let first
 await a.withPreparation(async()=>{
  const save=a.begin({action:'knowledge.save'});const index=a.begin({action:'knowledge.index'})
  first=save.headers['X-AE-Flow'];assert.ok(first);assert.equal(first,index.headers['X-AE-Flow'])
  assert.equal(a.begin({action:'chat.send'}).headers['X-AE-Flow'],'')
  a.end(index,false,true)
 })
 await a.withPreparation(async()=>{const index=a.begin({action:'knowledge.index'});assert.equal(index.headers['X-AE-Flow'],first);a.end(index)})
 await a.withPreparation(async()=>{assert.notEqual(a.begin({action:'knowledge.save'}).headers['X-AE-Flow'],first)})
 await a.flush();assert.ok(!JSON.stringify(events).includes('api_key'))
})
test('disabled or unavailable analytics never posts events, including a remembered test exclusion',async()=>{
 for(const excluded of [false,true]){
  const local=storage();if(excluded)local.setItem('agenteval.analytics.excluded','1')
  const requests=[];const a=createAnalytics({storage:local,sessionStorage:storage(),crypto:webcrypto,fetcher:async(url,options)=>{requests.push(url);return {ok:false,status:404}}})
  await a.start();a.activate({action:'site.home',placement:'App.control_01'});await a.flush()
  assert.equal(a.ready,false);assert.ok(requests.every(url=>url.endsWith('/preference')))
 }
})
test('cached new client falls back to v2 after server rollback without arbitrary fields or labels',async()=>{
 const events=[];const a=createAnalytics({storage:storage(),sessionStorage:storage(),crypto:webcrypto,fetcher:async(url,options)=>{
  if(url.endsWith('/interactions'))events.push(...JSON.parse(options.body).events)
  return {ok:true,json:async()=>({excluded:false})}
 }})
 await a.start();a.activate({action:'welcome.setup',placement:'LandingPage.control_06'});a.onceRecord('exposure',{action:'guide.issue',placement:'JourneyGuide.issue',issue_kind:'retrieval_miss'});await a.flush()
 assert.ok(events.every(r=>!('ui_variant' in r)))
 assert.equal(events.at(-1).placement,'api');assert.ok(!events.some(r=>r.action==='guide.issue'))
})
