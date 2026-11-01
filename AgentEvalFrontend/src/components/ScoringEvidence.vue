<script setup>
import MarkdownContent from './MarkdownContent.vue'
import {computed} from 'vue'
import WorkspaceIcon from './WorkspaceIcon.vue'
import {retrievalCitation,retrievalCitationSummary} from '../scoring-citations.js'
import {readableScoringReason} from '../scoring-language.js'
const props=defineProps({result:Object,retrieval:Object,topK:Number,documents:{type:Array,default:()=>[]}})
const retrievalSummary=computed(()=>retrievalCitationSummary(props.retrieval,props.topK))
const sourceCitations=items=>(items||[]).map(citation=>({...citation,source:retrievalCitation(citation,props.retrieval,props.documents,props.topK)}))
const dimensions={faithfulness:'事实有没有依据',conditions:'条件有没有说全',relevance:'有没有答到点上',actionability:'下一步是否清楚'}
const scoreText=score=>({0:'不符合',1:'部分符合',2:'符合',INSUFFICIENT:'资料不足',NA:'本题不适用'})[score]||'待判断'
const yesNo=value=>({YES:'是',NO:'否',INSUFFICIENT:'暂时无法确认',NA:'本题不适用'})[value]||'暂时无法确认'
const errorText=value=>({JUDGMENT_SCHEMA_INVALID:'评分模型的返回格式不符合要求，请到运行日志查看原始返回。',JUDGMENT_PARSE_ERROR:'评分结果未能解析，请查看运行日志。'})[value]||value||'本题尚未完成评分。'

</script>
<template>
  <section v-if="result?.scoring_protocol" class="scoring-evidence" aria-label="政策证据评分">
    <h4>评分明细</h4>
    <p v-if="result.evidence_evaluation?.status!=='SUCCESS'">{{errorText(result.evidence_evaluation?.error)}}</p>
    <template v-if="result.evidence_evaluation?.judgment">
      <p>问题是否解决：{{yesNo(result.evidence_evaluation.judgment.task_resolved)}} · 回答是否有据可依：{{yesNo(result.evidence_evaluation.judgment.faithful_to_available)}}</p>
      <details v-for="(value,key) in result.evidence_evaluation.judgment.dimensions" :key="key">
        <summary>{{dimensions[key]||key}} · {{scoreText(value.score)}}<small v-if="Number.isInteger(value.score)">（{{value.score}}/2）</small></summary>
        <p class="dimension-reason"><span>评分理由</span>{{readableScoringReason(value.reason,result.evidence_evaluation,key)}}</p>
        <details v-if="value.answer_quotes?.length||value.citations?.length" class="quoted-passages"><summary>查看引用片段</summary>
          <div class="quote-list">
            <figure v-for="(text,i) in value.answer_quotes" :key="'a'+i" class="evidence-quote answer-quote">
              <figcaption><WorkspaceIcon name="chat" :size="17" /><strong>Agent 的回答</strong><small v-if="value.answer_quotes.length>1">引用 {{i+1}}</small></figcaption>
              <MarkdownContent class="quote-content" :source="text" />
            </figure>
            <p v-if="retrievalSummary&&value.citations?.some(c=>c.scope==='RETRIEVED')" class="retrieval-overview">{{retrievalSummary}}</p>
            <figure v-for="(citation,i) in sourceCitations(value.citations)" :key="'c'+i" :class="['evidence-quote',citation.scope==='REFERENCE'?'reference-quote':'retrieved-quote']">
              <figcaption><WorkspaceIcon name="document" :size="17" /><strong>{{citation.scope==='REFERENCE'?'评分用的参考资料':'当时检索到的资料'}}</strong><small v-if="citation.source.label" class="retrieval-rank">{{citation.source.label}}</small></figcaption>
              <p v-if="citation.source.title" class="quote-source-title">{{citation.source.title}}</p>
              <MarkdownContent class="quote-content" :source="citation.quote" />
            </figure>
          </div>
        </details>
      </details>
    </template>
  </section>
</template>
<style scoped>
.scoring-evidence{margin:16px 0;padding:16px;border:1px solid var(--border,#ddd);border-radius:12px;overflow-wrap:anywhere}details{margin:10px 0}summary{cursor:pointer}
.dimension-reason{margin:16px 0;line-height:1.85}.dimension-reason>span{display:block;margin-bottom:5px;color:var(--muted);font-size:12px}
.retrieval-overview{margin:0;color:var(--muted);font-size:12px;line-height:1.8}.evidence-quote .quote-source-title{margin:0 0 8px;color:var(--quote-label);font-size:13px;font-weight:600}.evidence-quote figcaption .retrieval-rank{padding:3px 8px;border:1px solid var(--quote-border);border-radius:5px;background:#ffffff80;white-space:nowrap}
.quote-list{display:grid;gap:16px;margin-top:16px}.evidence-quote{--quote-border:#cbddec;--quote-accent:#6e95b9;--quote-label:#365d7d;margin:0;padding:16px 18px;border:1px solid var(--quote-border);border-left:4px solid var(--quote-accent);border-radius:10px;background:#edf4fb;min-width:0}.retrieved-quote{--quote-border:#d5dfca;--quote-accent:#879b70;--quote-label:#50633f;background:#f0f4e9}.reference-quote{--quote-border:#e6dbc4;--quote-accent:#b19a68;--quote-label:#78623b;background:#faf4e8}
.evidence-quote figcaption{display:flex;align-items:center;flex-wrap:wrap;gap:8px;color:var(--quote-label);padding-bottom:12px;margin-bottom:12px;border-bottom:1px solid var(--quote-border);font-size:13px}.evidence-quote figcaption>svg{flex-shrink:0}.evidence-quote figcaption strong{font-weight:600}.evidence-quote figcaption small{margin-left:auto;font-size:11px;color:var(--quote-label)}.evidence-quote .quote-content{margin:0;padding:0;border:0;background:none;color:var(--color-text,#292d25);font-size:14px;line-height:1.9;overflow-wrap:anywhere}
@media(max-width:600px){.evidence-quote{padding:13px 14px}.quote-list{gap:12px}.evidence-quote figcaption{padding-bottom:10px;margin-bottom:10px}}
</style>
