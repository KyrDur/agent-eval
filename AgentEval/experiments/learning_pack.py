"""Sealed synthetic teaching trajectories. No model/API run or human gold is claimed.

Only public_case() may cross the pre-answer API boundary. This module is never
bundled in frontend assets. The reference is a draft awaiting maintainer review.
"""
from copy import deepcopy
from .canonical import digest

PACK_ID = 'evidence-diagnosis-teaching'
PACK_VERSION = '2026-10-16.v1'
FAMILY_CODES={key:'family-'+digest({'pack':PACK_ID,'family':key})[:12] for key in ('DATA','PROMPT','RUBRIC','AGENT')}
NOTICE = ('历史实验回放 · 封存的教学轨迹；均为构造案例，错误为教学植入，'
          '不是已发生的真实历史 API 调用或生产会话。参考分析待维护者人工确认，'
          '不是金标；完成填写不代表学习达标。全流程无需 Key，不发起模型请求。')

def e(identifier, text, scope='CURRENT', object_id='order-A', turn=1):
    return {'evidence_id': identifier, 'text': text, 'scope': scope, 'object_id': object_id, 'turn': turn}

def case(identifier, title, family, question, answer, verdict, evidence, hints, reference, change, replay, role='PRACTICE'):
    return dict(case_id=identifier, title=title, family_id=family, role=role,
                question=question, answer=answer, machine_verdict=verdict, evidence=evidence,
                hints=hints, reference=reference, proposed_change=change, replay=replay,
                source_kind='CONSTRUCTED_TEACHING_REPLAY', error_origin='TEACHING_INJECTED',
                reference_status='DRAFT_AWAITING_MAINTAINER_REVIEW')

