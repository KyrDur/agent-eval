// Persist an idempotency receipt and a one-way configuration fingerprint only.
// Questions, prompts, answers, provider settings and keys never enter storage.
export const pendingFields=['pendingRequest','pendingFingerprint','pendingType','pendingRun']
export function pendingReceipt(p){
 if(!p.pendingRequest||!/^[a-f0-9]{64}$/.test(p.pendingFingerprint||'')||!['BASELINE','RETEST'].includes(p.pendingType))return null
 return {request_id:p.pendingRequest,fingerprint:p.pendingFingerprint,run_type:p.pendingType,run_id:p.pendingRun||null}
}
function canonical(value){
 if(Array.isArray(value))return value.map(canonical)
 if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])]))
 return value
}
export async function runFingerprint(body){
 const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(canonical(body))))
 return [...new Uint8Array(bytes)].map(v=>v.toString(16).padStart(2,'0')).join('')
}
