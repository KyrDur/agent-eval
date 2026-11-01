export const pageNames={welcome:'首页',setup:'模型配置',knowledge:'资料准备',chat:'对话测试',define:'测试题',evaluate:'评测结果',improve:'试修改',compare:'前后比较',career:'项目整理',history:'历史实验',calibration:'评分校准',learning:'新手练习'}
export const methodNames={RERANK_TOGGLE:'资料重排',QUERY_REWRITE_TOGGLE:'问题改写',TOP_K_CHANGE:'返回资料数量',ANSWER_PROMPT_CHANGE:'回答提示词',KNOWLEDGE_UPDATE:'知识库更新'}
export const reasons={none:'未分类',busy:'仍在执行',precondition:'前置条件未满足',missing_input:'缺少必填内容',invalid_input:'内容格式不正确',unconfirmed:'尚未确认',credentials:'缺少模型凭据',connection:'模型未连接',knowledge:'缺少资料',index:'索引未就绪',unsaved:'修改未保存',configuration:'配置变化',already_complete:'已有结果',run_incomplete:'运行未完成',baseline:'缺少初测',authentication:'模型认证失败',rate_limit:'额度或请求限制',timeout:'请求超时',network:'网络连接失败',execution:'执行异常',service:'本站服务异常',unknown:'原因未采集'}
export const actionNames={
 'setup.save':'保存模型配置','setup.test':'测试模型连接','setup.tools':'验证工具能力','judge.save':'保存评分模型','judge.connect':'连接评分模型','judge.bind':'绑定评分模型',
 'knowledge.generate':'生成资料草稿','knowledge.regenerate':'重新生成资料','knowledge.save':'保存资料','knowledge.index':'准备资料索引',
 'tests.generate':'生成测试题','tests.save':'保存测试题','chat.send':'发送测试问题','chat.draft':'保存对话草稿',
 'run.baseline':'开始初测','run.retest':'开始复测','run.repeat':'重复运行','comparison.create':'生成前后比较',
 'change.propose':'保存修改方案','change.record':'记录修改','change.diagnose':'记录问题判断','change.apply':'应用修改','change.confirm':'确认修改','change.preview':'预览问题改写','change.rollback':'恢复原版',
 'trace.analyze':'分析运行轨迹','review.save':'保存人工复核','conclusion.save':'保存实验结论','career.evidence':'整理项目事实','career.confirm':'确认项目事实','career.preview':'预览项目材料','career.generate':'生成旧版材料','career.copy':'复制旧版材料','career.download':'下载旧版材料','career.fetch':'取得导出内容','career.edit':'保存材料编辑','career.regenerate':'重新生成材料段落','interview.save':'保存面试练习',
 'evidence.details':'查看原文依据','site.history':'打开历史实验','site.new':'创建新实验','site.sync':'同步实验状态','welcome.setup':'开始体验','welcome.practice':'开始免费练习'
}
export function actionName(action){if(actionNames[action])return actionNames[action];const parts=String(action||'').split('.');if(parts[0]==='site'&&parts[1]==='navigate')return '进入'+(pageNames[parts[2]]||'工作台');return ({career:'项目整理交互',welcome:'首页交互',learning:'练习交互',retrievalpage:'实验页面交互',result:'评测结果交互',change:'修改方案交互',site:'工作台交互'})[parts[0]]||'其他功能交互'}
export const format=n=>n===null||n===undefined?'—':Number(n).toLocaleString('zh-CN')
export const percent=r=>r?.value===null||r?.value===undefined?'—':(r.value*100).toFixed(1)+'%'
export function beijingDay(value=new Date()){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(value)}
export function timeLabel(value){if(!value)return '未采集';const d=new Date(value);return Number.isNaN(+d)?'未采集':d.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}
export function queryFor(filters){
 const q=new URLSearchParams({days:String(filters.days==='custom'?7:filters.days||7),source:filters.source||'live',include_excluded:filters.excluded?'1':'0'})
 if(filters.days==='custom'){
  const {since,until}=filters
  if(!/^\d{4}-\d{2}-\d{2}$/.test(since||'')||!/^\d{4}-\d{2}-\d{2}$/.test(until||''))throw new Error('请选择完整的开始和结束日期。')
  const span=(Date.parse(until+'T00:00:00+08:00')-Date.parse(since+'T00:00:00+08:00'))/86400000
  if(!Number.isInteger(span)||span<0||span>=90||until>beijingDay())throw new Error('请选择截至今天、最多 90 天的有效范围。')
  q.set('days',String(span+1));q.set('since',since);q.set('until',until)
 }
 return q.toString()
}
export function createReportStore({fetcher=globalThis.fetch,onChange=()=>{},timeoutMs=25000}={}){
 const state={data:null,status:'idle',loading:false,error:'',updatedAt:null,key:null}
 let generation=0,controller=null
 async function refresh(filters){
  let key;try{key=queryFor(filters)}catch(e){state.error=e.message;onChange(state);return}
  if(state.loading&&state.key===key)return
  const current=++generation;controller?.abort();controller=new AbortController();const activeController=controller
  if(state.key!==key){state.data=null;state.updatedAt=null}
  Object.assign(state,{key,loading:true,status:'loading',error:''});onChange(state)
  const timer=setTimeout(()=>activeController.abort(),timeoutMs)
  try{
   const response=await fetcher('/api/experiments/analytics/report?'+key,{cache:'no-store',credentials:'omit',signal:activeController.signal})
   if(!response.ok)throw new Error('统计读取通道暂时不可用。')
   const data=await response.json()
   if(data.product_status!=='READY'||data.product?.version!==1)throw new Error('产品分析汇总暂时不可用，不能以基础访问数据代替。')
   if(current!==generation)return
   Object.assign(state,{data,status:'ready',loading:false,error:'',updatedAt:new Date().toISOString()})
  }catch(e){if(current!==generation)return;Object.assign(state,{status:state.data?'stale':'error',loading:false,error:e.name==='AbortError'?'读取超时，将自动重试。':e.message})}
  finally{clearTimeout(timer);if(current===generation)onChange(state)}
 }
 return {state,refresh,stop(){generation++;controller?.abort()}}
}
export function csvContent(report){
 const p=report.product,rows=[['模块','指标','数量','分母','口径'],['范围',p.period.since+' 至 '+p.period.until,'','','北京时间；'+(report.include_excluded?'包含测试浏览器':'排除测试浏览器')]]
 if(p.traffic)for(const [key,label] of [['visitors','匿名访客'],['views','浏览量'],['visits','访问次数']])rows.push(['访问',label,p.traffic[key],'','采集事件'])
 for(const [key,label] of [['valid_baseline_users','首次观测有效初测使用者'],['full_loop_users','完整实验闭环使用者'],['full_loops','完整实验闭环'],['partial_loops','部分实验闭环']])rows.push(['业务核对',label,p.business[key],'','已封存的 RAG 实验；不回填埋点'])
 for(const r of p.traffic?.daily||[])rows.push(['每日',r.day,r.visitors,'','匿名访客'])
 for(const r of p.business.funnel.stages)rows.push(['实验漏斗',r.name,r.mature,p.business.funnel.mature,'进入后 7 天；已成熟实验'])
 for(const r of p.retention?.visit_cohorts||[])for(const c of r.cells)rows.push(['访问留存',r.date+' 第'+c.day+'天',c.state==='observing'?'观察中':c.numerator,c.denominator,'首次观测访问；精确自然日'])
 for(const r of p.business.methods)for(const k of ['saved','applied','retested','compared'])rows.push(['修改方式',methodNames[r.method]+' '+({saved:'保存',applied:'应用',retested:'有效复测',compared:'完整比较'})[k],r[k],'','按方案创建日期进入；进度截至读取时'])
 for(const r of p.operations)rows.push(['操作',actionName(r.action),r.success,r.submitted,'操作回执成功；不等于回答正确'])
 const escape=v=>'"'+String(v??'未采集').replace(/^[=+\-@]/,'\t$&').replaceAll('"','""')+'"'
 return '\ufeff'+rows.map(row=>row.map(escape).join(',')).join('\r\n')
}
