import {analytics} from './analytics.js'
// Explicit bindings only: never read labels, URLs, IDs, field values or textContent.
const controls=new Set()
function metadata(el){return {...el.__ae.binding,placement:el.closest('[data-analytics-location]')?.getAttribute('data-analytics-location') || el.__ae.binding.placement}}
function visibleContent(el){
  if(document.hidden)return false
  const r=el.getBoundingClientRect(),area=r.width*r.height
  const visible=Math.max(0,Math.min(innerHeight,r.bottom)-Math.max(0,r.top))*Math.max(0,Math.min(innerWidth,r.right)-Math.max(0,r.left))
  return area>0 && visible/area>=.5
}
function checkContent(el){
  if(!analytics.ready || !visibleContent(el)){
    clearTimeout(el.__ae.viewTimer);el.__ae.viewTimer=null;return
  }
  if(el.__ae.viewTimer)return
  const visit=analytics.pageVisit
  el.__ae.viewTimer=setTimeout(()=>{
    el.__ae.viewTimer=null
    if(el.__ae && visit===analytics.pageVisit && visibleContent(el))analytics.onceRecord('exposure',metadata(el))
  },1000)
}
function check(el){
  const meta=metadata(el)
  if(meta.kind==='view'){checkContent(el);return}
  if(!meta.core || !analytics.ready)return
  const rect=el.getBoundingClientRect()
  if(rect.width && rect.height && rect.top<innerHeight && rect.bottom>0 && rect.left<innerWidth && rect.right>0){
    analytics.onceRecord('exposure',meta)
    if(el.matches(':disabled'))analytics.onceRecord('unavailable',meta,{reason:meta.reason||'precondition'});else analytics.onceRecord('available',meta)
  }
}
const observer=typeof IntersectionObserver==='function'?new IntersectionObserver(entries=>{for(const {target,isIntersecting} of entries)if(target.__ae && (isIntersecting || target.__ae.binding.kind==='view'))check(target)},{threshold:[0,.5,1]}):null
export const trackDirective={
  mounted(el,{value}){
    const listeners=[],on=(name,fn,target=el)=>{target.addEventListener(name,fn,true);listeners.push([target,name,fn])}
    el.dataset.analyticsAction=value.action;el.dataset.analyticsPlacement=value.placement;
    el.__ae={binding:value,listeners};controls.add(el)
    const meta=()=>metadata(el)
    if(value.kind==='view'){} // Content markers only observe visibility; no click/text collection.
    else if(value.kind==='edit')on('input',()=>analytics.onceRecord('edit_start',meta()))
    else if(el.matches('select,input'))on('change',()=>analytics.activate(meta(),el.type==='checkbox'?(el.checked?'select':'deselect'):'change'))
    else {
      const form=el.matches('button:not([type="button"])')?el.closest('form'):null
      const activate=()=>{
        const m=meta();analytics.navigation(m)
        const state=el.matches('summary')?(el.parentElement.open?'collapse':'expand'):el.hasAttribute('aria-expanded')?(el.getAttribute('aria-expanded')==='true'?'collapse':'expand'):'none'
        if(m.action.startsWith('metric.help.')){if(!el.__ae.focusActivation)analytics.activate(m,'expand');el.__ae.focusActivation=false;return ''}
        return analytics.activate(m,state)
      }
      if(form){
        on('submit',event=>{if(event.submitter && event.submitter!==el)return;activate()},form)
        let invalid=false
        on('invalid',()=>{if(invalid)return;invalid=true;activate();analytics.blocked(value.action,'invalid_input');queueMicrotask(()=>{invalid=false})},form)
      } else on('click',()=>{if(el.matches(':disabled'))return;activate()})
      // Metric explanation can open through focus, before a click or keyboard activation.
      if(value.action.startsWith('metric.help.')){on('focus',()=>{el.__ae.focusActivation=true;analytics.activate(meta(),'expand')});on('blur',()=>{el.__ae.focusActivation=false})}
    }
    if(value.core || value.kind==='view')observer?.observe(el)
    check(el)
  },
  updated(el,{value}){el.dataset.analyticsAction=value.action;el.dataset.analyticsPlacement=value.placement;el.__ae.binding=value;check(el)},
  unmounted(el){clearTimeout(el.__ae.viewTimer);for(const [target,name,fn] of el.__ae.listeners)target.removeEventListener(name,fn,true);observer?.unobserve(el);controls.delete(el);delete el.__ae}
}
export function refreshControls(){for(const el of controls)check(el)}
export function installControlAnalytics(app){app.directive('track',trackDirective);globalThis.document?.addEventListener('visibilitychange',()=>{refreshControls();void analytics.flush()});globalThis.addEventListener?.('online',()=>void analytics.flush());globalThis.addEventListener?.('pagehide',()=>void analytics.flush({keepalive:true}))}
