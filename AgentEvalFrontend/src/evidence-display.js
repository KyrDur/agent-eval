// Presentation only: never rewrites stored states or infers a pass from missing data.
export const evidenceStates={FULL:'已包含已核对要点',PARTIAL:'仅包含部分要点',MISSING:'未包含必要原文',UNREVIEWED:'政策适用性待核对',CONFLICT:'来源或版本待核对',OUT_OF_SCOPE:'本题范围外',NOT_CHECKED:'尚未检查',UNKNOWN:'尚不确定',REFERENCE_COMPLETENESS_UNCONFIRMED:'参考答案是否完整，还未核对'}
export const evidenceState=value=>evidenceStates[value]||(value?'旧记录未提供说明':'本次未记录')
export function evidenceCount(stage){
 if(stage?.required_count==null)return ''
 if(stage.status==='UNREVIEWED'||stage.review_status!=='CONFIRMED')return `检测到 ${stage.included_count??0} 条文本匹配，政策适用性待核对`
 return `${stage.included_count??0} / ${stage.required_count} 条已核对要点`
}
