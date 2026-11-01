<script setup>
import {computed} from 'vue'
const props=defineProps({count:Number,selected:Boolean})
// These are symbolic sheets for a configured limit, never retrieved document records.
const sheets=computed(()=>Number.isFinite(props.count)?Math.min(5,Math.max(0,props.selected?props.count:Math.ceil(props.count/10))):0)
</script>
<template>
 <svg class="retrieval-papers" :class="{selected}" viewBox="0 0 180 76" fill="none" aria-hidden="true">
  <g v-for="n in sheets" :key="n" :transform="`translate(${12+(n-1)*25},${5+(n%2)*6})`">
   <rect width="42" height="58" rx="4" class="paper-fill" />
   <path d="M9 15h24M9 23h24M9 31h24M9 39h17" />
  </g>
  <path v-if="count>5" d="M162 58h.2m6 0h.2m6 0h.2" class="paper-more" />
  <path v-if="!sheets" d="M14 18h44v40H14Z" stroke-dasharray="4 4" />
 </svg>
</template>
<style scoped>
.retrieval-papers{display:block;width:180px;max-width:100%;height:58px;color:#b8beb4;stroke:currentColor;stroke-width:1.2;stroke-linecap:round}.paper-fill{fill:#fff}.selected{color:#819277}.selected .paper-fill{fill:#f5f8f0}.paper-more{stroke-width:2.5}
@media(max-width:560px){.retrieval-papers{height:58px;width:130px}}
</style>