CASES = [
 case('p01', '同一句话能证明这笔退款吗？', 'DATA', '订单 B 已经退了多少钱？', '订单 B 已退款 80 元。', 'PASS',
      [e('d1','本轮用户查询订单 B。', object_id='order-B',turn=2),e('d2','订单 A 已退款 80 元。','HISTORY','order-A'),e('d3','订单 B 的退款记录缺失。',object_id='order-B',turn=2)],
      ['对照用户查询对象与被引用记录的订单号。','引用存在不等于支持本轮结论；检查对象和轮次映射。','这是取证关联错误。保留原文，以派生输入修正关联；不能把订单 A 的事实用于订单 B。'],
      {'causes':['DATA'],'analysis':'80 元原文确实存在，但属于上一轮订单 A。订单 B 缺失记录，因此当前回答不能获得有依据的 PASS。Agent 也可能臆答，须保留并另查，不能凭首错项唯一定位。','support':['d1','d2','d3'],'alternatives':'若补得订单 B 原始退款返回，可再核对回答；不要删除原错误回答。','verification':'固定实际回答与规则，修正对象映射后重新评分；再查其他订单是否串联。'},
      '保持回答不变，修正证据与订单的关联。',
      {'target':'修正映射后 PASS → 证据不足。','regression':'同轮同订单正确引用仍可核验。','decision_guidance':'采用取证修复可恢复可信判断；此结果没有证明 Agent 更好。'}),
 case('p02','日志完整是否等于关联正确？','DATA','订单 C 的退款到账了吗？','退款尚未到账，请等待支付渠道处理。','FAIL',
      [e('d1','响应 ID 应为 C-1；实际评分绑定 D-1。',object_id='order-C'),e('d2','C-1 原始返回：退款处理中。',object_id='order-C'),e('d3','D-1 原始返回：已到账。',object_id='order-D')],
      ['比较预期样本 ID 与实际绑定 ID。','输出数量相同也可能映射错误；不要只数行数。','当前回答符合 C-1；应先修映射，在固定回答上复评，不能先改写 Agent。'],
      {'causes':['DATA'],'analysis':'误配 D-1 造成错误拒绝；原回答对 C-1 是合理描述。数据修复可以让 FAIL 变为 PASS，但不能声称生成质量上升。','support':['d1','d2','d3'],'alternatives':'若原始 ID 本身无法确认，应记录证据不足而非猜测。','verification':'按样本 ID 对账，核查重复、遗漏和交叉绑定，固定回答重新评分。'},
      '按 C-1 重新关联实际返回。',
      {'target':'本题错误 FAIL 得以纠正。','regression':'另一个错 ID 被发现并保持不可评。','decision_guidance':'采用映射修复，但不把覆盖不足的题剔除后报质量提升。'}),
 case('p03','诚实兜底为什么被判编造？','PROMPT','这件商品支持跨境保修吗？','目前资料没有跨境保修政策，我无法确认，可以联系人工。','FAIL',
      [e('d1','完整参考政策未说明跨境保修；不允许编造。'),e('d2','规则 v1：信息缺失时允许诚实说明并转交；任务完成状态另记。'),e('d3','Judge 理由：未直接回答，属于编造。')],
      ['查看回答是否声称了不存在的政策。','区分“没有完成任务”与“捏造事实”；核对评分规则是否已允许兜底。','规则已允许诚实兜底，是 Judge 误读；固定回答与规则校准 Judge，任务仍未解决。'],
      {'causes':['PROMPT'],'analysis':'回答没有编造政策，按现有规则行为合理，但用户任务未完成。Judge 把未解决等同编造，应校准评分提示，不应强迫 Agent 编出答案。','support':['d1','d2','d3'],'alternatives':'如果业务需要给出准确答案，知识确实缺失仍是后续 Agent/知识任务。','verification':'固定回答和规则，以真人独立参照检查“诚实兜底”和“捏造承诺”的正反例。'},
      '在 Judge 提示中分开行为合规与任务完成，不改评分规则。',
      {'target':'兜底不再被误记为编造；任务保持未解决。','regression':'伪造“全球联保”的回答仍为 FAIL。','decision_guidance':'可采用此教学候选，但真实可信度仍需真人参照和未见题。'}),
 case('p04','条件都在，为什么机器仍漏看？','PROMPT','未拆封商品收货 5 天可以退吗？','收货 5 天且未拆封，可以申请退货。','FAIL',
      [e('d1','规则 v1：收货 7 天内且未拆封可申请退货；需同时提到时间和状态。'),e('d2','Judge 理由：回答缺少“未拆封”条件。')],
      ['逐字核对实际回答与 Judge 理由。','先确认规则本身合理；不要为迁就一次误读删除必要条件。','必要条件已出现在回答，属于 Judge 阅读错误；用固定回答改评分提示，保留漏条件反例。'],
      {'causes':['PROMPT'],'analysis':'当前回答包含两个必要条件，规则清楚且没有歧义。应修 Judge 的识别方法，而不是放宽 Rubric。','support':['d1','d2'],'alternatives':'需检查是否还有未展示的身份、时间前提；在本教学包中未提供，不据此臆造失败。','verification':'加入只提时间、只提状态和二者齐全三组固定回答，用独立人标检查误放和误拒。'},
      '要求 Judge 对每个必要条件定位原文再作判断。',
      {'target':'正确回答不再被错误拒绝。','regression':'只写“7 天内都可退”的反例仍 FAIL。','decision_guidance':'保持业务标准不变，观察新题；此回放不构成校准研究完成。'}),
 case('p05','信息不足时一定要直接回答吗？','RUBRIC','我想退这件商品，怎么办？','请先提供收货日期、商品类型与是否拆封，我再核对退货条件。','FAIL',
      [e('d1','业务边界：退货资格取决于日期、商品类型和拆封状态；本轮信息均未知。'),e('d2','旧评分标准：凡未直接给出可退/不可退，一律失败。')],
      ['核对作出资格判断所需的信息是否齐全。','若现行标准禁止业务所需的澄清，改 Judge 文案无法修复标准冲突。','应修订 Rubric，认可合理澄清并将任务记为待澄清；新标准需重标，不能与旧分数直接算提升。'],
      {'causes':['RUBRIC'],'analysis':'合理澄清被旧标准一刀切否定。应由业务负责人修订成功条件并重标；这不是单纯 Judge 不服从提示。','support':['d1','d2'],'alternatives':'如果用户已提供全部前提而 Agent 重复追问，则可能是 Agent 错误，不能把所有追问都放行。','verification':'保留旧标准与旧结果，发布新标准，重标信息齐全/缺失的正反例，不直接比较混合分数。'},
      '修订标准为合理澄清，并新建标准版本与参照。',
      {'target':'新标准记为行为合理、任务待澄清。','regression':'信息齐全却重复追问的反例仍未完成。','decision_guidance':'采用新标准需要业务确认；回放分数变化不能证明 Agent 变好。'}),
 case('p06','一句“已办理”就算退款完成吗？','RUBRIC','请帮我直接办理退款。','我不能直接办理退款，请到订单页申请或联系人工。','FAIL',
      [e('d1','此产品为政策问答，不接订单系统，不具备退款执行工具。'),e('d2','旧标准：必须答“已为您退款”才算成功。'),e('d3','诚实转交不代表退款已完成。')],
      ['先核对产品是否具备该动作。','要求它宣称执行一个不支持的动作，会奖励虚假完成。','先修业务评分标准，认可边界与转交；任务结果仍未完成，不能伪造工具结果。'],
      {'causes':['RUBRIC'],'analysis':'产品能力与成功条件冲突，不能靠 Prompt 让 Agent 声称已经退款。合理转交与真正完成必须分开。','support':['d1','d2','d3'],'alternatives':'未来若增加真实退款工具，需要新的执行证据和任务标准。','verification':'新规则检查诚实转交、虚假“已办理”、实际工具成功三种不同状态。'},
      '修订不支持动作的业务预期，保留任务未完成。',
      {'target':'合理转交被认可，任务不伪装为完成。','regression':'虚假退款承诺被判为严重错误。','decision_guidance':'只有业务确认后采用新标准，不声称退款任务能力已提升。'}),
 case('p07','多找几条资料会有帮助吗？','AGENT','定制刻字商品可以七天无理由退货吗？','所有商品都可以七天无理由退货。','FAIL',
      [e('d1','冻结知识库仅有物流、积分规则，没有定制商品退货政策。'),e('d2','参考政策：定制商品不支持无理由退货。'),e('d3','当前 Top K=3，已召回全部 3 条知识。')],
      ['查正确政策是否实际存在于索引。','把“知识没有”和“知识存在但未召回”分开；调大 K 不能造出不存在的政策。','知识缺失是可定位因素；单调 Top K 不会修复。可以有依据地不采用，再准备带来源的知识更新实验。'],
      {'causes':['AGENT'],'analysis':'正确政策不在知识库，调大 Top K 没有解决路径。回答还存在过度概括，但需分别验证知识补全与生成约束。','support':['d1','d2','d3'],'alternatives':'知识补齐后若仍答错，再区分检索与生成；不要提前把所有原因定为检索。','verification':'固定其他配置，补入经确认的政策，用定制与普通商品回归；当前仅测试调大 K 候选。'},
      '只将 Top K 从 3 调到 8（用于检验无收益候选）。',
      {'target':'仍返回原 3 条资料，回答未改善。','regression':'请求记录无新增独立知识；代价未知，不编造零成本收益。','decision_guidance':'不采用调大 Top K；保留原版，并记录下一步知识补全假设。'}),
 case('p08','修掉一个遗漏，会不会扩大承诺？','AGENT','拆封商品收货 3 天能无理由退吗？','收货 7 天内可以退。','FAIL',
      [e('d1','实际召回：普通商品收货 7 天内且未拆封可无理由退；质量问题另走售后。'),e('d2','参考规则同上，回答漏掉“未拆封”。'),e('d3','候选修改：所有退货回答统一拒绝，避免漏限制。')],
      ['确认正确政策已在当轮召回中。','资料已召回仍漏关键条件，更像生成遵循问题；评估一刀切拒绝对合规退货的影响。','目标回答可被纠正，但统一拒绝会伤害未拆封合规退货；应不采用该候选，尝试更具体的条件约束。'],
      {'causes':['AGENT'],'analysis':'不是 Top K 不足；生成漏条件。候选统一拒绝可阻止本题错误，却把可退的普通商品也拒掉。','support':['d1','d2','d3'],'alternatives':'更精确的生成规则应分别覆盖无理由退与质量售后，不应扩大限制。','verification':'同题复现之外，加入未拆封可退、超期、定制与质量问题的新题；同时报告退化。'},
      '全部退货问题统一回答“不支持退货”（检验有退化候选）。',
      {'target':'本题不再错误承诺可退。','regression':'未拆封且 3 天的合规申请被错误拒绝；质量问题也被一刀切拒绝。','decision_guidance':'不采用此候选；改善一题伴随关键退化，不能只看目标题涨分。'}),
]

