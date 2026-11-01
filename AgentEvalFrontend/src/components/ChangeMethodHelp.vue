<script>
// Keep a single explanation visible when moving between method cards.
let dismissActiveHelp=null
</script>
<script setup>
import {computed,nextTick,onBeforeUnmount,onMounted,ref,useId,watch} from 'vue'
import {changeMethodPrinciples} from '../change-method-principles.js'
import {changeOptions} from '../retrieval-change-options.js'
const props=defineProps({type:{type:String,required:true},label:String})
const explanation=computed(()=>changeMethodPrinciples[props.type])
const title=computed(()=>props.label||changeOptions.find(option=>option.value===props.type)?.label||'修改方法')
const id=useId(),anchor=ref(null),popup=ref(null),open=ref(false),ready=ref(false),pinned=ref(false),focused=ref(false)
const placement=ref({}),above=ref(false)
let closeTimer
function cancelClose(){clearTimeout(closeTimer)}
function dismiss(){cancelClose();open.value=false;pinned.value=false;ready.value=false;if(dismissActiveHelp===dismiss)dismissActiveHelp=null}
function show(){cancelClose();if(dismissActiveHelp!==dismiss){dismissActiveHelp?.();dismissActiveHelp=dismiss}open.value=true}
function closeSoon(){cancelClose();if(!pinned.value&&!focused.value)closeTimer=setTimeout(dismiss,160)}
function toggle(){if(pinned.value)dismiss();else{show();pinned.value=true}}
function position(){
 if(!open.value||!anchor.value||!popup.value)return
 const rect=anchor.value.getBoundingClientRect(),width=popup.value.offsetWidth,height=popup.value.offsetHeight
 if(rect.bottom<0||rect.top>window.innerHeight){dismiss();return}
 const gap=10,margin=12,below=window.innerHeight-rect.bottom-gap-margin
 above.value=below<height&&rect.top>below
 const top=above.value?rect.top-gap-height:rect.bottom+gap
 placement.value={left:Math.max(margin,Math.min(rect.left+rect.width/2-width/2,window.innerWidth-width-margin))+'px',top:Math.max(margin,Math.min(top,window.innerHeight-height-margin))+'px'}
 ready.value=true
}
function outside(event){if(open.value&&!anchor.value?.contains(event.target)&&!popup.value?.contains(event.target))dismiss()}
function escape(event){if(open.value&&event.key==='Escape'){event.preventDefault();event.stopPropagation();dismiss()}}
function blur(){focused.value=false;dismiss()}
watch(open,async value=>{if(value){ready.value=false;await nextTick();position()}})
watch(()=>props.type,dismiss)
onMounted(()=>{window.addEventListener('resize',position);window.addEventListener('scroll',position,true);window.addEventListener('keydown',escape,true);document.addEventListener('pointerdown',outside,true)})
onBeforeUnmount(()=>{dismiss();window.removeEventListener('resize',position);window.removeEventListener('scroll',position,true);window.removeEventListener('keydown',escape,true);document.removeEventListener('pointerdown',outside,true)})
</script>
<template>
 <span v-if="explanation" class="change-method-help" @mouseenter="show" @mouseleave="closeSoon">
  <button ref="anchor" type="button" class="change-method-help-trigger" :aria-label="`${title}：原理说明`" :aria-describedby="open?id:undefined" @focus="focused=true;show()" @blur="blur" @click.stop="toggle"><span aria-hidden="true">?</span></button>
  <Teleport to="body"><section v-if="open" ref="popup" :id="id" role="tooltip" class="change-method-help-popup" :class="{'is-above':above}" :style="[placement,{visibility:ready?'visible':'hidden'}]" @mouseenter="cancelClose" @mouseleave="closeSoon">
   <strong class="change-method-help-title">{{title}} · 原理</strong>
   <p>{{explanation.principle}}</p>
   <p class="change-method-help-example"><b>举个例子</b>{{explanation.example}}</p>
   <p class="change-method-help-distinction">{{explanation.distinction}}</p>
  </section></Teleport>
 </span>
</template>
<style scoped>
.change-method-help{display:inline-flex;flex-shrink:0;vertical-align:middle;line-height:1}
.change-method-help button.change-method-help-trigger{display:inline-grid;place-items:center;width:30px;height:30px;min-width:30px;min-height:30px;padding:0;border:0;border-radius:50%;background:transparent;color:#68785d;cursor:help;gap:0}
.change-method-help button.change-method-help-trigger>span{display:grid;place-items:center;flex:none;width:19px;height:19px;margin:0;border:1px solid #8d9b81;border-radius:50%;font-size:12px;font-weight:600;line-height:1;color:inherit}
.change-method-help button.change-method-help-trigger:hover,.change-method-help button.change-method-help-trigger:focus-visible{background:#e4eadc;color:#354730}
.change-method-help-trigger:focus-visible{outline:2px solid var(--color-focus);outline-offset:2px}
.change-method-help-popup{position:fixed;z-index:1200;box-sizing:border-box;width:min(336px,calc(100vw - 24px));max-height:calc(100dvh - 24px);overflow:auto;padding:18px;border:1px solid #c6cdbb;border-radius:10px;background:#fffef9;box-shadow:0 8px 30px #25301e24;color:var(--color-text,#292c27);text-align:left;font-size:14px;font-weight:400;line-height:1.8;white-space:normal;overflow-wrap:anywhere}
.change-method-help-popup .change-method-help-title{display:block;margin:0 0 9px;font-size:14px;font-weight:650;line-height:1.6;color:#354730}
.change-method-help-popup p{margin:0;font-size:14px;line-height:1.8}
.change-method-help-popup .change-method-help-example{margin-top:12px;padding:10px 12px;border-radius:6px;background:#f0f3e9}
.change-method-help-example b{display:block;margin-bottom:3px;font-size:12px;font-weight:600;color:#56694b}
.change-method-help-popup .change-method-help-distinction{margin-top:12px;padding-top:11px;border-top:1px solid #e0e4d7;font-size:13px;color:#5c6259}
@media(pointer:coarse){.change-method-help button.change-method-help-trigger{width:36px;height:36px;min-width:36px;min-height:36px}}
</style>
