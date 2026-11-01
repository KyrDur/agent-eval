// Only receipt IDs enter browser storage. The server owns the confirmed snapshot.
export const flowStages={SAVED:'方案已保存',PREPARING:'正在按新方案准备资料',APPLYING:'正在应用实验配置',SUBMITTING:'正在确认复测回执',RUNNING:'正在用原题复测',COMPARING:'正在整理前后比较',COMPLETE:'复测与比较已完成',PARTIAL:'仅部分完成',FAILED:'流程停在失败步骤',CANCELLED:'已停止后续任务',UNKNOWN:'需要读取已有回执'}
export const flowTerminal=['COMPLETE','PARTIAL','FAILED','CANCELLED']
export function flowController({client,storage,onChange,onArtifacts,pollMs=1000,autoPoll=true}){
 const key='agenteval.retest-flow.v1';let id=null,timer,generation=0,reading=false
 try{const value=storage.getItem(key);if(/^[A-Za-z0-9_-]{1,100}$/.test(value||''))id=value}catch{}
 const stop=()=>{clearTimeout(timer);generation++}
 async function sync(){
  if(!id||reading)return
  const current=generation;reading=true
  try{const flow=await client.get('/retest-flows/'+id,{timeoutMs:10000,retryReads:true});if(current!==generation)return
   onChange(flow);await onArtifacts(flow)
   if(autoPoll&&!flowTerminal.includes(flow.stage)&&flow.stage!=='UNKNOWN')timer=setTimeout(sync,pollMs)
  }catch(e){if(current===generation)onChange({flow_id:id,stage:'UNKNOWN',error:e.message})}
  finally{reading=false}
 }
 return {async start(body){if(reading)throw new Error('正在读取原任务，请稍后再操作。');stop();id=crypto.randomUUID();storage.setItem(key,id)
   // Save the ID before POST. An uncertain response is reconciled with GET only.
   onChange({flow_id:id,stage:'SAVED'})
   try{const flow=await client.post('/retest-flows',{...body,request_id:id},{timeoutMs:15000});onChange(flow)}
   catch(e){if([400,401,403,409,422].includes(e.status)){storage.removeItem?.(key);id=null;onChange(null);throw e}onChange({flow_id:id,stage:'UNKNOWN',error:e.message})}
   await sync()
  },sync:async()=>{stop();await sync()},resume:async()=>{if(!id)return;stop();onChange(await client.post('/retest-flows/'+id+'/resume',{}));await sync()},
  cancel:async()=>{if(!id)return;stop();onChange(await client.post('/retest-flows/'+id+'/cancel',{}));await sync()},
  restore:sync,dispose:stop,clear(){stop();id=null;storage.removeItem?.(key);onChange(null)}}
}
