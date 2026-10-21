"""Project defaults and contribution summaries from sealed experiment records.

Defaults describe the practice workbench, not the shoppers of the demo store.
No model calls, questionnaires, or writes to the experiment are involved.
"""
from .career_models import ProjectContext

CHANGE_NAMES = {
    'RERANK_TOGGLE': '知识重排', 'QUERY_REWRITE_TOGGLE': '问题改写',
    'TOP_K_CHANGE': '返回资料数量', 'TOP_K': '返回资料数量',
    'ANSWER_PROMPT_CHANGE': '回答要求', 'KNOWLEDGE_UPDATE': '知识资料版本',
}


def project_context(kind, base, after, comparison, store):
    snapshot = base.controls['eval_set_snapshot'] if kind == 'RETRIEVAL' else base.eval_set_snapshot
    cases = snapshot.get('cases', snapshot.get('case_snapshot', []))
    executed = len(base.case_results)
    steps = [f'围绕电商客服场景运行初测，保存 {executed} 道题已返回的过程与结果']
    parents = []
    change = None
    if after:
        if kind == 'RETRIEVAL' and after.change_id:
            change = store.get('retrieval_changes', after.change_id)
            parents.append('retrieval_changes:' + after.change_id)
            steps.append('依据保存的修改理由，选择调整' + CHANGE_NAMES.get(change.change_type, '客服配置'))
        elif kind == 'AGENT_BEHAVIOR' and after.applied_change_ids:
            parents.extend('changes:' + identifier for identifier in after.applied_change_ids)
            steps.append('按已保存的修改记录调整客服规则')
        steps.append(f'运行复测并保存 {len(after.case_results)} 道题已返回的结果，保留修改前后版本')
    elif kind == 'RETRIEVAL':
        proposals = sorted((item for item in store.list('retrieval_changes')
                            if item.baseline_run_id == base.run_id), key=lambda item: item.confirmed_at)
        if proposals:
            change = proposals[-1]
            parents.append('retrieval_changes:' + change.change_id)
            state = '已应用，尚无复测结果' if change.implemented_status == 'APPLIED' else '待应用、待复测'
            steps.append('记录调整' + CHANGE_NAMES.get(change.change_type, '客服配置') + '的方案（' + state + '）')
    if comparison:
        steps.append('保存逐题对比，分别检查改善、未变、退化及无法比较的结果')
    source_counts = {}
    for case in cases:
        source = case.get('source') or 'UNSPECIFIED'
        source_counts[source] = source_counts.get(source, 0) + 1
    context = ProjectContext(
        project_name='电商客服 Agent 评测与优化实践', project_context='PERSONAL_PROJECT',
        motivation='为缺少项目经历的求职者提供可操作的 AI 产品实践，将评测、问题分析和迭代过程整理为有依据的项目经历。',
        target_users='18–24 岁、缺少项目经历的求职者',
        user_problem='缺少能亲自操作、验证和复盘的项目经历，难以在简历与面试中说明自己做了哪些产品判断、修改带来了什么结果。',
        why_ai='以电商客服为实践场景：AI 理解自然语言问题并组织回答；RAG 先从店铺知识中查找商品、退换货等资料，再依据检索内容回答，便于核对答案与来源。Agent 执行本轮配置的客服任务，平台保存过程并评测。当前实验具备哪些能力，以运行记录为准。',
        user_roles=['产品设计'], user_contribution='；'.join(steps) + '。',
        system_contribution='平台提供知识导入、检索、客服作答、评分、对比和材料整理能力；模型完成调用中的文本生成。记录中的平台能力不计作使用者独立开发的工程成果。',
        existing_capabilities='本项目提供电商客服实践场景及知识问答、检索配置和评测流程；用户在已有能力上进行实验。实际使用范围以本次保存的记录为准。',
        real_users=False, deployed=False, confirmed=True,
    )
    return context, {
        'origin': 'PROJECT_TEMPLATE', 'version': '20261019',
        'background_source': '产品方预设的实践背景：18–24 岁求职者；产品设计角色',
        'contribution_source': '本次已保存的初测、复测、修改与对比记录',
        'case_sources': source_counts,
        'real_users_and_deployment': 'NOT_VERIFIED',
        'reflection': '未从记录推断个人反思或已验证根因',
        'capability_sources': ['AgentEval/experiments/RETRIEVAL.md', 'AgentEval/wiki/AgentEval定位与技术亮点.md'],
    }, parents