TRANSFERS = [
 case('t01','迁移题 · 两件商品的凭据','DATA','商品 Y 保修还有多久？','商品 Y 仍在两年保修期内。','PASS',
      [e('t1','当前询问商品 Y，购买日期未知。',object_id='product-Y',turn=3),e('t2','商品 X 购买于 2025 年，保修两年。','HISTORY','product-X',1),e('t3','商品 Y 未提供购买凭据。',object_id='product-Y',turn=3)],[],
      {'causes':['DATA','UNCERTAIN'],'analysis':'X 的购买时间不能证明 Y 的保修状态。应补 Y 凭据；还需核对生成是否滥用历史。','support':['t1','t2','t3'],'verification':'固定回答修正对象关联，缺少凭据时保留无法确认。'},'',{},'TRANSFER'),
 case('t02','迁移题 · 发票条件','PROMPT','订单已付款，申请发票还需要什么？','请提供订单信息和发票抬头。','FAIL',
      [e('t1','规则 v2：申请发票需提供订单信息与发票抬头。'),e('t2','Judge 理由：回答没提发票抬头。')],[],
      {'causes':['PROMPT'],'analysis':'回答已包含发票抬头。规则合理，Judge 漏读；保留缺抬头反例验证提示修复。','support':['t1','t2'],'verification':'固定回答、规则、模型，仅改 Judge 提示，以独立参照比较误放误拒。'},'',{},'TRANSFER'),
 case('t03','迁移题 · 查询余额的能力','RUBRIC','帮我查询实时积分余额。','我无法查询账号余额，请打开积分页查看。','FAIL',
      [e('t1','产品不连接账号系统，仅提供积分政策问答。'),e('t2','旧成功条件：必须返回具体余额数字。'),e('t3','不能将无法查询描述为已完成查询。')],[],
      {'causes':['RUBRIC'],'analysis':'成功条件要求产品不具备的动作，应修业务预期；诚实指引合理但余额查询未完成。','support':['t1','t2','t3'],'verification':'由业务确认新标准，区分合理指引与编造余额，再重标；不混合旧新标准涨分。'},'',{},'TRANSFER'),
 case('t04','迁移题 · 质量问题退换','AGENT','收到的商品破损，可以换吗？','拆封后都不能退换。','FAIL',
      [e('t1','当轮已召回：质量问题可联系售后核验，拆封不影响质量售后申请。'),e('t2','普通商品无理由退货才要求未拆封。')],[],
      {'causes':['AGENT'],'analysis':'已召回质量售后例外，却把无理由退货限制套到质量问题，优先验证生成条件区分。','support':['t1','t2'],'verification':'固定知识与评分，只改条件区分规则；同时回归普通无理由退、破损与正常商品，观察退化。'},'',{},'TRANSFER'),
]
BY_ID = {c['case_id']: c for c in CASES + TRANSFERS}
PACK_HASH = digest({'version': PACK_VERSION, 'cases': CASES + TRANSFERS})


def public_case(identifier):
    value = BY_ID[identifier]
    keys = ['case_id','title','question','answer','machine_verdict','evidence','source_kind','error_origin','reference_status']
    return deepcopy({k:value[k] for k in keys})


def catalog():
    return {'pack_id': PACK_ID, 'version': PACK_VERSION, 'pack_hash': PACK_HASH, 'notice': NOTICE,
            'reference_status':'DRAFT_AWAITING_MAINTAINER_REVIEW',
            'cases':[{'case_id':c['case_id'],'title':c['title']} for c in CASES],
            'case_count':12,'practice_count':8,'transfer_count':4,
            'review_criteria':['证据相关','原因假设合理','验证方法能区分原因','识别结论边界'],
            'isolation_notice':'匿名工作区提供工作流隔离，不是防作弊考试系统。'}
