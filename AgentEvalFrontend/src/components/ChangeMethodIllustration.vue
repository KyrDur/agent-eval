<script setup>
import {computed} from 'vue'
const props=defineProps({type:String,ready:Boolean,retrievalMode:String,contextStrategy:String})
const kind=computed(()=>({KNOWLEDGE_UPDATE:'knowledge',ANSWER_PROMPT_CHANGE:'rules',QUERY_REWRITE_TOGGLE:'query',RERANK_TOGGLE:'order',CHUNKING_CHANGE:'chunks',EMBEDDING_CHANGE:'matching',RETRIEVAL_MODE_CHANGE:'search',CONTEXT_STRATEGY_CHANGE:'context',LOGS:'logs',COMPARISON:'comparison'})[props.type]||'search')
</script>
<template>
 <svg :class="['method-illustration','mode-'+retrievalMode,{'context-selected':contextStrategy==='SELECTED'}]" viewBox="0 0 400 180" fill="none" aria-hidden="true">
  <path class="wash" d="M58 129C28 83 81 30 142 39c39-36 80-11 112 2 46-10 104 12 96 57 14 38-30 66-84 55-49 19-86-1-112 2-41 14-81 1-96-26Z" />
  <g v-if="kind==='knowledge'">
   <g transform="translate(65 28) rotate(-8 44 60)"><path class="paper" d="m5 3 79-1 3 119-83 1Z"/><path d="M20 25h49M20 38h49M20 51h35M20 81h43M20 94h32"/><rect class="accent-fill" x="17" y="62" width="56" height="10" rx="2" stroke="none"/></g>
   <path class="arrow" d="M171 79c21-10 38-9 55 2m-9-10 10 11-14 5"/>
   <g transform="translate(241 36)"><path class="paper" d="M0 0h94v103H0Z"/><path d="M0 58h94M0 103h94M13 12v40m12-40v40m14-40v40m29-40v40M16 72v25m13-25v25m17-25v25m19-25v25"/><path class="accent-fill" d="M44 10h15v43H44Z"/><path class="terracotta-fill" d="m73 72 11-2 6 25-12 2Z"/></g>
   <circle class="accent-fill" cx="325" cy="38" r="19"/>
   <path v-if="ready" class="light-stroke" d="m316 38 6 6 11-13"/><path v-else class="light-stroke" d="M325 29v18m-9-9h18"/>
  </g>
  <g v-else-if="kind==='rules'">
   <g transform="translate(66 24) rotate(-5 48 65)"><path class="paper" d="M2 5 94 2l3 128-94 1Z"/><path d="M19 23h59M19 40h34M42 64h35M42 87h35M42 110h24"/><rect x="18" y="55" width="14" height="14" rx="3"/><rect x="18" y="79" width="14" height="14" rx="3"/><rect x="18" y="103" width="14" height="14" rx="3"/><path v-if="ready" class="blue-stroke" d="m20 61 4 4 7-8m-11 29 4 4 7-8"/></g>
   <path class="arrow" d="M181 91h42m-11-10 12 10-12 10"/>
   <g transform="translate(245 45) rotate(4 49 44)"><path class="paper" d="M0 0h99v76H38L16 94V76H0Z"/><path d="M17 20h65M17 35h39M17 50h47"/><path class="blue-stroke" d="m67 48 7 7 13-17"/></g>
   <path class="terracotta-stroke" d="m195 37 3-14m8 18 10-8m-31 8-8-8"/>
  </g>
  <g v-else-if="kind==='query'">
   <path class="paper" d="M49 36h112v77h-25l-20 19 1-19H49Z"/><path d="M66 57h72M66 73h55M66 89h64"/>
   <path class="arrow" d="M179 88c18-17 37-17 53 0m-12-13 14 14-18 2"/>
   <g transform="translate(251 39) rotate(6 37 49)"><path class="paper" d="M0 0h74v100H0Z"/><path d="M13 22h47M13 36h47M13 51h30M13 76h26"/></g>
   <circle class="accent-fill" cx="317" cy="108" r="25"/><circle class="light-stroke" cx="313" cy="104" r="11"/><path class="light-stroke" d="m321 112 10 11"/>
  </g>
  <g v-else-if="kind==='order'">
   <g v-for="n in 3" :key="n" :transform="`translate(${55+(n-1)*9},${27+(n-1)*25})`"><path class="paper" d="M0 0h91v39H0Z"/><path d="M14 12h63M14 24h42"/></g>
   <path class="arrow" d="M184 89h40m-10-11 12 11-12 11"/>
   <g v-for="n in 3" :key="'after'+n" :transform="`translate(${252-(n-1)*4},${27+(n-1)*34})`"><rect :class="n===1?'accent-fill':'paper'" width="91" height="29" rx="3"/><path :class="{'light-stroke':n===1}" d="M14 10h62M14 20h42"/></g>
   <path class="terracotta-stroke" d="m154 45 8-13m-1 21 14-2"/>
  </g>
  <g v-else-if="kind==='chunks'">
   <g transform="translate(61 23) rotate(-4 44 65)"><path class="paper" d="M0 0h88v132H0Z"/><path d="M14 21h59M14 33h59M14 47h42M14 67h59M14 79h59M14 103h59M14 115h42"/><path class="terracotta-stroke" stroke-dasharray="4 4" d="M-7 41h102M-7 87h102"/></g>
   <path class="arrow" d="M181 87h42m-11-10 12 10-12 10"/>
   <g transform="translate(252 24)"><rect class="paper" width="89" height="59" rx="4"/><rect class="paper" y="70" width="89" height="59" rx="4"/><path d="M14 17h60M14 30h60M14 44h42M14 87h60M14 101h60M14 115h42"/><path class="blue-stroke" d="M-10 3h-8v52h8M99 73h8v52h-8"/></g>
  </g>
  <g v-else-if="kind==='matching'">
   <path class="paper" d="M47 47h72v87H47Z"/><path d="M61 66h44M61 79h44M61 93h26"/>
   <path class="arrow" d="M138 91h35m-10-10 12 10-12 10"/>
   <path d="m202 49 41 13-24 42 52 19 32-46 36 42M202 49l17 55m24-42 60 15m-32 46 68-4"/>
   <circle class="paper" cx="202" cy="49" r="8"/><circle class="accent-fill" cx="243" cy="62" r="9"/><circle class="paper" cx="219" cy="104" r="8"/><circle class="terracotta-fill" cx="271" cy="123" r="9"/><circle class="paper" cx="303" cy="77" r="8"/><circle class="accent-fill" cx="339" cy="119" r="9"/>
  </g>
  <g v-else-if="kind==='search'">
   <g class="keyword-route"><rect class="paper" x="55" y="26" width="92" height="51" rx="6"/><path d="M71 43h18m8 0h30M71 58h43"/></g>
   <g class="semantic-route"><path class="paper" d="M55 101h92v49H55Z"/><path class="blue-stroke" d="m70 132 13-16 18 13 16-12 14 16"/></g>
   <path class="keyword-route" d="M158 52c37 0 40 37 64 37"/><path class="semantic-route" d="M158 125c37 0 40-36 64-36"/>
   <path class="arrow" d="M219 89h24m-9-9 10 9-10 9"/>
   <g transform="translate(263 42)"><path class="paper" d="M0 0h74v99H0Z"/><path d="M14 22h46M14 37h46M14 52h30M14 74h40"/><circle class="accent-fill" cx="65" cy="85" r="20"/><circle class="light-stroke" cx="61" cy="81" r="8"/><path class="light-stroke" d="m67 87 8 9"/></g>
  </g>
  <g v-else-if="kind==='context'">
   <g class="context-neighbor" transform="translate(48 52) rotate(-6 37 43)"><rect class="paper" width="74" height="88" rx="3"/><path d="M13 21h47M13 36h47M13 51h34M13 67h41"/></g>
   <g transform="translate(161 31)"><rect class="accent-fill" width="78" height="111" rx="4"/><path class="light-stroke" d="M14 24h49M14 40h49M14 56h36M14 81h45"/></g>
   <g class="context-neighbor" transform="translate(279 52) rotate(6 37 43)"><rect class="paper" width="74" height="88" rx="3"/><path d="M13 21h47M13 36h47M13 51h34M13 67h41"/></g>
   <path class="context-neighbor" d="M135 88h14m-7-7v14M251 88h14m-7-7v14"/>
   <path class="terracotta-stroke" d="M124 151c34 14 117 14 150 0"/>
  </g>
  <g v-else-if="kind==='comparison'">
   <g transform="translate(54 34) rotate(-5 43 54)"><rect class="paper" width="86" height="109" rx="5"/><path d="M16 23h55M16 39h55M16 55h38M16 80h47"/><path class="terracotta-stroke" d="M16 95h27"/></g>
   <g transform="translate(258 34) rotate(5 43 54)"><rect class="paper" width="86" height="109" rx="5"/><path d="M16 23h55M16 39h55M16 55h38M16 80h47"/><path class="blue-stroke" d="M16 95h40"/></g>
   <path class="arrow" d="M160 67h72m-10-9 11 9-11 9M232 116h-72m10-9-11 9 11 9"/>
   <circle class="accent-fill" cx="199" cy="91" r="25"/><circle class="light-stroke" cx="195" cy="87" r="11"/><path class="light-stroke" d="m203 95 11 11"/>
  </g>
  <g v-else-if="kind==='logs'">
   <g transform="translate(103 28) rotate(-9 53 60)"><rect class="paper" width="101" height="121" rx="5"/><path d="M17 25h64M17 40h64M17 55h45M17 79h64M17 94h41"/></g>
   <g transform="translate(196 37) rotate(7 44 55)"><rect class="paper" width="88" height="108" rx="5"/><path d="M17 23h53M17 38h53M17 53h34M17 77h45"/></g>
   <path class="accent-fill" d="M281 94c22-3 43 9 41 30-2 18-21 29-43 23l-17 10 4-22c-9-19-4-35 15-41Z"/>
   <path class="light-stroke" d="M280 114h26m-26 12h17"/>
   <path class="terracotta-stroke" d="m85 55-11-6m17-5-3-12m206 4 8-10m-1 21 13-3"/>
  </g>
 </svg>
</template>
<style scoped>
.method-illustration{display:block;width:100%;height:auto;stroke:#646b58;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}.wash{fill:#eeebdf;stroke:none}.paper{fill:#fffdf7}.accent-fill{fill:#8e9f7b;stroke:#6b7c5d}.terracotta-fill{fill:#d6a088;stroke:#ac735d}.blue-stroke{stroke:#6184b2;stroke-width:2.4}.terracotta-stroke{stroke:#b97f61;stroke-width:2}.accent-fill+.light-stroke,.light-stroke{stroke:#fffdf7}.arrow{stroke:#89927d;stroke-width:2}
.mode-VECTOR .keyword-route,.mode-BM25 .semantic-route,.context-selected .context-neighbor{opacity:.18}
</style>
