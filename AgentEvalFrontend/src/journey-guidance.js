// Display guidance derives only from saved state; it never creates a verdict or decision.
export const journey = [
  {id:'setup',label:'连接模型',goal:'选一个已开通的模型，试试能否连上。',
   steps:['选择你已开通的模型服务，填写对应 API Key，点击「保存模型会话」。','点击「测试连接」。出现连接成功后再继续；RAG 知识问答不要求测试工具能力。','聊天与 Judge 使用这里的远程模型；知识库的 MiniLM 在本地运行，不需要另一把 Key。'],
   tip:'连接成功只表示请求可用，不表示回答质量合格。Key 仅保存在后端内存，服务重启后需重新输入。'},
  {id:'knowledge',label:'准备评测规则',goal:'准备一份客服能查到的店铺资料。',
   steps:['第一次可使用示例资料，也可按预填的电商场景让 AI 生成模拟资料；不必从零编写售后政策。','核对上面的规则，点击「保存这些规则，准备出题」；AI 资料先勾选核对确认。保存和整理资料由系统完成。','准备完成后，点击「下一步：AI 生成测试题」。AI 会根据规则出题并填写预期回答，再进入第一次评测；首次使用保持默认参数即可。'],
   tip:'知识回答“政策是什么”，测试题检查“能不能找到、能不能答对”。补充知识与修改模型是不同变量；切换模型请另建初测。'},
  {id:'chat',label:'辅助：聊天找问题',goal:'先聊几句，遇到问题就留作测试题。',
   steps:['选择当前知识库或某次实验的版本，先核对模型连接与索引是否就绪。','问一个知识范围内的问题，展开「引用与检索依据」，核对回答引用的政策和条件。','遇到答错、缺少知识或值得保留的回答，点击「加入测试」，由你填写预期行为和相关知识，然后到测试页确认保存。'],
   tip:'当前是知识问答，不能实际查询订单或执行退款。Agent 自己的回答不能直接当标准答案；缺少资料时应明确说明。'},
  {id:'define',label:'AI 出题与核对',goal:'挑几道题，看看客服能不能答好。',
   steps:['点击「AI 生成测试草稿」，默认生成 8 道题及预期行为、原文依据。使用 Demo 知识时，也可以直接载入现成题目。','展开题目依据，对照资料核对即可，不必自己写问题或标准。题数、题型与模型可以使用默认设置。','首次出题勾选核对确认后，点击「确认并保存」，即可进入评测；已有题时先合并核对。手动修改与补题是可选操作。'],
   tip:'普通初测和复测只运行调试题；保留题在两版配置锁定后专门运行，结束后解封，已曝光题不能重新作为未见题。当前采用匿名工作区内的工作流隔离，开发者仍可访问本地文件。'},
  {id:'evaluate',label:'初测与读结果',goal:'跑完后，先挑一道答得不好的题看看。',
   steps:['首次评测用于记录当前表现。运行前核对模型、知识版本、测试范围和预计请求数量，第一次可以保持改写／重排关闭。','先看是否有执行无效（INVALID），再看正确知识有没有进入返回结果。只运行检索时，还没有检查最终回答。','可以点击单题的 AI 解读，在站内查看发生了什么、待验证原因和单变量建议。按下方推荐的一条题展开依据，核对正确知识、实际候选、最终回答和判定理由，再决定修改什么。'],
   tip:'检索找到正确知识不等于回答正确；回答判定来自检查模型（Judge），出现分歧时应人工复核并记录理由。'},
  {id:'improve',label:'只改一个变量',goal:'选一道有问题的题，试一个改法。',
   steps:['选定初测中的题，写下观察事实与根因假设；“为什么失败”在验证前仍是假设。','缺少正确资料先检查知识；问题表述不同可尝试查询改写；已有候选但排序靠后可考虑重排或 Top K。一次只选一个变量。','写明备选方案、选择理由与副作用，确认并记录，再点击「应用」，最后运行 Retest（同题复测）。'],
   tip:'改写／重排会增加远程请求。提高 Top K 会增加回答上下文。不要同时改题目、知识和模型，再把结果归因给其中一个。'},
  {id:'compare',label:'比较与作决定',goal:'看看哪些题变好了，哪些反而变差了。',
   steps:['先看控制条件是否可比较、题目是否完整匹配；有 INVALID 或部分匹配时，仅讨论有效范围。','逐题看改前与改后的相关知识排名，并单独查看回答变化，优先检查退化题。','填写保留、继续调整或采用初测版本的理由，保存结论；可回到对应版本聊天、独立重复运行，再整理材料。'],
   tip:'一次结果是观察，不自动证明整体变好或因果关系。重复运行检查稳定性，新的保留题检查是否只适应了调试题。'},
  {id:'career',label:'整理项目与求职材料',goal:'把这次做过的事整理下来。',
   steps:['点击「整理当前实验事实」，先检查选中的初测、复测与比较，只有初测时只能整理事实草稿。','补充实际背景、个人贡献、方案取舍与局限，确认属实后生成；未做过的部分不要补写为能力。','项目复盘说明问题与实验，简历草稿提炼贡献，面试讲稿与追问卡帮助解释证据；核对后导出 Markdown。'],
   tip:'材料是草稿，不是已验证业绩。后续复核或新实验不会自动改写旧材料，要显式整理新证据并重新生成。'},
]
// Common teaching examples, never inferred labels or statistics for a user's run.
export const evaluationIssueTypes = [
  {kind:'retrieval_miss',stage:'资料查找',title:'没找到正确资料',example:'问退货条件，返回的却只有发货说明。',inspect:'核对应该命中的资料、实际返回内容与索引版本。'},
  {kind:'low_rank',stage:'资料查找',title:'正确资料排序靠后',example:'正确规则排第 5 位，本次只返回前 3 条。',inspect:'查看候选排序和返回数量，再判断是否需要改写问题或调整排序。'},
  {kind:'rule_conflict',stage:'回答检查',title:'回答与规则冲突',example:'规则不支持定制商品无理由退货，客服却说可以退。',inspect:'对照规则原文、实际回答和判定理由。'},
  {kind:'missing_condition',stage:'回答检查',title:'漏掉适用条件',example:'只说可以保修，却漏掉“保修期内、非人为故障”。',inspect:'核对商品类型、期限及例外条件是否被保留。'},
  {kind:'fabrication',stage:'回答检查',title:'编造事实或操作承诺',example:'没有订单查询与退款工具，却声称“已为你退款”。',inspect:'检查回答中的事实或操作是否有资料与执行记录支持。'},
  {kind:'unsupported_conclusion',stage:'回答检查',title:'资料不足仍给出结论',example:'资料没有这项政策，客服却报出确定的时限或金额。',inspect:'核对资料范围，判断是否应说明资料不足或请用户进一步确认。'},
]
export function nextJourneyStep(session, rag) {
  if(session?.credential_status!=='PRESENT'||session?.text_connection_status!=='READY')return {id:'setup',label:'先连接自己的模型'}
  if(!rag?.index)return {id:'knowledge',label:'准备知识并建立索引'}
  if(!rag.evalSet)return {id:'define',label:'确认测试题与评测标准'}
  if(!rag.baseline)return {id:'evaluate',label:'检查条件，运行第一次评测'}
  if(rag.retest&&!rag.comparison)return {id:'compare',label:'查看如何生成前后比较'}
  if(rag.comparison)return {id:'career',label:'整理实验与项目材料'}
  return {id:'evaluate',label:'从一条待改善题开始分析'}
}
export function runBriefing({session,index,cases=[],config={},verifyAnswers=false}) {
  const count=cases.length
  const calls={rewrite:config.query_rewrite?count:0,rerank:config.rerank?count:0,
    agent:verifyAnswers?count:0,judge:verifyAnswers?count:0}
  const configuration=session?.configuration||{}
  return {count,debug:cases.filter(c=>(c.partition||'DEBUG')==='DEBUG').length,
    holdout:cases.filter(c=>c.partition==='HOLDOUT').length,
    answerModel:configuration.role_overrides?.general?.model||configuration.model||'尚未配置',
    judgeModel:configuration.judge_provider_configuration?.role_overrides?.judge?.model||configuration.judge_provider_configuration?.model||configuration.role_overrides?.judge?.model||configuration.model||'尚未配置',
    knowledgeVersion:index?.knowledge_version,embedding:index?.embedding_snapshot,
    calls,totalCalls:Object.values(calls).reduce((sum,n)=>sum+n,0),budget:configuration.max_calls}
}
export function resultStartingPoint(view) {
  const run=view?.run, rows=run?.case_results||[],answers=view?.effective_answer_results||[]
  if(!run||!['COMPLETE','PARTIAL','FAILED'].includes(run.status))return null
  const invalid=rows.find(c=>c.status!=='SUCCESS'||c.retrieval_status==='INVALID')
  if(invalid)return {kind:'INVALID',caseId:invalid.case_id,query:invalid.query,title:'先排除执行失败',
    explanation:'这题没有产生有效检索结果。先查看错误原因，处理模型、长度或连接问题，再重新运行；不要把 INVALID 当作答错。'}
  const answerInvalid=answers.find(a=>a.execution_status!=='SUCCESS'||a.judge_status==='FAILED'||a.evaluation_error)
  if(answerInvalid){const c=rows.find(c=>c.case_id===answerInvalid.case_id);return {kind:'INVALID',caseId:c?.case_id,query:c?.query,title:'先排除回答检查失败',explanation:'检索结果与回答检查分开记录。这题的 Agent 或 Judge 没有完成有效检查；先展开最终回答查看错误，不能把它当作质量失败。'}}
  if(!rows.length)return {kind:'INVALID',title:'先确认本次是否取得结果',explanation:'本次没有取得可分析的题目结果。请查看冻结 Run 证据、错误提示及模型连接，不能据此评价回答质量。'}
  const failed=answers.find(a=>a.execution_status==='SUCCESS'&&a.judge_status!=='FAILED'&&!a.evaluation_error&&a.final_status==='FAIL')
  const row=rows.find(c=>c.case_id===failed?.case_id)
  if(row)return {kind:'ANSWER',caseId:row.case_id,query:row.query,title:'先核对一条被判失败的回答',
    explanation:'展开这题的最终回答和判定理由，对照你写的标准及引用资料。Judge 可能误判；有分歧先记录人工复核，再提出修改。'}
  const labeled=rows.filter(c=>(c.relevant_document_ids?.length||c.relevant_chunk_ids?.length))
  const missing=labeled.find(c=>c.metrics?.relevant_rank==null)
  if(missing)return {kind:'MISSING',caseId:missing.case_id,query:missing.query,title:'先检查没有找到的正确知识',
    explanation:'正确知识没有进入本次候选池。先核对文档内容、标签和索引版本；若知识确实存在，再检查问题表述与检索方式。'}
  const outside=labeled.find(c=>c.metrics?.relevant_rank>(c.top_k||run.retrieval_config.top_k))
  if(outside)return {kind:'OUTSIDE_K',caseId:outside.case_id,query:outside.query,title:'先检查找到了却没返回的知识',
    explanation:`正确知识排第 ${outside.metrics.relevant_rank} 位，本次只返回前 ${outside.top_k||run.retrieval_config.top_k} 条。先看候选依据，再选择改写、重排或调整返回数量，一次只改一项。`}
  const lower=labeled.find(c=>c.metrics?.relevant_rank>1)
  if(lower)return {kind:'LOWER_RANK',caseId:lower.case_id,query:lower.query,title:'从一条排序靠后的题开始',
    explanation:`正确知识已经返回，但排第 ${lower.metrics.relevant_rank} 位。查看候选是否相关；${run.verify_answers?'再核对最终回答是否用了正确资料。':'本次没有检查最终回答，不能据此判断 Agent 已答对。'}`}
  if(!labeled.length)return {kind:'UNLABELED',title:'先补齐检索标签',explanation:'本次没有可用于检索计分的相关知识标签。回到测试页确认应该找到哪份资料；检索指标不可用不表示零分。'}
  return {kind:'CLEAR',title:'这批已标注题未发现检索待改善项',explanation:run.verify_answers?'继续检查回答、人工判定分歧和新的保留题，不要只凭这批题宣称整体变好。':'正确知识均排首位，但本次没有检查回答。可以另建开启回答验证的初测，再准备新的保留题。'}
}
