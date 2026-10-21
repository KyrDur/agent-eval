<script setup>
const props=defineProps({caseRecord:{type:Object,required:true}})
const emit=defineEmits(['change'])
function setContext(key,value){props.caseRecord.evidence_context={...props.caseRecord.evidence_context,[key]:value||null};emit('change')}
function setRule(key,value){props.caseRecord.scenario_rules={schema_version:'SCENARIO_RULES_V1',...props.caseRecord.scenario_rules,[key]:value};emit('change')}
function setComplete(value){props.caseRecord.reference_complete=value===''?null:value==='true';emit('change')}
function setOrder(value){setContext('object_ids',{...props.caseRecord.evidence_context?.object_ids,order_id:value||null})}
const lines=value=>value.split('\n').map(s=>s.trim()).filter(Boolean)
</script>
<template>
 <details class="advanced scenario-rule-editor"><summary>进阶：来源、业务规则与证据边界</summary>
  <p class="muted">这些声明随题目版本冻结。历史缺失显示未知；有文档不代表已覆盖全部必要政策。合理澄清或转交可以符合预期，仍需单独判断任务是否完成。</p>
  <label>评测场景<select :value="caseRecord.scenario_rules?.template_id||'POLICY_RAG'" @change="setRule('template_id',$event.target.value)"><option value="POLICY_RAG">政策知识问答：需要核验完整参考</option><option value="MISSING_KNOWLEDGE">知识缺失：检查诚实兜底</option><option value="CLARIFICATION">信息不足：检查合理澄清</option></select></label>
  <label class="check"><input type="checkbox" :checked="!!caseRecord.evidence_context?.used_for_tuning" @change="setContext('used_for_tuning',$event.target.checked)" />这道题曾用于修改或选择方案（不能再当作独立保留题）</label>
  <label>送入回答与评分的历史<select :value="caseRecord.evidence_context?.history_mode||'RECENT_FOUR'" @change="setContext('history_mode',$event.target.value)"><option value="RECENT_FOUR">最近 4 条消息（原历史继续保留）</option><option value="FULL">完整提供的历史</option></select></label>
  <label>必须包含的参考政策 ID（每行一项）<textarea :value="(caseRecord.evidence_context?.required_reference_ids||[]).join('\n')" @input="setContext('required_reference_ids',lines($event.target.value))" /></label>
  <label>必须提供的证据 ID（每行一项）<textarea :value="(caseRecord.evidence_context?.required_evidence_ids||[]).join('\n')" @input="setContext('required_evidence_ids',lines($event.target.value))" /></label>
  <div class="form-row"><label>必要前提<select multiple :value="caseRecord.evidence_context?.required_evidence||[]" @change="setContext('required_evidence',Array.from($event.target.selectedOptions,o=>o.value))"><option value="reference_complete">完整参考政策</option><option value="turn_id">明确当前轮次</option><option value="object_ids">明确业务对象</option><option value="policy_time">明确政策版本与时效</option><option value="question_timezone">提问时区</option></select></label><label>本题输入字符预算<input type="number" min="1" max="500000" :value="caseRecord.evidence_context?.max_input_characters||100000" @input="setContext('max_input_characters',Number($event.target.value))" /></label></div>
  <div class="form-row"><label>题目来源类型<select :value="caseRecord.evidence_context?.source_type||'UNKNOWN'" @change="setContext('source_type',$event.target.value)"><option value="UNKNOWN">未知或尚未核对</option><option value="CONSTRUCTED">人工构造 / 教学示例</option><option value="AI_GENERATED">AI 生成题</option><option value="ACTUAL">已保存的实际交互</option></select></label>
   <label>参考政策是否足够<select :value="caseRecord.reference_complete==null?'':String(caseRecord.reference_complete)" @change="setComplete($event.target.value)"><option value="">未知，尚未确认</option><option value="true">已核对覆盖本题所需政策</option><option value="false">已知缺少必要政策</option></select></label></div>
  <p class="muted">真实 API 回答可以对应构造题；实际交互也不自动表示来自生产流量。来源与参考完整性分别声明。</p>
  <label>参考完整性的核对说明<textarea :value="caseRecord.reference_completeness?.reason||''" rows="2" @input="caseRecord.reference_completeness={...caseRecord.reference_completeness,reason:$event.target.value};emit('change')" /></label>
  <div class="form-row"><label>会话 ID（如已知）<input :value="caseRecord.evidence_context?.conversation_id||''" @input="setContext('conversation_id',$event.target.value)" /></label><label>当前轮次 ID（如已知）<input :value="caseRecord.evidence_context?.turn_id||''" @input="setContext('turn_id',$event.target.value)" /></label><label>当前订单 ID（如已知）<input :value="caseRecord.evidence_context?.object_ids?.order_id||''" @input="setOrder($event.target.value)" /></label></div>
  <div class="form-row"><label>原提问时间（带偏移的 ISO 时间）<input :value="caseRecord.evidence_context?.question_time||''" placeholder="未知可留空" @input="setContext('question_time',$event.target.value)" /></label><label>原时区<input :value="caseRecord.evidence_context?.question_timezone||''" placeholder="未知可留空" @input="setContext('question_timezone',$event.target.value)" /></label></div>
  <label>政策来源与版本<input :value="caseRecord.scenario_rules?.policy_source||''" @input="setRule('policy_source',$event.target.value)" /></label>
  <label>适用范围<textarea :value="caseRecord.scenario_rules?.applicability||''" rows="2" @input="setRule('applicability',$event.target.value)" /></label>
  <div class="form-row"><label>政策开始适用时间<input :value="caseRecord.scenario_rules?.valid_from||''" placeholder="未知可留空" @input="setRule('valid_from',$event.target.value)" /></label><label>政策停止适用时间<input :value="caseRecord.scenario_rules?.valid_until||''" placeholder="未知可留空" @input="setRule('valid_until',$event.target.value)" /></label></div>
  <label>本轮预期行为<select :value="caseRecord.scenario_rules?.expected_behavior||'UNKNOWN'" @change="setRule('expected_behavior',$event.target.value)"><option value="UNKNOWN">尚未明确</option><option value="ANSWER">根据有效政策回答</option><option value="CLARIFY">补充信息后再判断</option><option value="HANDOFF">说明限制并转交</option><option value="REFUSE">合理拒答</option></select></label>
  <div class="form-row"><label>必要条件（每行一项）<textarea :value="(caseRecord.scenario_rules?.necessary_conditions||[]).join('\n')" rows="2" @input="setRule('necessary_conditions',lines($event.target.value))" /></label><label>关键错误（每行一项）<textarea :value="(caseRecord.scenario_rules?.critical_errors||[]).join('\n')" rows="2" @input="setRule('critical_errors',lines($event.target.value))" /></label></div>
  <label>允许的兜底<textarea :value="caseRecord.scenario_rules?.allowed_fallbacks||''" rows="2" @input="setRule('allowed_fallbacks',$event.target.value)" /></label>
  <div class="form-row"><label>正例<textarea :value="caseRecord.scenario_rules?.positive_example||''" rows="2" @input="setRule('positive_example',$event.target.value)" /></label><label>反例<textarea :value="caseRecord.scenario_rules?.negative_example||''" rows="2" @input="setRule('negative_example',$event.target.value)" /></label></div>
  <div class="form-row"><label>标准确认人<input :value="caseRecord.scenario_rules?.confirmed_by||''" @input="setRule('confirmed_by',$event.target.value)" /></label><label>本次规则变更理由<input :value="caseRecord.scenario_rules?.change_reason||''" @input="setRule('change_reason',$event.target.value)" /></label></div>
  <p class="note">规则含义变化需要新版本及人工复核；不能据此直接声称 Agent 变好。字段声明仍需维护者确认。</p>
 </details>
</template>
<style scoped>
.scenario-rule-editor{margin-block:16px;overflow-wrap:anywhere}.scenario-rule-editor .form-row{flex-wrap:wrap}.scenario-rule-editor label{min-width:0}
</style>
