import {analytics} from './analytics.js'
import {operationFor} from './analytics-operations.js'
const errors = {
  SCORING_PROTOCOL_CHANGED:['评分协议已更新','请重新预览并创建新协议任务。原尝试和报告保留。'],
  SCORING_SCOPE_INVALID:['评分范围不正确','请选择本次已执行的题目。'],
  SOURCE_HASH_MISMATCH:['封存内容校验失败','评分已停止，请核对本次运行记录。'],
  ANSWER_NOT_ACQUIRED:['本题没有完整回答','请先查看原运行的回答步骤。'],
  SCORING_PROFILE_REQUIRED:['原运行缺少可恢复的评分协议','请保留历史记录，在证据评分流程建立新的运行。'],
  FORMAT_MODE_UNSUPPORTED:['模型服务不支持所选输出约束','请明确选择服务支持的模式，系统不会自动切换协议。'],
  SCORING_ENGINE_CHANGED_NEW_PROTOCOL_REQUIRED:['评分约束已更新','历史方法与结果继续保留；请建立新评分方法并重新校准，再采用到当前实验。'],
  HOLDOUT_USED_FOR_TUNING:['这道题已参与选方案','请改为调试题，并使用新的保留题验证。'],
  REVIEW_EVIDENCE_REQUIRED:['需要先补齐判断依据','缺少必要政策或有效执行时不能直接改为通过，请建立取证修订批次后重评。'],
  PREVIEW_CHANGED_REVIEW_AGAIN:['输入或规则已变化','请重新预览并核对清洗和范围。'],
  MAX_ATTEMPTS_REACHED:['已达到本域重试上限','请检查已有失败证据或建立明确的新运行。'],
  INPUT_BUDGET_EXCEEDED:['本次输入超过预算','请缩小必要历史、参考资料或模型输出预留，或核对模型上下文配置。关键内容不会静默截断。'],
  DOMAIN_BUSY:['该业务域正在运行','可查看已有作业；其他业务域仍可运行。'],
  SCOPE_CONFIRMATION_REQUIRED:['先确认样本范围','请逐条核对保留、排除和待确认样本并填写依据。'],
  CSV_EXPORT_RUN_NOT_FINISHED:['评测还在运行','运行结束后可以导出；部分完成或失败的结果也会保留。'],
  CSV_EXPORT_TOO_LARGE:['文件超过 32 MiB','本次没有截取或下载部分结果。请拆分题集后导出，已有记录仍然保留。'],
  CSV_EXPORT_UNAVAILABLE:['暂时无法导出','请重新读取这次结果后重试，导出不会重新运行评测。'],
  CSV_DOWNLOAD_FAILED:['下载未完成','请重试下载，已有评测结果不受影响。'],
  LIMITED_DECISION_SCOPE_REQUIRED:['需要限定结论范围','当前有覆盖、范围或判定有效性限制。请明确选择仅限已观察可比子集，或记录继续调整/采用原版。'],
  ISSUE_PLAN_REQUIRED:['缺少预先验收条件','修改前请声明目标错误、成功条件、退化风险和验证题。'],
  ISSUE_ACCEPTANCE_REQUIRED:['尚不满足修复条件','请核对目标错误是否消除、退化检查和结论适用范围。'],
  LEARNING_STAGE_INVALID:['当前步骤尚未就绪','请按页面完成初判、预测、回放和采用决定，再进入新题验证。'],
  LEARNING_EVIDENCE_INVALID:['引用与原文不符','请选择本题证据并复制其中的原文片段。'],
  ANSWER_QUOTE_INVALID: ['回答引用与原文不符', '请点选冻结回答中的原文片段，不要自行改写。旧版机评失败会保留记录。'],
  FRAGMENT_SCHEMA_INVALID: ['片段评分格式不正确', '新版评分应返回片段编号。请保留本次失败，再调整或重试评分方法。'],
  FRAGMENT_ID_DUPLICATED: ['片段重复引用', '同一个维度内无需重复选择相同片段。'],
  ISSUE_PLAN_REQUIRED: ['先声明修复验收条件', '修改前填写成功条件、目标错误、潜在退化、验证范围及题目 ID。'],
  ISSUE_PLAN_ALREADY_FROZEN: ['验收条件已固定', '只能在记录具体修改时声明本轮验收条件，不能看完复测再改条件。'],
  ISSUE_ACCEPTANCE_REQUIRED: ['修复验收依据不足', '有效评分仍需明确目标错误消除、退化检查、结论范围和本人判断。评分由 PASS 改为 FAIL 也可能修复误判。'],
  ISSUE_VERIFICATION_KIND_INVALID: ['复测类型不对应问题', '数据修复重评固定回答，Judge 修改进入校准，评分标准修订建立新研究，Agent 修改关联新的 Retest。'],
  ISSUE_VERIFICATION_VERSION_INVALID: ['复测条件或版本不同', '核对固定回答、样本、评分标准、Judge 配置与派生输入的父版本引用。不同尺度不能当作同口径改善。'],
  ISSUE_CHANGE_NOT_OBSERVED: ['尚未找到实际改动', '关联的版本需保留实际差异；只重新运行相同版本不能证明本次修改修复了问题。'],
  ISSUE_UNSEEN_SCOPE_INVALID: ['新题验证依据不足', '新题需有有效评分且未出现在基线题目中；已使用案例不能计作未见验证。'],
  ISSUE_PRIORITY_SCOPE_REQUIRED: ['同类数量缺少范围', '观察数量需同时提供来源与分母，不能按构造题频次预测线上影响。'],
  ISSUE_INPUT_INVALID: ['问题记录未填写完整', '标题、负责人和进展说明不能只包含空白。'],
  FRAGMENT_ID_INVALID: ['引用了不存在的片段', '评分方法引用的编号不属于本题冻结输入，请保留失败记录后调整评分说明。'],
  FRAGMENT_SCOPE_INVALID: ['引用范围混用', '回答引用须选回答片段，政策依据须选检索或参考政策片段。'],
  ISSUE_EVENT_CONFLICT: ['问题记录已有新进展', '请重新读取问题记录，再追加本次进展，避免覆盖其他人的更新。'],
  ISSUE_TRANSITION_INVALID: ['进展顺序不符合要求', '先记录复现、具体修改，再关联新运行复测。尚未解决也可以如实保存。'],
  ISSUE_VERIFICATION_REQUIRED: ['缺少复测证据', '复测需关联同一道题的新运行并记录结果；只有支持改善的复测才能记录修复结论。'],
  ISSUE_VERIFICATION_INVALID: ['复测运行不匹配', '请选择同一数据集、同一道题的新运行。执行或评分失败不能记作已改善。'],
  ISSUE_CHANGE_REQUIRED: ['缺少修改内容', '请说明实际修改了哪个环节。'],
  ISSUE_SCOPE_INVALID: ['问题与运行不匹配', '请使用当前样本集中的运行和题目。'],
  CROSS_PARTITION_FAMILY: ['同源样本跨集', '相同问题、近重复、回答变体或同源模板必须放在同一用途分组。请检查 group_id、template_id 和问题文本。'],
  HOLDOUT_ALREADY_EXPOSED: ['保留集已曝光', '这些保留内容已用于最终验证，请增加新的保留样本。'],
  HOLDOUT_LOCKED: ['保留机评尚未解封', '请先锁定候选并执行专门的最终验证操作。'],
  CANDIDATE_LOCKED: ['候选及人工参照已锁定', '本轮协议和标注已冻结。继续调整请建立新的研究样本集。'],
  CANDIDATE_ALREADY_LOCKED: ['本轮已锁定候选', '请读取已有保留验证记录，重复提交不会建立新验证。'],
  REFERENCE_LOCKED: ['人工参照已冻结', '最终验证已锁定，不能修改本轮标注和裁决。'],
  REQUEST_BUDGET_INVALID: ['请求预算不足或超限', '请核对样本数、重复次数、总预算和 Provider 会话调用上限。'],
  PROVIDER_CONFIG_CHANGED: ['模型配置与协议不一致', '请选择与冻结协议完全相同的 Provider 配置，或新建并比较新协议。'],
  ANNOTATION_REQUIRED_BEFORE_RESULTS: ['样本尚未提交标注', '此查看者须先提交相关样本的标注，才能查看完整机评对照。AI 和 Codex 标注仍会保留其真实来源。'],
  CALIBRATION_RUN_REQUIRED: ['缺少校准集实验', '基线与候选协议都须先在校准集运行，之后才能锁定最终对照。'],
  HOLDOUT_EXAMPLE_PROHIBITED: ['保留样本不能作示例', '请选择校准集中的边界样本。'],
  EXAMPLE_REQUIRES_HUMAN_REFERENCE: ['示例缺少独立人工参照', '先完成该校准样本的独立人工标注或裁决。'],
  RUBRIC_CHANGED_NEW_STUDY_REQUIRED: ['评分尺度发生变化', '请重新标注相关样本并建立新研究版本，不能沿用旧尺度声称准确率提高。'],
  INDEPENDENT_HUMAN_REFERENCE_REQUIRED: ['研究参照仍待完成', '采用候选需要相关样本的真实独立人工参照与最终验证。可以保存继续调整或保留原版的结论。'],
  ANSWER_QUOTE_REQUIRED: ['缺少回答原文', '每个数值评分维度都需圈定实际回答原文。'],
  RETRIEVED_CITATION_REQUIRED: ['缺少检索依据', '事实与依据维度须引用回答当时所见的检索片段。'],
  REFERENCE_CITATION_REQUIRED: ['缺少参考政策依据', '条件覆盖维度须引用完整参考政策。'],
  INSUFFICIENT_ITEMS_REQUIRED: ['缺少证据不足说明', '选择证据不足时，请填写具体不足项。'],
  EVIDENCE_QUOTE_INVALID: ['证据引用不匹配', '引用 ID 和文字须来自所选范围的冻结内容。'],
  CALIBRATION_INPUT_TOO_LARGE: ['样本依据过多', '单样本双层证据最多 50 万字符；请整理有效政策范围，系统不会静默截断。'],
  IDEMPOTENCY_CONFLICT: ['重复请求参数不同', '原请求 ID 已绑定冻结参数，请先同步状态。'],
  AI_REQUEST_BUSY: ['AI 正在处理这次请求', '请等待当前生成完成，已有草稿保留。'],
  CHAT_SOURCE_REQUIRED: ['请选择评测记录', '问答需要绑定本次运行或前后比较。'],
  CHAT_RUN_NOT_FINISHED: ['评测还没结束', '运行结束后再询问这次结果。'],
  CHAT_CASE_NOT_IN_RUN: ['这道题未在本次运行', '请选择本次已运行的题目，未运行的保留题不会发送给 AI。'],
  CHAT_CONTEXT_MISMATCH: ['问答范围已变化', '请在当前运行或题目的问答中重新提问。'],
  EVALUATION_CHAT_LIMIT_REACHED: ['本段问答已达 20 轮', '请点击“开始新一段问答”。原问答记录仍然保留。'],
  AI_OUTPUT_INVALID: ['生成内容未通过校验', '返回内容、知识 ID 或原文引用不符合要求。已有草稿保留，可以明确重试；重试会增加请求。'],
  AI_INPUT_TOO_LARGE: ['本次资料过多', '请缩小知识或单题轨迹范围后再生成，系统不会静默截断依据。'],
  EMBEDDING_MODEL_UNAVAILABLE: ['本地语义模型不可用', '请检查首次模型下载的网络、缓存文件和运行依赖；系统不会自动改用词汇检索。'],
  EMBEDDING_INPUT_TOO_LONG: ['内容超过语义模型长度限制', '每段最多 256 Token（含特殊标记）。请缩短问题，或减小知识切分长度后重新建索引；系统不会静默截断。'],
  CHAT_CONFIGURATION_CHANGED: ['对话配置已变化', '请开始新对话，使用当前知识版本与模型配置。'],
  CONVERSATION_BUSY: ['这段对话正在回答', '请等待当前回答完成后再发送。'],
  CONVERSATION_LIMIT_REACHED: ['本段对话已达到 30 次', '请开始新对话。历史记录仍保留。'],
  WORKSPACE_UNAVAILABLE: ['工作区身份已失效', '请刷新页面建立新的独立工作区。旧记录不会自动转入新工作区。'],
  WORKSPACE_CAPACITY_REACHED: ['服务暂时繁忙', '当前工作区容量已满，请稍后再试。'],
  WORKSPACE_BUSY: ['实验服务暂时繁忙', '服务器同时运行的实验已达到上限，请稍后重试。'],
  WORKSPACE_ORIGIN_REJECTED: ['请求来源不受支持', '请从本站页面操作。'],
  PUBLIC_PROVIDER_ENDPOINT_NOT_ALLOWED: ['此模型地址暂不支持公开访问', '公开站点仅允许已配置的模型服务域名和 HTTPS。可使用 DeepSeek、百炼、Kimi、OpenAI、Claude、硅基流动或智谱官方地址。'],
  NARRATIVE_VALIDATION_FAILED: ['材料校验未通过', '请检查配置冲突、未验证业绩或补充判断。未通过的结果不会保存为正式材料。'],
  AUTH_FAILED: ['模型认证失败', '请检查 API Key，并重新配置会话。'],
  MODEL_NOT_FOUND: ['模型不存在', '请检查模型名称及 Base URL。'],
  RATE_LIMITED: ['模型请求受限', '请稍后重试，或检查服务额度。'],
  TIMEOUT: ['模型请求超时', '请稍后重试，或在高级设置中调整超时。'],
  NETWORK_ERROR: ['模型网络连接失败', '请检查模型服务地址与网络。'],
  INVALID_RESPONSE: ['模型响应无法用于评测', '返回格式不符合本次请求协议。'],
  PROVIDER_ERROR: ['模型服务异常', '请检查兼容服务的参数支持，或稍后重试。'],
  CALL_BUDGET_EXCEEDED: ['请求预算耗尽', '请检查本次调用预算；已有失败不会变成有效分数。'],
  HOLDOUT_GROUP_REVIEW_REQUIRED:['请核对保留题分组','每道题填写 group_id，并确认调试题与保留题没有同源泄漏。'],
  CROSS_PARTITION_FAMILY:['调试与保留题存在重叠','同题改写、同源模板或明显相似题必须放入同一组和用途。'],
  HOLDOUT_ALREADY_LOCKED_OR_EXPOSED:['这组保留题已锁定或使用','请使用未参与调试、未解封的新题开展下一次独立验证。'],
  HOLDOUT_ALREADY_EXPOSED:['这组题已有公开结果','不能再作为新的独立保留题，请准备新题。'],
  HOLDOUT_SPLIT_NOT_CONFIRMED:['保留题分组尚未确认','重新保存测试题，核对同源分组并确认拆分。'],
  IMPLEMENTATION_CHANGED_CREATE_BASELINE:['运行实现已更新','新建 Baseline 和 Retest 后再锁定独立验证，历史记录仍保留。'],
  SCORING_PROFILE_MODEL_MISMATCH:['模型与已验证方案不一致','使用该评分方案验证时的 Judge 配置，或建立新的校准研究。'],
  SCORING_PROFILE_NOT_VALIDATED:['评分方案尚未完成验证','请完成独立人工参照与保留验证后，再采用该方案。'],
  ADOPTION_REQUIRES_COMPLETE_EVALUATION:['验证范围仍有无效判定','核对未判定、执行失败与结果 ID；可保存不采用或继续观察的报告。'],
  HOLDOUT_VALIDATION_ALREADY_STARTED:['此验证已经开始','请读取已保存结果，不会自动重复模型请求。'],
  HOLDOUT_REQUEST_BUDGET_TOO_SMALL:['保留验证预算不足','提高总请求上限，或缩小下一套独立验证题。'],
  CREDENTIAL_UNAVAILABLE: ['模型凭据需要重新输入', '后端重启或删除会话后，Key 不会恢复。'],
  CONNECTION_NOT_VERIFIED: ['请先测试模型连接', '文本连接成功后才能开始评测。'],
  TEXT_CONNECTION_NOT_READY: ['请先测试模型连接', '连接成功后才能测试工具能力。'],
  TOOL_CALL_UNSUPPORTED: ['模型不支持工具调用', '该模型可以普通对话，但当前无法运行客服评测。'],
}

