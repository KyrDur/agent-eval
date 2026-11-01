// Separate receipt survives reloads without changing the selected experiment.
export function indexBuildController({client,storage,onChange,onReady,pollMs=1000}) {
 const key='agenteval.index-build.v1';let pending=null,timer=null,generation=0
 try { const value=JSON.parse(storage.getItem(key)||'null');if(value&&/^[A-Za-z0-9_-]{1,128}$/.test(value.request_id||'')&&value.body&&/^[A-Za-z0-9_-]{1,128}$/.test(value.dataset_id||'')&&(!value.job_id||/^[A-Za-z0-9_-]{1,128}$/.test(value.job_id)))pending=value } catch {}
 const persist=()=>{if(pending)storage.setItem(key,JSON.stringify(pending));else storage.removeItem?.(key)}
 const stop=()=>{clearTimeout(timer);generation++}
 async function read(){
  if(!pending)return null
  const old=pending
  const job=await client.get(old.job_id?'/index-tasks/'+old.job_id:'/index-task-receipts/'+old.request_id,{timeoutMs:10000,retryReads:true})
  if(pending!==old)return null
  if(!/^[A-Za-z0-9_-]{1,128}$/.test(job.job_id||'')||job.request_id!==old.request_id)throw new Error('索引回执无法核对，请保留当前请求编号。')
  pending={...pending,job_id:job.job_id};persist();onChange(job)
  if(job.status==='READY'){const index=await client.get('/knowledge-indices/'+job.index_id);await onReady(index);pending=null;persist();stop()}
  else if(['FAILED','CANCELLED'].includes(job.status)){pending=null;persist();stop()}
  return job
 }
 function poll(){stop();if(!pending)return;const current=generation
  timer=setTimeout(async()=>{try{await read();if(current===generation)poll()}catch(e){onChange({status:'UNKNOWN',error:e.message,request_id:pending?.request_id})}},pollMs);timer?.unref?.()
 }
 return {
  async start(dataset,config,model){
   if(pending)throw new Error('有待确认的建索引任务，请先读取进度或取消。')
   pending={request_id:crypto.randomUUID(),dataset_id:dataset.knowledge_dataset_id,body:{version:dataset.version,chunk_config:config,embedding_model:model}};persist();onChange({status:'SUBMITTING',request_id:pending.request_id})
   try{const job=await client.post(`/knowledge-datasets/${dataset.knowledge_dataset_id}/index-tasks`,{...pending.body,request_id:pending.request_id},{timeoutMs:15000});pending={...pending,job_id:job.job_id};persist();onChange(job);if(['READY','FAILED','CANCELLED'].includes(job.status))await read();else poll();return job}
   catch(e){if([400,401,403,404,409,422].includes(e.status)){pending=null;persist()}onChange({status:'UNKNOWN',error:e.message,request_id:pending?.request_id});throw e}
  },
  async resume(){if(!pending)return;try{await read();poll()}catch(e){onChange({status:'UNKNOWN',error:e.message,request_id:pending?.request_id})}},
  async retry(){if(!pending?.body)return;const job=await client.post(`/knowledge-datasets/${pending.dataset_id}/index-tasks`,{...pending.body,request_id:pending.request_id});pending={...pending,job_id:job.job_id};persist();onChange(job);await read();poll()},
  async cancel(){if(!pending)return;stop();if(!pending.job_id)await read();if(!pending)return;const job=await client.post('/index-tasks/'+pending.job_id+'/cancel',{});onChange(job);if(['READY','FAILED','CANCELLED'].includes(job.status)){pending=null;persist()}else poll()},
  dispose:stop,
 }
}
