"""Versioned retrieval trust views; old artifacts and their hashes stay untouched.

The legacy PASS/FAIL/INVALID API remains available. This companion records why an
answer is (or is not) evaluable, and reconciles event identities before counting.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .canonical import digest, text_hash

SCHEMA = 'TRUSTED_RESULT_V1'
CHECK_STATES = ('PASS', 'FAIL', 'EVIDENCE_INSUFFICIENT', 'NOT_APPLICABLE',
                'NOT_CHECKED', 'EXECUTION_FAILED', 'NOT_RUN')


def source_identity(case):
    declared = case.evidence_context.get('source_type')
    # A local API call, an imported chat, or the editor's default are not proof
    # that the question came from a real production user.
    if declared in {'ACTUAL', 'CONSTRUCTED', 'AI_GENERATED','UNKNOWN'}:
        return declared
    return 'AI_GENERATED' if case.source == 'ai_generated' else 'CONSTRUCTED' if case.source == 'demo' else 'UNKNOWN'


def _date(value, timezone=None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            if not timezone:
                return None
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone))
        return parsed
    except (ValueError, TypeError, ZoneInfoNotFoundError, AttributeError):
        return None


def freeze_input(case, retrieval, answer, documents, run_id=None):
    """Keep all visible sources, including inapplicable ones and actual errors.

    Applicability is separate from existence/hash checks. Missing metadata stays
    null; no current date, current object or assumed policy version fills it in.
    """
    context = deepcopy(case.evidence_context)
    requirements = context.get('required_evidence', [])
    from .evidence_policy import checks, selected_history
    item_checks = checks(case.scenario_rules, case.reference_complete, len(documents),len(retrieval.get('results',[])))
    missing = list(context.get('missing_items', []))
    truncated = list(context.get('truncated_items', []))
    if retrieval.get('error')=='INPUT_BUDGET_EXCEEDED':
        truncated.append({'scope':'PLANNED_MODEL_REQUEST','reason':'INPUT_BUDGET_EXCEEDED','omitted':False})
    reference = {d['document_id']: d for d in documents}
    evidence = []
    problems = []
    question_at = _date(context.get('question_time'), context.get('question_timezone'))
    for scope, values in [('RETRIEVED', retrieval.get('results', [])), ('REFERENCE', documents)]:
        for value in values:
            document_id = value.get('document_id')
            source = reference.get(document_id, {})
            metadata = {**source.get('metadata', {}), **value.get('metadata', {})}
            identifier = value.get('chunk_id') if scope == 'RETRIEVED' else document_id
            text = value.get('text', '')
            issues = []
            expected_hash = value.get('text_hash') if scope == 'RETRIEVED' else value.get('content_hash')
            if expected_hash and expected_hash != text_hash(text):
                issues.append('SOURCE_HASH_MISMATCH')
            for field in ('conversation_id', 'turn_id'):
                actual, expected = metadata.get(field), context.get(field)
                if actual is not None and expected is not None and actual != expected:
                    dependency = next((d for d in context.get('history_dependencies', [])
                        if d.get('evidence_id') == identifier and d.get('conversation_id') == actual
                        and d.get('turn_id') == metadata.get('turn_id')
                        and d.get('valid_for_turn_id') == context.get('turn_id')
                        and d.get('object_ids', {}) == context.get('object_ids', {})), None)
                    if dependency is None:
                        issues.append(field.upper() + '_MISMATCH')
            for key, actual in metadata.get('object_ids', {}).items():
                expected = context.get('object_ids', {}).get(key)
                if expected is not None and actual != expected:
                    issues.append('OBJECT_MISMATCH:' + key)
            expected_version = context.get('policy_versions', {}).get(document_id)
            if expected_version is not None and metadata.get('policy_version') != expected_version:
                issues.append('POLICY_VERSION_MISMATCH')
            if metadata.get('effective_from') or metadata.get('effective_until'):
                start = _date(metadata.get('effective_from'), metadata.get('policy_timezone'))
                end = _date(metadata.get('effective_until'), metadata.get('policy_timezone'))
                if question_at is None or (metadata.get('effective_from') and start is None) or (metadata.get('effective_until') and end is None):
                    issues.append('POLICY_TIME_PREMISES_MISSING')
                elif (start and question_at < start) or (end and question_at >= end):
                    issues.append('POLICY_NOT_EFFECTIVE')
            if 'object_ids' in requirements and (not context.get('object_ids') or not metadata.get('object_ids')):
                issues.append('OBJECT_SCOPE_UNKNOWN')
            if 'turn_id' in requirements and (not context.get('turn_id') or not metadata.get('turn_id')):
                issues.append('TURN_SCOPE_UNKNOWN')
            if 'policy_time' in requirements and (question_at is None or not metadata.get('effective_from') or not metadata.get('policy_version')):
                issues.append('POLICY_TIME_PREMISES_MISSING')
            evidence.append({'evidence_id': identifier, 'scope': scope,
                'visibility': metadata.get('visibility', 'RETRIEVED_CONTEXT' if scope == 'RETRIEVED' else 'REFERENCE_POLICY'),
                'document_id': document_id, 'text': text, 'source_sha256': text_hash(text),
                'source_position': value.get('source_position'), 'chunk_index': value.get('chunk_index'),
                'metadata': metadata, 'applicability': 'EVIDENCE_INSUFFICIENT' if issues else 'PASS',
                'applicability_reasons': sorted(set(issues))})
            problems.extend({'evidence_id': identifier, 'scope': scope, 'reason': reason} for reason in sorted(set(issues)))
    retrieved_ids = {v.get('evidence_id') for v in evidence}
    for required in context.get('required_evidence_ids', []):
        if required not in retrieved_ids:
            missing.append('EVIDENCE:' + str(required))
    reference_ids={v['evidence_id'] for v in evidence if v['scope']=='REFERENCE'}
    for identifier in context.get('required_reference_ids',[]):
        if identifier not in reference_ids:missing.append('REFERENCE:'+str(identifier))
    for field in ('question_timezone', 'business_day_rule', 'policy_effective_date'):
        if field in requirements and not context.get(field):
            missing.append(field)
    if case.reference_complete is True and not documents:
        missing.append('REFERENCE_POLICY')
    if (any(c['status']=='EVIDENCE_INSUFFICIENT' for c in item_checks) or 'reference_complete' in requirements) and case.reference_complete is not True:
        missing.append('REFERENCE_COMPLETENESS_UNCONFIRMED')
    # Never truncate silently. A model context budget must be explicitly
    # supported before very large input can be judged faithfully.
    characters = len(case.query) + len(answer or '') + sum(len(m['content']) for m in case.context) + sum(len(v['text']) for v in evidence)
    max_characters = context.get('max_input_characters', 100000)
    if not isinstance(max_characters, int) or isinstance(max_characters, bool) or max_characters < 1:
        max_characters = 100000
    if characters > min(max_characters, 500000):
        truncated.append({'scope': 'JUDGE_INPUT', 'reason': 'INPUT_BUDGET_EXCEEDED', 'characters': characters,
                          'limit': min(max_characters, 500000), 'omitted': False})
    missing = sorted(set(str(v) for v in missing))
    package = {'schema_version': SCHEMA, 'sample_id': case.case_id, 'run_id': run_id,
        'parent_input_id': context.get('parent_input_id'), 'conversation_id': context.get('conversation_id'),
        'turn_id': context.get('turn_id'), 'object_ids': context.get('object_ids'),
        'question_time': context.get('question_time'), 'question_timezone': context.get('question_timezone'),
        'source_type': source_identity(case), 'editor_source': case.source, 'question': case.query,
        'current_answer': answer, 'necessary_history': selected_history(case), 'original_history':deepcopy(case.context),
        'history_selection':{'mode':context.get('history_mode','RECENT_FOUR'),'original_count':len(case.context),'selected_count':len(selected_history(case))},
        'history_dependencies': context.get('history_dependencies', []), 'evidence': evidence,
        'tool_evidence': deepcopy(retrieval.get('tool_evidence', [])),
        'reference_complete': case.reference_complete, 'reference_completeness': deepcopy(case.reference_completeness),
        'scenario_rules': deepcopy(case.scenario_rules), 'missing_items': missing, 'truncated_items': truncated,
        'cleaning_version': context.get('cleaning_version'), 'semantic_mapping_version': context.get('semantic_mapping_version'),
        'evidence_contract_version':'EVIDENCE_CONTRACT_V2', 'item_checks': item_checks, 'scope_frozen_before_scoring':True,
        'check': {'status': 'EVIDENCE_INSUFFICIENT' if missing or truncated or problems else 'PASS',
                  'issues': problems, 'semantic_support': 'REQUIRES_JUDGMENT',
                  'reference_completeness_status': 'DECLARED_COMPLETE' if case.reference_complete is True else
                    'DECLARED_INCOMPLETE' if case.reference_complete is False else 'UNKNOWN'}}
    package['content_hash'] = digest(package)
    package['input_id'] = package['content_hash']
    return package


def result_state(result, package=None):
    if result is None:
        return 'NOT_RUN'
    budget_blocked=(getattr(result,'judge_error',None)=='INPUT_BUDGET_EXCEEDED' or any(getattr(t,'execution_error',None)=='INPUT_BUDGET_EXCEEDED' for t in getattr(result,'turn_evidence',[])) or any(t.get('reason')=='INPUT_BUDGET_EXCEEDED' for t in (package or {}).get('truncated_items',[])))
    if budget_blocked:return 'EVIDENCE_INSUFFICIENT'
    if result.execution_status != 'SUCCESS':
        return 'EXECUTION_FAILED'
    if result.hard_rule_violations:
        return 'FAIL'
    if package is None:
        return 'EVIDENCE_INSUFFICIENT'
    review = getattr(result,'human_evaluation_state',None)
    if review in {'EVIDENCE_INSUFFICIENT','NOT_APPLICABLE'}:
        return review
    if result.judge_status == 'FAILED' or result.evaluation_error:
        return 'EXECUTION_FAILED'
    if package and package.get('check', {}).get('status') == 'EVIDENCE_INSUFFICIENT':
        judgment=(result.evidence_evaluation or {}).get('judgment') or {}
        if judgment.get('critical_errors') or judgment.get('verdict')=='FAIL':
            return 'FAIL'
        return 'EVIDENCE_INSUFFICIENT'
    applicability=(package or {}).get('scenario_rules',{}).get('evaluation_applicability',{})
    # An explicit, confirmed scope rule may exempt an otherwise passing event.
    # It can never conceal a visible failure or an unconfirmed critical check.
    if (isinstance(applicability,dict) and applicability.get('applicable') is False
        and all(isinstance(applicability.get(k),str) and applicability[k].strip()
                for k in ('rule_id','reason','confirmed_by'))) and (package.get('scope_frozen_before_scoring') or result.final_status=='PASS'):
        return 'NOT_APPLICABLE'
    if 'reference_complete' in package:
        from .evidence_policy import checks
        items=checks(package.get('scenario_rules',{}),package.get('reference_complete'),sum(v.get('scope')=='REFERENCE' for v in package.get('evidence',[])),sum(v.get('scope')=='RETRIEVED' for v in package.get('evidence',[])))
        if any(i['status']=='EVIDENCE_INSUFFICIENT' for i in items):return 'EVIDENCE_INSUFFICIENT'
    if result.final_status in {'PASS', 'FAIL'}:
        return result.final_status
    if result.judge_status == 'SUCCESS' and result.evidence_evaluation:
        return 'EVIDENCE_INSUFFICIENT'
    return 'NOT_CHECKED' if result.judge_status == 'NOT_RUN' else 'EVIDENCE_INSUFFICIENT'


def answer_trust(result, package=None, retrieval=None):
    state = result_state(result, package)
    evaluation = (result.evidence_evaluation or {}) if result else {}
    judgment = evaluation.get('judgment') or {}
    business = next((v['business_assessment'] for v in evaluation.get('citation_provenance', [])
                     if 'business_assessment' in v), {})
    task = business.get('task_outcome', {'YES': 'COMPLETED', 'NO': 'UNRESOLVED'}.get(judgment.get('task_resolved'), 'UNKNOWN'))
    if state in {'NOT_RUN', 'EXECUTION_FAILED', 'EVIDENCE_INSUFFICIENT', 'NOT_CHECKED'}:
        task = 'UNKNOWN'
    forbidden = bool(result and result.case and any(r.type == 'forbidden_claim' for r in result.case.executable_rules))
    critical = 'FAIL' if result and (result.hard_rule_violations or judgment.get('critical_errors')) else (
        'PASS' if forbidden or (judgment and state in {'PASS', 'FAIL'}) else 'NOT_CHECKED')
    return {'schema_version': SCHEMA, 'evaluation_state': state,
        'legacy_status': result.final_status if result else None,
        'task_outcome': task, 'task_unit': 'TURN',
        'current_turn_behavior': business.get('current_turn_behavior', 'UNKNOWN'),
        'expected_behavior': (package or {}).get('scenario_rules', {}).get('expected_behavior'),
        'judged_by': 'HUMAN_REVIEW' if result and result.human_final_status else 'MACHINE' if judgment else 'EXECUTABLE_RULE' if result and result.hard_rule_violations else 'UNKNOWN',
        'scoring_protocol': result.scoring_protocol if result else None,
        'checks': [{'name': 'retrieval', 'status': 'PASS' if retrieval and retrieval.get('status') == 'SUCCESS' else 'EXECUTION_FAILED' if retrieval else 'NOT_RUN'},
                   {'name': 'generation', 'status': 'PASS' if result and result.execution_status == 'SUCCESS' else 'NOT_CHECKED' if retrieval and retrieval.get('status') != 'SUCCESS' else 'EXECUTION_FAILED' if result else 'NOT_RUN'},
                   {'name': 'evidence', 'status': (package or {}).get('check', {}).get('status', 'NOT_CHECKED')},
                   {'name': 'quality', 'status': state},
                   {'name': 'critical_errors', 'status': critical},
                   {'name': 'business_tools', 'status': 'NOT_APPLICABLE', 'rule': 'SINGLE_TURN_RAG_HAS_NO_BUSINESS_ACTION_TOOLS'}],
        'first_failed_check_is_root_cause': False}


def reconcile(expected_ids, records, identifier=lambda r: r['case_id'], version=None):
    counts = Counter(identifier(r) for r in records)
    expected = set(expected_ids)
    duplicates = sorted(k for k, count in counts.items() if count > 1)
    missing = sorted(expected - set(counts))
    unexpected = sorted(set(counts) - expected)
    valid_ids = sorted(expected & set(counts) - set(duplicates))
    return {'schema_version': SCHEMA, 'event_key': ['sample_id', 'version', 'repetition'],
        'version': version, 'repetition': 1,
        'expected_count': len(expected_ids), 'received_count': len(records), 'unique_received_count': len(counts),
        'expected_ids': list(expected_ids), 'valid_ids': valid_ids, 'missing_ids': missing,
        'duplicate_ids': duplicates, 'unexpected_ids': unexpected,
        'complete': not missing and not unexpected and not duplicates and len(expected_ids) == len(expected)}


def _ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}


def sample_flow(run, answers=None):
    expected = list(run.execution_order)
    rows = run.case_results
    answers = run.answer_results if answers is None else answers
    retrieval_check = reconcile(expected, rows, version=run.controls.get('eval_set_hash'))
    answer_check = reconcile(expected, answers, lambda v: v.case_id,
                             version=run.controls.get('scoring_profile', {}).get('content_hash') or run.controls.get('evaluation_protocol_hash'))
    valid_answers = {r.case_id: r for r in answers if r.case_id in answer_check['valid_ids']}
    by_row = {r['case_id']: r for r in rows if r['case_id'] in retrieval_check['valid_ids']}
    states = {key: [] for key in CHECK_STATES}
    tasks = {key: [] for key in ('COMPLETED', 'UNRESOLVED', 'WAITING_CLARIFICATION', 'UNKNOWN')}
    for identifier in expected:
        row = by_row.get(identifier)
        answer = valid_answers.get(identifier)
        trust = answer_trust(answer, row.get('input_package') if row else None, row)
        state = trust['evaluation_state'] if run.verify_answers else 'NOT_RUN'
        states[state].append(identifier)
        tasks[trust['task_outcome']].append(identifier)
    binary = len(states['PASS']) + len(states['FAIL'])
    cases = run.controls.get('eval_set_snapshot', {}).get('cases', [])
    included = [c for c in cases if c['case_id'] in set(expected)]
    sources = {}
    for case in included:
        source = case.get('evidence_context', {}).get('source_type') or ('AI_GENERATED' if case.get('source') == 'ai_generated' else 'CONSTRUCTED' if case.get('source') == 'demo' else 'UNKNOWN')
        sources.setdefault(source, []).append(case['case_id'])
    eligible = [i for i in expected if i not in states['NOT_APPLICABLE']] if run.verify_answers else []
    enough = [identifier for identifier in expected if by_row.get(identifier, {}).get('input_package', {}).get('check', {}).get('status') == 'PASS']
    flow = {'schema_version': SCHEMA, 'unit': 'SAMPLE_VERSION_REPETITION',
        'raw_record_count': len(cases), 'independent_case_count': len(expected),
        'problem_family_count': len({c.get('group_id') or c['case_id'] for c in included}),
        'answer_count': len(answer_check['valid_ids']), 'scoring_event_count': len(answers),
        'retrieval_reconciliation': retrieval_check, 'answer_reconciliation': answer_check if run.verify_answers else None,
        'states': {key: {'count': len(value), 'sample_ids': value} for key, value in states.items()},
        'task_outcomes': {key: {'count': len(value), 'sample_ids': value} for key, value in tasks.items()},
        'coverage': _ratio(binary, len(eligible)), 'machine_pass_rate': _ratio(len(states['PASS']), binary),
        'sources': {key: {'count': len(value), 'sample_ids': value, 'production_frequency': None} for key, value in sources.items()},
        'stages': [
            {'name': 'raw_records', 'count': len(cases), 'sample_ids': [c['case_id'] for c in cases]},
            {'name': 'deduplicated', 'count': len({c['case_id'] for c in cases}), 'sample_ids': sorted({c['case_id'] for c in cases})},
            {'name': 'in_scope', 'count': len(expected), 'sample_ids': expected,
             'excluded': [{'sample_id': c['case_id'], 'reason': 'OUTSIDE_DECLARED_PARTITION'} for c in cases if c['case_id'] not in set(expected)]},
            {'name': 'evidence_checked', 'count': len(enough), 'sample_ids': enough},
            {'name': 'expected_evaluation', 'count': len(eligible), 'sample_ids': eligible},
            {'name': 'received', 'count': len(answer_check['valid_ids']) if run.verify_answers else len(retrieval_check['valid_ids']),
             'sample_ids': answer_check['valid_ids'] if run.verify_answers else retrieval_check['valid_ids']},
            {'name': 'valid_binary_decision', 'count': binary, 'sample_ids': sorted(states['PASS'] + states['FAIL'])}],
        'complete': retrieval_check['complete'] and (not run.verify_answers or answer_check['complete'])}
    flow['partial_pass_rate']=deepcopy(flow['machine_pass_rate'])
    flow['publication_status']='COMPLETE' if flow['complete'] else 'INCOMPLETE'
    if not flow['complete']:
        flow['machine_pass_rate']={'numerator':len(states['PASS']),'denominator':binary,'value':None,'reason':'RESULT_RECONCILIATION_INCOMPLETE'}
    flow['historical_recheck_required']=run.controls.get('trust_contract_version')!='EVIDENCE_CONTRACT_V2'
    traces=[t for row in rows for t in row.get('provider_call_traces',[])]
    usages=[t.get('usage') for t in traces]
    known=[u for u in usages if isinstance(u,dict) and isinstance(u.get('total_tokens'),(int,float))]
    latencies=[r.get('case_latency_ms') for r in rows]
    flow['cost']={'actual_requests':run.provider_call_count,
        'known_token_requests':len(known),'unknown_usage_requests':max(0,run.provider_call_count-len(known)),
        'known_total_tokens':sum(u['total_tokens'] for u in known) if known else None,
        'case_latency_ms':sum(latencies) if latencies and all(isinstance(v,(int,float)) for v in latencies) else None,
        'currency_cost':None,'price_status':'UNKNOWN','retries_included_in_actual_requests':True}
    return flow


def comparison_trust(before, after, answers_a, answers_b, comparable):
    a, b = sample_flow(before, answers_a), sample_flow(after, answers_b)
    expected_a, expected_b = set(before.execution_order), set(after.execution_order)
    binary_a = set(a['states']['PASS']['sample_ids'] + a['states']['FAIL']['sample_ids'])
    binary_b = set(b['states']['PASS']['sample_ids'] + b['states']['FAIL']['sample_ids'])
    common = sorted(binary_a & binary_b) if comparable else []
    states_a = {identifier: key for key, values in a['states'].items() for identifier in values['sample_ids']}
    states_b = {identifier: key for key, values in b['states'].items() for identifier in values['sample_ids']}
    transitions = [{'sample_id': identifier, 'before': states_a.get(identifier), 'after': states_b.get(identifier),
                    'comparable': identifier in common} for identifier in sorted(expected_a | expected_b)]
    coverage_a, coverage_b = a['coverage']['value'], b['coverage']['value']
    declined = bool(coverage_a is not None and coverage_b is not None and coverage_b < coverage_a)
    lost = sorted(binary_a - binary_b)
    reasons = []
    if not comparable: reasons.append('CONTROL_CONDITIONS_CHANGED')
    if not a['complete'] or not b['complete']: reasons.append('RESULT_RECONCILIATION_INCOMPLETE')
    if expected_a != expected_b: reasons.append('DECLARED_SCOPE_CHANGED')
    if before.verify_answers != after.verify_answers: reasons.append('EVALUATION_MODE_CHANGED')
    if declined or lost: reasons.append('VALID_DECISION_COVERAGE_DECLINED')
    if before.verify_answers and (binary_a != expected_a or binary_b != expected_b): reasons.append('NOT_ALL_EXPECTED_SAMPLES_HAVE_VALID_DECISIONS')
    if not before.verify_answers: reasons.append('ANSWER_QUALITY_NOT_EVALUATED')
    regressions = [v['sample_id'] for v in transitions if v['before'] == 'PASS' and v['after'] == 'FAIL']
    if regressions: reasons.append('ANSWER_REGRESSIONS_REQUIRE_REVIEW')
    allowed = not reasons
    paired_before = _ratio(sum(states_a[v] == 'PASS' for v in common), len(common))
    paired_after = _ratio(sum(states_b[v] == 'PASS' for v in common), len(common))
    return {'schema_version': SCHEMA, 'baseline': a, 'retest': b,
        'full_scope': {'sample_ids': sorted(expected_a | expected_b), 'baseline_ids': sorted(expected_a),
                       'retest_ids': sorted(expected_b), 'added_ids': sorted(expected_b - expected_a), 'removed_ids': sorted(expected_a - expected_b),
                       'state_transitions': transitions},
        'common_subset': {'sample_ids': common, 'count': len(common), 'baseline_pass_rate': paired_before, 'retest_pass_rate': paired_after,
                          'improved_ids': [v for v in common if states_a[v] == 'FAIL' and states_b[v] == 'PASS'],
                          'regressed_ids': regressions, 'unchanged_ids': [v for v in common if states_a[v] == states_b[v]]},
        'coverage_declined': declined, 'lost_valid_decision_ids': lost,
        'overall_improvement_allowed': allowed, 'adoption_allowed': allowed,
        'restriction_reasons': reasons, 'causal_attribution_allowed': False,
        'claim_scope': 'FULL_EXPECTED_SCOPE_OBSERVED_ONLY' if allowed else 'COMMON_SUBSET_ONLY_WITH_RESTRICTIONS'}
