// Copy the complete supplied text while retaining the click's clipboard permission.
export async function copyCompleteText(text,{document=globalThis.document,clipboard=globalThis.navigator?.clipboard,timeoutMs=5000}={}){
 if(document?.execCommand){
  const active=document.activeElement,field=document.createElement('textarea')
  field.value=text;field.setAttribute('readonly','')
  field.style.cssText='position:fixed;left:-9999px;top:0;opacity:0;font-size:16px'
  let copied=false
  try{document.body.appendChild(field);field.focus?.({preventScroll:true});field.select();field.setSelectionRange(0,field.value.length);copied=document.execCommand('copy')}
  catch{/* Some browsers only support the asynchronous Clipboard API. */}
  finally{field.remove();active?.focus?.({preventScroll:true})}
  if(copied)return
 }
 if(!clipboard?.writeText)throw new Error('clipboard unavailable')
 let timer
 try{await Promise.race([clipboard.writeText(text),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('clipboard timeout')),timeoutMs)})])}
 finally{clearTimeout(timer)}
}
