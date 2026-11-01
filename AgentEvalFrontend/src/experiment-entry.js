import {reactive} from 'vue'
import {api,ApiError} from './api.js'
import {readPointers} from './presentation.js'
import {createWorkspace} from './workspace.js'
import {createRetrievalWorkspace,readRetrievalPointers} from './retrieval-workspace.js'
import {createPracticeWorkspace} from './practice-workspace.js'
import {createAiAssistance,restoreAiDrafts} from './ai-assistance.js'

// Browsing the landing page or practice must not replace the remembered experiment
// with empty pointers before the visitor has chosen what to open.
export function createEntryStorage(storage=globalThis.localStorage){
  let writable=false
  return {getItem:key=>storage.getItem(key),setItem:(key,value)=>{if(writable)storage.setItem(key,value)},
    removeItem:key=>{if(writable)storage.removeItem?.(key)},
    activate(){writable=true},hold(){writable=false}}
}

export function createExperimentEntry(work,rag,mode,storage,{client=api,timeoutMs=20000,practice,ai}={}){
  const remembered=()=>mode.value==='RETRIEVAL'?readRetrievalPointers(storage):readPointers(storage)
  const hasSaved=()=>Object.entries(remembered()).some(([key,value])=>key!=='step'&&!!value)||!!readPointers(storage).session
  const state=reactive({pending:true,loading:false,hasSaved:hasSaved(),error:null})
  let generation=0,controller=null
  function cancel(){generation++;controller?.abort();controller=null;state.loading=false;state.error=null}
  function choose(){cancel();storage.hold();state.pending=true;refreshChoice()}
  function startFresh(){
    cancel();storage.activate();work.reset();rag.reset();work.state.initialized=true
    state.pending=false;work.go('setup')
  }
  async function resume({runId}={}){
    cancel();storage.hold();state.pending=true;state.loading=true
    const current=++generation,abort=new AbortController();controller=abort
    const timer=setTimeout(()=>abort.abort(),timeoutMs)
    // Restore into isolated state and apply it only after every required read has
    // succeeded. Cancelled/late responses cannot overwrite a new experiment.
    const readClient={get:(path,options={})=>client.get(path,{...options,signal:abort.signal}),
      list:(group)=>client.list(group,{signal:abort.signal})}
    const temporaryStorage={getItem:key=>storage.getItem(key),setItem(){}}
    const oldWork=createWorkspace(temporaryStorage,readClient,{autoPoll:false})
    const oldRag=createRetrievalWorkspace(oldWork,temporaryStorage,readClient,{autoPoll:false})
    const oldPractice=createPracticeWorkspace(oldWork,oldRag,temporaryStorage,readClient)
    const oldAi=createAiAssistance()
    try{
      if(mode.value==='RETRIEVAL'){
        if(runId)await oldRag.open(runId,{includeLatestRetest:false,useFrozenControls:true})
        else{
          await oldRag.restore({resultsOnly:readPointers(storage).step==='evaluate'})
          const session=readPointers(storage).session
          if(!oldWork.state.session&&session)oldWork.state.session=await readClient.get('/provider-sessions/'+session)
        }
        oldWork.state.step=runId?'evaluate':readPointers(storage).step||'setup'
      }else if(runId){await oldWork.history();await oldWork.openHistory(runId)}
      else await oldWork.restore()
      // Other modules are restored only when that is the page the visitor chose
      // to continue. A result page does not need every chat, draft and rubric.
      if(practice&&oldWork.state.step==='chat')await oldPractice.restore()
      if(ai&&['knowledge','define'].includes(oldWork.state.step))await restoreAiDrafts(oldAi,readClient)
      if(current!==generation||abort.signal.aborted)throw new ApiError('RECORD_READ_TIMEOUT',0)
      Object.assign(work.state,oldWork.state,{initialized:true,busy:'',error:null,notice:''})
      Object.assign(rag.state,oldRag.state)
      if(practice&&oldWork.state.step==='chat')Object.assign(practice.state,oldPractice.state)
      if(ai&&['knowledge','define'].includes(oldWork.state.step))Object.assign(ai,oldAi)
      storage.activate();work.go(work.state.step==='welcome'?'setup':work.state.step);rag.persist()
      state.pending=false;state.loading=false;state.hasSaved=hasSaved()
      if(mode.value==='RETRIEVAL'){rag.resumePolling();rag.syncIndex?.()}else work.resumePolling()
      return true
    }catch(error){
      if(current===generation){state.loading=false;state.error=error instanceof ApiError?{title:error.title,message:error.message}:{title:'暂时无法读取这次实验',message:'可以重试，或开始新实验。原记录仍然保留。'}}
      return false
    }finally{clearTimeout(timer);oldWork.dispose();oldRag.dispose();if(current===generation)controller=null}
  }
  function refreshChoice(){state.hasSaved=hasSaved()}
  return {state,cancel,choose,startFresh,resume,refreshChoice,dispose:cancel}
}
