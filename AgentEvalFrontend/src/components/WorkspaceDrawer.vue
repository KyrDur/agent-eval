<script>
// Teleported drawers share a body lock, including when a log is opened from another drawer.
const drawerStack=[]
let drawerCount=0,originalOverflow='',originalInert=false,originalAria=null
function acquirePage(token){drawerStack.push(token);if(drawerCount++===0){originalOverflow=document.body.style.overflow;originalInert=document.getElementById('app')?.inert||false;document.body.style.overflow='hidden';const root=document.getElementById('app');if(root){originalAria=root.getAttribute('aria-hidden');root.inert=true;root.setAttribute('aria-hidden','true')}}}
function releasePage(token){const at=drawerStack.indexOf(token);if(at>=0)drawerStack.splice(at,1);if(--drawerCount<=0){drawerCount=0;document.body.style.overflow=originalOverflow;const root=document.getElementById('app');if(root){root.inert=originalInert;if(originalAria===null)root.removeAttribute('aria-hidden');else root.setAttribute('aria-hidden',originalAria)}}}
</script>
<script setup>
import {nextTick,onBeforeUnmount,ref,watch} from 'vue'
import WorkspaceIcon from './WorkspaceIcon.vue'
const props=defineProps({open:Boolean,title:String})
const emit=defineEmits(['close'])
const dialog=ref(null),drawerToken=Symbol('drawer')
let returnFocus,hasLock=false
function close(){emit('close')}
function keydown(event){
 if(drawerStack.at(-1)!==drawerToken)return
 if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close()}
 if(event.key==='Tab'){
  const targets=[...dialog.value.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary,[tabindex="0"]')].filter(el=>el.getClientRects().length)
  const first=targets[0],last=targets.at(-1)
  if(!dialog.value.contains(document.activeElement)){event.preventDefault();first?.focus();return}
  if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}
  else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}
 }
}
function restore(){if(hasLock){document.removeEventListener('keydown',keydown,true);releasePage(drawerToken);hasLock=false}returnFocus?.isConnected&&returnFocus.focus()}
watch(()=>props.open,async open=>{
 if(open){returnFocus=document.activeElement;await nextTick();if(!props.open)return;acquirePage(drawerToken);hasLock=true;document.addEventListener('keydown',keydown,true);dialog.value?.querySelector('[data-drawer-close]')?.focus()}
 else restore()
},{immediate:true})
onBeforeUnmount(restore)
</script>
<template>
 <Teleport to="body"><div v-if="open" class="workspace-drawer-backdrop" @click.self="close">
  <section ref="dialog" class="workspace-drawer" role="dialog" aria-modal="true" :aria-label="title">
   <header><h2>{{title}}</h2><button type="button" class="drawer-close" aria-label="关闭查看区" data-drawer-close @click="close"><WorkspaceIcon name="close" /></button></header>
   <div class="workspace-drawer-content"><slot /></div>
  </section>
 </div></Teleport>
</template>
<style>
.workspace-drawer-backdrop{position:fixed;inset:0;background:#20271f66;z-index:1000;display:flex;justify-content:flex-end}.workspace-drawer{width:min(680px,94vw);height:100dvh;display:flex;flex-direction:column;background:var(--color-surface);box-shadow:-12px 0 40px #00000012;min-width:0}.workspace-drawer>header{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:20px 24px;border-bottom:1px solid var(--border);flex-shrink:0}.workspace-drawer>header h2{font-size:19px;margin:0}.drawer-close{border:0;background:var(--color-surface-subtle);border-radius:8px;padding:9px;display:grid;place-items:center;color:var(--color-text)}.workspace-drawer-content{padding:24px;overflow:auto;overscroll-behavior:contain;overflow-wrap:anywhere;min-height:0;flex:1}.workspace-drawer-content .panel{margin-bottom:18px;padding:18px}.workspace-drawer-content .two-column{grid-template-columns:1fr}.workspace-drawer-content pre{max-width:100%;white-space:pre-wrap;overflow-wrap:anywhere}.workspace-drawer-content h3{font-size:16px;margin:18px 0 12px}.workspace-drawer-content h4{font-size:14px;margin:18px 0 10px}.workspace-drawer-content p{font-size:14px;line-height:1.85}.workspace-drawer-content .agent-response{white-space:normal;background:var(--color-canvas);padding:18px;border-radius:8px;margin:12px 0}.workspace-drawer-content .drawer-tabs{display:flex;gap:16px;border-bottom:1px solid var(--border);margin-bottom:22px;overflow-x:auto}.drawer-tabs button{border:0;border-bottom:2px solid transparent;background:none;padding:8px 0 12px;white-space:nowrap;font-size:13px;color:var(--muted)}.drawer-tabs button[aria-selected=true]{color:var(--color-text);border-color:var(--color-text)}
@media(max-width:600px){.workspace-drawer{width:100vw}.workspace-drawer>header,.workspace-drawer-content{padding:18px}}
</style>