export function describeError(code, status = 0) {
  if (errors[code]) return { title: errors[code][0], message: errors[code][1] }
  if (status === 409) return { title: '操作条件尚未满足', message: '请同步后端状态，检查确认、版本、修改或复核条件。' }
  if (status === 422) return { title: '填写内容需要检查', message: '请检查必填项、规则格式与模型参数。' }
  if (status === 404) return { title: '记录无法找到', message: '请检查后端数据目录，或从历史实验重新打开。' }
  if (status === 503) return { title: '实验后端暂不可用', message: '请稍后点击“同步状态”读取已保存进度，避免重复开始评测。' }
  if (status === 502 || status === 504) return { title: '服务暂时无法响应', message: '任务可能仍在执行，请点击“同步状态”读取已保存进度。' }
  return { title: '无法连接实验 API', message: '连接暂时中断，请点击“同步状态”读取已保存结果，避免重复开始评测。' }
}
export class ApiError extends Error {
  constructor(code, status) {
    const safe = describeError(code, status)
    super(safe.message)
    this.title = safe.title
    this.status = status
    // Never retain/echo the server body, request body, URL, or arbitrary exception text.
    this.code = Object.hasOwn(errors, code) ? code : 'API_ERROR'
  }
}
export function createApi(fetcher = globalThis.fetch) {
  async function request(path, body, meta) {
    const specification=operationFor(path,body,meta)
    const operation=specification?analytics.begin(specification):null
    let response
    try {
      response = await fetcher('/api/experiments' + path, {
        method: body === undefined ? 'GET' : 'POST',
        headers: { 'Content-Type': 'application/json',...operation?.headers },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        cache: 'no-store',
      })
    } catch { analytics.end(operation,true);throw new ApiError(null, 0) }
    let data
    try { data = await response.json() } catch { analytics.end(operation,false,true);throw new ApiError(null, response.status) }
    analytics.end(operation,false,!response.ok || ['FAILED','AUTH_FAILED','PARTIAL'].includes(data?.status))
    if (!response.ok) throw new ApiError(typeof data.detail === 'string' ? data.detail : null, response.status)
    return data
  }
  return {
    get: (path, meta = {}) => request(path,undefined,meta),
    post: (path, body = {}, meta = {}) => request(path, body, meta),
    async download(path) {
      let response
      try { response=await fetcher('/api/experiments'+path,{headers:{Accept:'text/csv'},cache:'no-store'}) }
      catch { throw new ApiError(null,0) }
      if(!response.ok){let data;try{data=await response.json()}catch{};throw new ApiError(typeof data?.detail==='string'?data.detail:null,response.status)}
      if(!response.headers.get('Content-Type')?.toLowerCase().startsWith('text/csv'))throw new ApiError('CSV_DOWNLOAD_FAILED',response.status)
      let blob,filename='evaluation.csv'
      try {
        blob=await response.blob()
        const encoded=response.headers.get('Content-Disposition')?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
        if(encoded)filename=decodeURIComponent(encoded)
      } catch { throw new ApiError('CSV_DOWNLOAD_FAILED',response.status) }
      if(!blob.size)throw new ApiError('CSV_DOWNLOAD_FAILED',response.status)
      return {blob,filename:filename.replace(/[\\/\u0000-\u001f]/g,'_'),rowCount:response.headers.get('X-CSV-Row-Count')}
    },
    async list(group) {
      let offset = 0, items = [], page
      do {
        page = await request(`/artifacts/${group}?offset=${offset}&limit=100`)
        items.push(...page.items)
        offset += page.items.length
      } while (offset < page.total && page.items.length)
      return items
    },
  }
}
export const api = createApi()

// Complete cookie creation before concurrent history requests. The public ref
// only clears stale UI pointers; it never authorizes backend access.
export async function prepareWorkspace(storage = globalThis.localStorage, fetcher = globalThis.fetch) {
  let response, data
  try {
    response = await fetcher('/api/experiments/workspace', {credentials: 'same-origin', cache: 'no-store'})
    data = await response.json()
  } catch { throw new ApiError(null, 0) }
  if (!response.ok) throw new ApiError(data.detail, response.status)
  if (data.isolated) {
    if (typeof data.workspace_ref !== 'string' || !/^[a-f0-9]{64}$/.test(data.workspace_ref)) throw new ApiError(null, 0)
    try {
      if (storage.getItem('agenteval.browser-workspace') !== data.workspace_ref) {
        for (const key of ['agenteval.workspace.v1','agenteval.retrieval.v1','agenteval.career.v1','agenteval.practice.v1','agenteval.calibration.v1']) storage.removeItem(key)
        storage.setItem('agenteval.browser-workspace', data.workspace_ref)
      }
    } catch { /* Backend cookie still enforces privacy when storage is disabled. */ }
  }
  return data
}
