"""Explain existing evidence decisions without changing them or inventing gaps."""
import json
from pathlib import Path

LABELS = json.loads(Path(__file__).with_name('evidence_reason_labels.json').read_text())


def decision_reasons(result, package, state):
    if state != 'EVIDENCE_INSUFFICIENT':
        return []
    if package is None:
        return [{'code': 'FROZEN_INPUT_MISSING', 'message': '这份记录没有保存本题评分所需的证据包',
            'next_step': '核对历史记录；不能由这份结果判断答案是否正确。'}]
    codes = list(package.get('missing_items', []))
    codes += [v.get('reason', '') for v in package.get('check', {}).get('issues', [])]
    codes += [v.get('reason', '') for v in package.get('item_checks', []) if v.get('status') == state]
    codes += [v.get('reason', '') for v in package.get('truncated_items', [])]
    evaluation = result.get('evidence_evaluation') if isinstance(result, dict) else getattr(result, 'evidence_evaluation', None)
    judgment = ((evaluation or {}).get('judgment') or {})
    codes += judgment.get('insufficient_items', [])
    reasons = {}
    for code in codes:
        code = str(code)
        known = next((key for key in LABELS if key in code), None)
        if known:
            message, next_step = LABELS[known]
            reasons[known] = {'code': known, 'message': message, 'next_step': next_step}
        elif code:
            key = code.split(':', 1)[0]
            reasons.setdefault(key, {'code': code, 'message': '本题仍有需要核对的证据项',
                'next_step': '展开本题的评分资料，核对列出的不足项和原文。'})
    if not reasons:
        reasons['UNSPECIFIED'] = {'code': 'INSUFFICIENT_REASON_UNRECORDED',
            'message': '当前记录未说明具体缺口，暂时无法确定原因',
            'next_step': '核对这道题的原始资料与评分结果，不能据此推断是知识库或模型出错。'}
    return list(reasons.values())
