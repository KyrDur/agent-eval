<script setup>
defineProps({name:String,size:{type:Number,default:20}})
const paths={
 home:'m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z',
 prepare:'M8 3H5a2 2 0 0 0-2 2v3m13-5h3a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3m8 0h3a2 2 0 0 0 2-2v-3M8 8h8v8H8Z',
 chart:'M4 20V4m0 16h17M9 16v-5m5 5V7m5 9v-8',
 adjust:'M4 7h7m4 0h5M4 17h3m4 0h9M11 4v6M7 14v6',
 compare:'M3 5h7v14H3Zm11 0h7v14h-7M7 9h0m11 0h0M6 13h1m10 0h1',
 folder:'M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z',
 log:'M8 3h11a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H8M3 7h9M3 12h9M3 17h9',
 scale:'M12 3v18M5 21h14M4 7h16M6 7l-4 8h8Zm12 0-4 8h8Z',
 help:'M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2-3 4m0 3h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
 book:'M12 6C9 3 4 3 2 4v15c3-1 7-1 10 2m0-15c3-3 8-3 10-2v15c-3-1-7-1-10 2Zm0 0v15',
 check:'m5 12 4 4L19 6',minus:'M5 12h14',alert:'M12 8v5m0 3h.01M12 3 2 21h20Z',
 search:'M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14m5-2 6 6',
 document:'M14 2H5a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9Zm0 0v7h7M7 13h10M7 17h7',
 chat:'M21 11a8 8 0 0 1-8 8H7l-5 3V11a9 9 0 0 1 19 0M7 9h10M7 13h6',
 arrow:'M4 12h16m-6-6 6 6-6 6',close:'m6 6 12 12M6 18 18 6',
 plug:'M8 2v5m8-5v5M5 7h14v4a7 7 0 0 1-14 0Zm7 11v4',
 list:'M9 5h12M9 12h12M9 19h12M3 5h.01M3 12h.01M3 19h.01',
 clock:'M12 6v6l4 2m6-2a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
 database:'M21 6c0 2.2-4 4-9 4s-9-1.8-9-4 4-4 9-4 9 1.8 9 4Zm0 0v12c0 2.2-4 4-9 4s-9-1.8-9-4V6m0 6c0 2.2 4 4 9 4s9-1.8 9-4',
 refresh:'M20 8a9 9 0 1 0 1 8M20 2v6h-6',download:'M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4',
 history:'M3 11a9 9 0 1 1 2 7M3 4v7h7m2-5v6l4 2',plus:'M12 5v14M5 12h14'
}
</script>
<template><svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="workspace-icon"><path :d="paths[name]||paths.document" /></svg></template>
<style scoped>.workspace-icon{flex-shrink:0;vertical-align:middle}</style>
