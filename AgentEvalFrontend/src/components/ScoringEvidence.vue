<script setup>
import {statusLabels} from '../calibration-presentation.js'
defineProps({result:Object})
const dimensions={faithfulness:'事实有没有依据',conditions:'条件有没有说全',relevance:'有没有答到点上',actionability:'下一步是否清楚'}
const scoreText=score=>({0:'不符合',1:'部分符合',2:'符合',INSUFFICIENT:'资料不足',NA:'本题不适用'})[score]||'待判断'
const yesNo=value=>({YES:'是',NO:'否',INSUFFICIENT:'暂时无法确认',NA:'本题不适用'})[value]||'暂时无法确认'
const errorText=value=>({JUDGMENT_SCHEMA_INVALID:'评分模型的返回格式不符合要求，请到运行日志查看原始返回。',JUDGMENT_PARSE_ERROR:'评分结果未能解析，请查看运行日志。'})[value]||value||'本题尚未完成评分。'

</script>
<template>
  <section v-if="result?.scoring_protocol" class="scoring-evidence" aria-label="政策证据评分">
    <h4>评分明细</h4>
    <p class="muted">每项满分 2 分：2 分符合，1 分部分符合，0 分不符合。</p>
    <details><summary>评分规则与校准记录</summary><p>{{result.scoring_protocol.calibration_status==='INITIAL_UNVALIDATED'?'当前使用初始评分规则，尚待人工校准。':statusLabels[result.scoring_protocol.calibration_status]}} · 本方案使用 0～2 分。</p>
    <details v-if="result.scoring_protocol.validation_scope"><summary>评分方案验证范围与采用依据</summary><p>研究样本 {{result.scoring_protocol.validation_scope.sample_count}} · 有效人工参照 {{result.scoring_protocol.validation_scope.valid_human_reference_count}} · 保留题 {{result.scoring_protocol.validation_scope.holdout_count??'尚未验证'}}</p><p>方法差异：{{result.scoring_protocol.validation_scope.changed_fields?.join('、')||'初始方案 / 未记录'}}</p><p>采用依据：{{result.scoring_protocol.validation_scope.adoption_reason||'初始方案尚无采用研究'}}</p><p>{{result.scoring_protocol.validation_scope.limitation||'尚未经过独立人工校准，不能当作已验证准确率。'}}</p></details>
    </details>
    <p v-if="result.evidence_evaluation?.status!=='SUCCESS'">{{errorText(result.evidence_evaluation?.error)}}</p>
    <template v-if="result.evidence_evaluation?.judgment">
      <p>问题是否解决：{{yesNo(result.evidence_evaluation.judgment.task_resolved)}} · 回答是否有据可依：{{yesNo(result.evidence_evaluation.judgment.faithful_to_available)}}</p>
      <details v-for="(value,key) in result.evidence_evaluation.judgment.dimensions" :key="key">
        <summary>{{dimensions[key]||key}} · {{scoreText(value.score)}}<small v-if="Number.isInteger(value.score)">（{{value.score}}/2）</small></summary>
        <p>{{value.reason}}</p>
        <blockquote v-for="(text,i) in value.answer_quotes" :key="'a'+i">回答：{{text}}</blockquote>
        <blockquote v-for="(citation,i) in value.citations" :key="'c'+i">{{citation.scope==='RETRIEVED'?'回答所见资料':'参考政策'}} · {{citation.evidence_id}}：{{citation.quote}}</blockquote>
      </details>
    </template>
  </section>
</template>
<style scoped>
.scoring-evidence{margin:16px 0;padding:16px;border:1px solid var(--border,#ddd);border-radius:12px;overflow-wrap:anywhere}details{margin:10px 0}summary{cursor:pointer}blockquote{margin:10px 0;padding:8px 12px;border-left:3px solid #ddd;white-space:pre-wrap}
</style>
