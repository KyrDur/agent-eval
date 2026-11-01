// Export boundaries redact credentials without mutating saved artifacts.
const sensitive=/(^|_)(api_key|authorization|proxy_authorization|password|secret|credential|access_token|refresh_token)($|_)/i
export function safeMaterial(value,{redactions=[]}={}){
 const marks=[]
 function visit(v,path='record'){
  if(Array.isArray(v))return v.map((x,i)=>visit(x,`${path}[${i}]`))
  if(v&&typeof v==='object')return Object.fromEntries(Object.entries(v).map(([k,x])=>{
   const normalized=k.replace(/([a-z])([A-Z])/g,'$1_$2')
   if(sensitive.test(normalized)||normalized.toLowerCase()==='token'||normalized.toLowerCase()==='x-api-key'){marks.push(path+'.'+k);return [k,'[认证信息已移除]']}
   return [k,visit(x,path+'.'+k)]
  }))
  if(typeof v!=='string')return v
  let s=v.replace(/\bBearer\s+[A-Za-z0-9._~+\/-]+/gi,'Bearer [已移除]').replace(/\bsk-(?:ant-)?[A-Za-z0-9_-]{8,}/g,'[密钥已移除]')
  s=s.replace(/(https?:\/\/)([^\s/@]+:[^\s/@]+)@/g,'$1[认证信息已移除]@').replace(/([?&](?:api[_-]?key|access_token|token|secret)=)[^&#\s"']+/gi,'$1[已移除]')
  for(const word of redactions.filter(s=>s.trim()))s=s.split(word).join('[业务内容已脱敏]')
  if(s!==v)marks.push(path)
  return s
 }
 return {data:visit(value),redactedPaths:marks}
}
