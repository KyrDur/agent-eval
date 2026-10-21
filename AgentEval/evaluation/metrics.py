"""All dialog quality aggregation uses this gate. Intent is a separate group."""
import statistics

from evaluation.models import DIMENSIONS


def dialog_metrics(results):
    valid = [r for r in results if not r.exclude_from_quality_metrics]
    scored = [r for r in valid if r.judge_status == "SUCCESS" and all(k in r.scores for k in DIMENSIONS)]
    passed = sum(r.final_status == "PASS" for r in valid)
    evidence = [r for r in valid if r.scoring_protocol and r.judge_status == 'SUCCESS']
    evidence_groups = {}
    for row in evidence:
        key = row.scoring_protocol['profile_hash']
        evidence_groups.setdefault(key, {'protocol':row.scoring_protocol,'rows':[]})['rows'].append(row)
    evidence_metrics = []
    for group in evidence_groups.values():
        averages = {}
        denominators = {}
        for dim in ('faithfulness','conditions','relevance','actionability'):
            values = [r.evidence_evaluation['judgment']['dimensions'][dim]['score'] for r in group['rows']]
            values = [v for v in values if type(v) is int]
            averages[dim] = statistics.mean(values) if values else None
            denominators[dim] = len(values)
        evidence_metrics.append({'protocol':group['protocol'],'scored_cases':len(group['rows']),
            'avg_scores':averages,'denominators':denominators})
    return {
        "total": len(results), "valid": len(valid), "passed": passed,
        "failed": sum(r.final_status == "FAIL" for r in valid),
        "invalid": len(results) - len(valid),
        "agent_errors": sum(r.execution_status == "FAILED" for r in results),
        "judge_errors": sum(r.judge_status == "FAILED" for r in results),
        "evaluation_errors": sum(r.evaluation_error is not None for r in results),
        "pending_human_reviews": sum(r.review_status == "PENDING" for r in results),
        "hard_rule_violations": sum(bool(r.hard_rule_violations) for r in results),
        "quality_scored_cases": len(scored),
        "evidence_scored_cases":len(evidence), "evidence_score_groups":evidence_metrics,
        "evidence_pending":sum(bool(r.evidence_evaluation and (r.evidence_evaluation.get('judgment') or {}).get('verdict')=='PENDING') for r in results),
        "pass_rate": passed / len(valid) if valid else None,
        "avg_scores": {k: statistics.mean(r.scores[k] for r in scored) for k in (*DIMENSIONS, "overall")}
            if scored else {},
    }
