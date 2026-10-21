import {contract} from './analytics-contract.js'
const pages = new Set(['welcome','setup','knowledge','chat','define','evaluate','improve','compare','career','history','calibration','learning'])
const clientEvents = new Set(['page_view','export_download','export_copy'])
const stages=new Set(['page_enter','available','interaction','exposure','unavailable','edit_start','validation_blocked','submitted','transport_error','client_wait','material_view','copy_success','download_trigger'])
export function createAnalytics({fetcher=globalThis.fetch,storage=globalThis.localStorage,
  sessionStorage=globalThis.localStorage,crypto=globalThis.crypto,umami=()=>globalThis.umami,
  now=()=>Date.now(),referrer='',doNotTrack=false,layout=()=>{
    const width=globalThis.innerWidth
    return typeof width==='number'?(width<=600?'compact':width<1024?'medium':'wide'):'unknown'
  }}={}) {
  let ready=false,currentPage='welcome',excluded=false,session='',touched=0,visit='',path='RETRIEVAL',entry='direct',timer
  let queue=[],inFlight=null
  const pending=new Map(),failures=new Map(),once=new Set()
  const preparations=new Map()
  let currentLayout='unknown',preparationFlow='',serverContractVersion=2
  const uuid=()=>crypto?.randomUUID?.() || ''
  function visitSession(){
    try {const saved=JSON.parse(sessionStorage.getItem('agenteval.analytics.session')||'null')
      if(saved && /^[A-Za-z0-9-]{1,64}$/.test(saved.id) && typeof saved.touched==='number' && now()-saved.touched<1800000){session=saved.id;touched=saved.touched}}
    catch{}
    if(!session || now()-touched>=1800000)session=uuid()
    touched=now();try{sessionStorage.setItem('agenteval.analytics.session',JSON.stringify({id:session,touched}))}catch{}
    return session
  }
  function safeReferrer(){try{const u=new URL(referrer);return ['http:','https:'].includes(u.protocol)?u.origin:''}catch{return ''}}
  async function send(name,page=currentPage){
    if(!ready || doNotTrack || !clientEvents.has(name) || !pages.has(page))return
    try{await fetcher('/api/experiments/analytics/events',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},keepalive:true,
      body:JSON.stringify({name,page,session:visitSession(),event_id:uuid(),referrer:safeReferrer()})})}catch{}
    if(!excluded)try{const tracker=umami();if(name==='page_view')await tracker?.track(props=>({...props,url:'/'+page,title:'Agent Eval · '+page,referrer:safeReferrer()}));else await tracker?.track(name)}catch{}
  }
  function fixed(value,values,fallback){return values.includes(value)?value:fallback}
  function record(stage,meta={},extra={}){
    if(!ready || doNotTrack || !stages.has(stage) || !contract.actions.includes(meta.action))return false
    if(serverContractVersion<3 && ['welcome.content','guide.issue','welcome.menu','welcome.section','welcome.evidence'].includes(meta.action))return false
    const row={stage,action:meta.action,page:pages.has(meta.page)?meta.page:currentPage,page_visit:meta.page_visit||visit,session:visitSession(),event_id:uuid(),
      placement:fixed(meta.placement,contract.placements,'api'),path,entry,
      material:fixed(meta.material,contract.materials,'unknown'),role:fixed(meta.role,contract.roles,'unknown'),
      context:fixed(meta.context,contract.contexts,'unknown'),reason:fixed(extra.reason,contract.reasons,'none'),
      state:fixed(extra.state,['none','expand','collapse','select','deselect','change'],'none'),
      operation:/^[A-Za-z0-9-]{1,64}$/.test(extra.operation||'')?extra.operation:'',
      retry_of:/^[A-Za-z0-9-]{1,64}$/.test(extra.retry_of||'')?extra.retry_of:'',duration_ms:Math.max(0,Math.min(3600000,Math.round(extra.duration_ms||0))),
      ui_variant:'muji_20261012',layout:fixed(meta.layout||currentLayout,contract.layouts,'unknown'),
      content:fixed(meta.content,contract.contents,'unknown'),example_kind:fixed(meta.example_kind,contract.example_kinds,'unknown'),
      issue_kind:fixed(meta.issue_kind,contract.issue_kinds,'unknown'),reveal:fixed(meta.reveal,contract.reveals,'unknown'),
      preparation_flow:/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(extra.preparation_flow||meta.preparation_flow||'')?(extra.preparation_flow||meta.preparation_flow):''}
    if(serverContractVersion<3){
      for(const key of ['ui_variant','layout','content','example_kind','issue_kind','reveal','preparation_flow'])delete row[key]
      if(row.placement.startsWith('LandingPage.') || row.placement==='JourneyGuide.issue')row.placement='api'
    }
    if(queue.length>=2048)return false
    queue.push(row)
    if(!timer)timer=setTimeout(()=>{timer=null;void flush()},150)
    return true
  }
  function flush({keepalive=false}={}){
    if(inFlight)return inFlight
    if(!queue.length)return Promise.resolve()
    clearTimeout(timer);timer=null
    inFlight=(async()=>{
      try{while(queue.length){const batch=queue.splice(0,keepalive?8:32)
        try{const r=await fetcher('/api/experiments/analytics/interactions',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({events:batch}),keepalive})
          if(!r.ok){if(r.status===422)continue;queue.unshift(...batch);break}
          await r.json?.()
        }catch{queue.unshift(...batch);break}
      }}finally{inFlight=null}
    })()
    return inFlight
  }
  function activate(meta,state='none'){
    const operation=meta.core?uuid():''
    if(operation)pending.set(meta.action,{operation,meta,time:now(),page:currentPage,page_visit:visit})
    record('interaction',meta,{operation,state})
    if(meta.viewed && ['project','resume','interview'].includes(meta.material))record('material_view',meta)
    return operation
  }
  function begin(meta){
    if(!ready || doNotTrack || !contract.core.includes(meta.action))return null
    const candidate=pending.get(meta.action);pending.delete(meta.action)
    const recent=candidate && now()-candidate.time<10000 && candidate.page===currentPage && candidate.page_visit===visit
    const operation=recent?candidate.operation:uuid(),details={...(recent?candidate.meta:{}),...meta,page:currentPage,page_visit:visit,layout:currentLayout,preparation_flow:['knowledge.save','knowledge.index'].includes(meta.action)?preparationFlow:'',placement:recent?candidate.meta.placement:'api'}
    const failure=failures.get(meta.action),retry_of=failure && failure.visit===visit && now()-failure.time<300000?failure.operation:''
    record('submitted',details,{operation,retry_of});void flush()
    const headers={'X-AE-Operation':operation,'X-AE-Action':meta.action,'X-AE-Page':currentPage,'X-AE-Visit':visit,'X-AE-Session':visitSession(),
      'X-AE-Placement':fixed(details.placement,contract.placements,'api'),'X-AE-Path':path,'X-AE-Entry':entry,
      'X-AE-Material':fixed(details.material,contract.materials,'unknown'),'X-AE-Role':fixed(details.role,contract.roles,'unknown'),
      'X-AE-Context':fixed(details.context,contract.contexts,'unknown'),'X-AE-Retry':retry_of,
      'X-AE-UI':'muji_20261012','X-AE-Layout':currentLayout,'X-AE-Flow':details.preparation_flow}
    return {headers,operation,meta:details,start:now(),visit}
  }
  function end(op,transport=false,failed=false){
    if(!op)return
    record(transport?'transport_error':'client_wait',op.meta,{operation:op.operation,duration_ms:now()-op.start,reason:transport?'network':'none'})
    if(transport || failed)failures.set(op.meta.action,{operation:op.operation,visit:op.visit,time:now()});else failures.delete(op.meta.action)
    if(op.meta.action==='knowledge.index' && !transport && !failed)preparations.delete(op.visit)
  }
  function blocked(action,reason='invalid_input'){const p=pending.get(action);pending.delete(action);record('validation_blocked',p?.meta||{action},{operation:p?.operation||uuid(),reason})}
  function onceRecord(stage,meta,extra={}){const key=[visit,stage,meta.action,meta.placement,meta.content||'',meta.example_kind||'',meta.issue_kind||'',extra.reason||''].join(':');if(once.has(key))return;if(record(stage,meta,extra))once.add(key)}
  async function withPreparation(task){
    if(!ready || doNotTrack)return task()
    const previous=preparationFlow,saved=preparations.get(visit)
    preparationFlow=saved && now()-saved.time<300000?saved.flow:uuid()
    preparations.set(visit,{flow:preparationFlow,time:now()})
    try{return await task()}finally{preparationFlow=previous}
  }
  async function start(page='welcome'){
    ready=false;let available=false;currentPage=pages.has(page)?page:'welcome';visit=uuid();currentLayout=fixed(layout(),contract.layouts,'unknown')
    try{excluded=storage.getItem('agenteval.analytics.excluded')==='1';if(excluded){await preference(true);available=true}else{const r=await fetcher('/api/experiments/analytics/preference',{credentials:'same-origin',cache:'no-store'});if(r.ok){const data=await r.json();excluded=!!data.excluded;serverContractVersion=data.contract_version===3?3:2;available=true}}}catch{}
    ready=available;await send('page_view');record('page_enter',{action:'site.page',placement:'api'});return excluded
  }
  async function preference(value){const r=await fetcher('/api/experiments/analytics/preference',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({excluded:!!value})});if(!r.ok)throw new Error('统计设置未保存，请稍后重试。');const data=await r.json();serverContractVersion=data?.contract_version===3?3:2;excluded=!!value;try{storage.setItem('agenteval.analytics.excluded',excluded?'1':'0');if(excluded)storage.setItem('umami.disabled','1');else storage.removeItem('umami.disabled')}catch{}return excluded}
  function page(value){if(!pages.has(value)||value===currentPage)return;currentPage=value;visit=uuid();currentLayout=fixed(layout(),contract.layouts,'unknown');once.clear();pending.clear();preparations.clear();void send('page_view');record('page_enter',{action:'site.page',placement:'api'})}
  function activity(){if(ready&&!doNotTrack)visitSession()}
  function navigation(meta){entry=meta.action.startsWith('welcome.')?'home':meta.action.startsWith('guide.')?'guide':meta.action.startsWith('site.navigate.')?'navigation':meta.action.startsWith('history.')?'history':meta.action==='site.home'?'return':'in_page'}
  return {start,page,event:send,preference,activity,record,activate,begin,end,blocked,onceRecord,flush,navigation,withPreparation,
    setPath:value=>{if(['RETRIEVAL','AGENT_BEHAVIOR'].includes(value))path=value},get ready(){return ready},get pageVisit(){return visit}}
}
export const analytics=createAnalytics({referrer:globalThis.document?.referrer||'',doNotTrack:globalThis.navigator?.doNotTrack==='1'})
export function loadUmami(config=import.meta.env||{}){if(!config.VITE_UMAMI_WEBSITE_ID || !/^\/[A-Za-z0-9/._-]+\.js$/.test(config.VITE_UMAMI_SCRIPT||''))return;const script=document.createElement('script');script.defer=true;script.src=config.VITE_UMAMI_SCRIPT;script.dataset.websiteId=config.VITE_UMAMI_WEBSITE_ID;script.dataset.autoTrack='false';script.dataset.excludeSearch='true';script.dataset.excludeHash='true';script.dataset.doNotTrack='true';document.head.appendChild(script)}
