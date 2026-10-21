<script setup>
import {computed,ref,watch} from 'vue'
import {labelFor} from '../calibration-presentation.js'
const props=defineProps({metrics:Object})
const emit=defineEmits(['inspect'])
const slice=ref('all'),filter=ref('ALL')
watch(()=>props.metrics,()=>{slice.value='all';filter.value='ALL'})
const current=computed(()=>slice.value==='all'?props.metrics:slice.value.startsWith('scenario:')?
  props.metrics.by_scenario?.[slice.value.slice(9)]||props.metrics:props.metrics.by_distribution?.[slice.value]||props.metrics)
const descriptions={
  agreement:['人机判断一致率','人和 AI 都能判定时，有多少判断相同。'],
  false_pass:['AI 错误放行','人认为不合格，AI 却判合格；分母为人工不合格事件。'],
  false_fail:['AI 错误拒绝','人认为合格，AI 却判不合格；分母为人工合格事件。'],
  critical_miss:['严重错误漏检','AI 漏掉了多少人工确认的严重错误；无法评分另列。'],
  coverage:['成功完成评分','得到合格或不合格判定的数量，不能当成答对数量。'],
  paired_coverage:['人机可比较数量','人和 AI 都有明确判定，才能比较是否一致。'],
  human_reference_coverage:['独立人工参照覆盖','已有真实独立人工最终判定的数量。'],
  repeat_stability:['重复评分一致','重复评分均可用且判断相同的回答占比。单次运行不可计算。'],
}
const cards=computed(()=>Object.entries(descriptions).filter(([key])=>current.value?.[key]))
const rows=computed(()=>(current.value?.rows||[]).filter(r=>filter.value==='ALL'||r.relation===filter.value||r.execution_status===filter.value||r.reference_state===filter.value||filter.value===`CELL:${r.human}:${r.machine}`))
const decisions=computed(()=>current.value.machine_decisions||{pass:current.value.rows.filter(r=>r.machine==='PASS').length,fail:current.value.rows.filter(r=>r.machine==='FAIL').length,pending:current.value.rows.filter(r=>r.machine==='PENDING').length,unavailable:current.value.rows.filter(r=>!r.machine).length})
const outcomeLabel=(key)=>({YES:'是',NO:'否',INSUFFICIENT:'无法判断',UNAVAILABLE:'没有可用记录'}[key]||key)
const display=v=>v.value==null?'不可计算':(v.value*100).toFixed(1)+'%'
</script>
<template>
  <section v-if="metrics" class="cal-metrics">
    <label>统计范围<select v-model="slice"><option value="all">全部评分事件</option><option value="actual_natural">实际使用 · 非诊断</option><option value="non_diagnostic">全部非诊断样本</option><option value="diagnostic">植入错误的诊断样本</option><option v-for="(_,name) in metrics.by_scenario" :key="name" :value="'scenario:'+name">场景：{{name}}</option></select></label>
    <p class="note">{{current.sample_count}} 份固定回答，每份评 {{current.repetitions}} 次。下面的“AI 判合格”是机器意见；有独立人工参照后，才能检查它是否判得合理。</p>
    <div class="cal-result-summary"><span>AI 判合格 <strong>{{decisions.pass}}</strong></span><span>AI 判不合格 <strong>{{decisions.fail}}</strong></span><span>资料不足待判断 <strong>{{decisions.pending}}</strong></span><span>评分不可用 <strong>{{decisions.unavailable}}</strong></span></div>
    <div class="rag-metric-grid"><button v-for="[key,description] in cards" :key="key" class="metric-card" @click="filter=key==='false_pass'?'FALSE_PASS':key==='false_fail'?'FALSE_FAIL':'ALL'"><small>{{description[0]}}</small><strong>{{display(current[key])}}</strong><small>{{current[key].numerator}} / {{current[key].denominator}}</small><small>{{description[1]}}</small></button></div>
    <p class="muted">{{current.rate_note}}</p>
    <p v-if="!current.agreement.denominator" class="note">目前缺少人和 AI 都能比较的判定，不能据此宣称评分准确率。</p>
    <h3>人与 AI 怎样判断 · 点击数量看具体题目</h3><table class="cal-table"><thead><tr><th>人工判断</th><th>AI 判合格</th><th>AI 判不合格</th></tr></thead><tbody><tr v-for="human in ['PASS','FAIL']" :key="human"><th>{{labelFor(human)}}</th><td v-for="machine in ['PASS','FAIL']" :key="machine"><button class="text-button" @click="filter=`CELL:${human}:${machine}`">{{current.matrix[human][machine].count}}</button></td></tr></tbody></table>
    <details class="evidence"><summary>评分失败、人工分歧与调用记录</summary><p><span v-for="(count,status) in current.health" :key="status" class="pill">{{labelFor(status)}}：{{count}} </span></p><p>严重错误无法检查：{{current.critical_unavailable.numerator}} / {{current.critical_unavailable.denominator}}</p><template v-if="current.unavailable_on_human_fail"><p>人工认为不合格、但 AI 评分不可用：{{current.unavailable_on_human_fail.numerator}} / {{current.unavailable_on_human_fail.denominator}}</p><p>人工认为合格、但 AI 评分不可用：{{current.unavailable_on_human_pass.numerator}} / {{current.unavailable_on_human_pass.denominator}}</p></template><p v-if="current.reconciliation">结果对账：{{current.reconciliation.balanced?'完整':'存在缺失或重复'}}。应评 {{current.reconciliation.expected}}，收到 {{current.reconciliation.received}}，缺失 {{current.reconciliation.missing}}，重复 {{current.reconciliation.duplicates}}，意外结果 {{current.reconciliation.unexpected}}。</p><p>请求 {{current.cost.request_count}} 次 · 合计耗时 {{(current.cost.latency_ms/1000).toFixed(2)}} 秒 · 用量已知 {{current.cost.usage_available_judgments}} / {{current.expected_judgments}}。费用未知。</p><p>输入 token：{{current.cost.usage?.input_tokens??'未知'}} · 输出 token：{{current.cost.usage?.output_tokens??'未知'}}</p></details>
    <details class="evidence"><summary>问题是否解决、回答是否诚实</summary><section v-for="[key,title] in [['task_resolution','用户问题是否解决'],['faithfulness','是否忠于所见证据']]" :key="key"><h4>{{title}}</h4><p v-for="side in ['human','machine']" :key="side">{{side==='human'?'人工':'AI'}}：<span v-for="(count,outcome) in current[key][side]" :key="outcome">{{outcomeLabel(outcome)}} {{count}}； </span></p></section><section v-for="[key,title] in [['task_failure_reasons','任务未完成的原因'],['answer_error_tags','回答本身的错误']]" :key="key"><h4>{{title}}</h4><p v-for="side in ['human','machine']" :key="side">{{side==='human'?'人工':'AI'}}：<span v-for="(count,reason) in current[key][side]" :key="reason">{{reason}} {{count}}； </span><span v-if="!Object.keys(current[key][side]).length">尚无记录</span></p></section></details>
    <label>筛选具体问题<select v-model="filter"><option value="ALL">全部，包括无法评分的题目</option><option v-if="filter.startsWith('CELL:')" :value="filter">按上方人机判断筛选</option><option value="AGREE">人机判断一致</option><option value="FALSE_PASS">AI 错误放行</option><option value="FALSE_FAIL">AI 错误拒绝</option><option value="DISAGREEMENT">人工分歧待裁决</option><option value="INTERFACE_ERROR">接口失败</option><option value="PARSE_ERROR">评分格式错误</option><option value="CONTENT_INVALID">评分依据校验失败</option><option value="UNPAIRED">无法比较</option></select></label>
    <table class="cal-table"><thead><tr><th>样本／第几次</th><th>人工</th><th>AI</th><th>比较结果</th><th>证据</th></tr></thead><tbody><tr v-for="row in rows" :key="row.key"><td>{{row.sample_id.slice(0,8)}} / {{row.repetition}}</td><td>{{labelFor(row.human||row.reference_state)}}</td><td>{{labelFor(row.machine||row.execution_status)}}<small v-if="row.error" class="cal-row-error">{{labelFor(row.error)}}</small></td><td>{{labelFor(row.relation)}}</td><td><button class="text-button" @click="emit('inspect',row.sample_id)">查看原文 →</button></td></tr></tbody></table><p v-if="!rows.length" class="empty">此范围没有样本。</p>
  </section>
</template>
