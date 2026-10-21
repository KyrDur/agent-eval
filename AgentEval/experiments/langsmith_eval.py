"""Optional LangSmith adapter for the product's actual grounded RAG pipeline.

Credentials stay in this process. Knowledge, examples and results are frozen and
hashed, while each invocation uses an independent provider client and history.
This module is not imported by the web application.
"""
import argparse
import asyncio
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import time
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

from core.llm_utils import extract_text_content
from evaluation.calibration import (
    BASE_PROMPT, VERIFY_PROMPT, FRAGMENT_PROMPT, FRAGMENT_VERIFY_PROMPT,
    RUBRIC_TEMPLATE, score_answer, final_verdict, check_judgment,
)
from evaluation.calibration_evidence import evidence_fragments, resolve_fragment_judgment
from .calibration_models import CalibrationSample, RubricVersion, CalibrationResult, Judgment
from .canonical import digest
from .models import now
from .provider_transport import ObservedProvider
from .provider_trace import usage_for
from .providers import ProviderConfig, ProviderFailure
from .retrieval_knowledge import FrozenKnowledge
from .retrieval_metrics import METRICS, case_metrics
from .retrieval_models import RetrievalCase, RetrievalConfig
from .retrieval_runtime import grounded_answer, pipeline_snapshot, retrieve_context
from .store import JsonStore, safe_artifact

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path.home() / '.config/agent-eval/langsmith.env'
DEFAULT_DATA = ROOT / 'examples/langsmith/ecommerce.json'
VERDICT_INSTRUCTIONS = '''\n最终规则须机械应用：critical_errors 非空则 FAIL；否则任一维度为 INSUFFICIENT 或不允许的 NA 则 PENDING；否则任一数值分数低于 minimum_scores 则 FAIL；全部满足最低分才 PASS。faithfulness 和 conditions 的最低分均为 2，打 1 分应为 FAIL，不能因为部分信息不足就改成 PENDING。只有分数明确为 INSUFFICIENT 时才适用弃判规则。'''
from .evidence_judge import ALIAS_PROMPT, alias_sample_input, normalize_alias_judgment, score_alias_answer


def read_config(path):
    """Read literal KEY=value lines; never execute a shell credential file."""
    values = dict(os.environ)
    if path.exists():
        if path.stat().st_mode & 0o077:
            raise ValueError('CONFIG_PERMISSIONS_REQUIRE_600')
        for line in path.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            key, separator, value = line.partition('=')
            if not separator or not key.strip().replace('_', '').isalnum():
                raise ValueError('CONFIG_LINE_INVALID')
            value = value.strip()
            if value[:1] in ('"', "'"):
                if value[-1:] != value[:1]:
                    raise ValueError('CONFIG_QUOTE_INVALID')
                value = value[1:-1]
            values.setdefault(key.strip(), value)
    return values


def provider_config(values, judge=False):
    prefix = 'AGENTEVAL_JUDGE_' if judge else 'AGENTEVAL_MODEL_'
    independent = judge and bool(values.get(prefix + 'API_KEY'))
    if not independent:
        prefix = 'AGENTEVAL_MODEL_'
    config = ProviderConfig(
        provider=values.get(prefix + 'PROVIDER') or 'openai-compatible',
        model=values.get(prefix + 'MODEL') or values.get('AGENTEVAL_MODEL', 'deepseek-chat'),
        base_url=values.get(prefix + 'BASE_URL') or 'https://api.deepseek.com/v1',
        temperature=float(values.get('AGENTEVAL_TEMPERATURE') or 0),
        max_tokens=int(values.get('AGENTEVAL_MAX_TOKENS') or 2200),
        completion_token_parameter=values.get('AGENTEVAL_TOKEN_PARAMETER') or 'max_tokens',
        thinking_mode='disabled' if 'deepseek.com' in (values.get(prefix + 'BASE_URL') or 'https://api.deepseek.com/v1') else None,
        timeout_seconds=90, max_calls=4,
    )
    key = values.get(prefix + 'API_KEY', '')
    if len(key) < 8 or any(c.isspace() for c in key):
        raise ValueError('MODEL_KEY_MISSING_OR_INVALID')
    return config, key, independent


def load_data(path, limit):
    data = json.loads(path.read_text())
    cases = [RetrievalCase.model_validate(c) for c in data['cases']]
    if not cases or len(cases) > 100 or len({c.case_id for c in cases}) != len(cases):
        raise ValueError('DATASET_CASE_IDS_INVALID')
    data['cases'] = [c.model_dump(mode='json') for c in cases[:limit]]
    return data


def examples_for(data, content_hash):
    """Reference answers never enter the generation function's inputs."""
    return [
        {
            'id': str(uuid5(NAMESPACE_URL, f'agent-eval:{content_hash}:{case["case_id"]}')),
            'inputs': {'case_id': case['case_id'], 'query': case['query'], 'context': case['context']},
            'outputs': {k: case[k] for k in (
                'expected_answer', 'relevant_document_ids', 'relevant_chunk_ids',
                'must_do', 'must_not_do', 'scenario', 'partition',
            )},
            'metadata': {'source': case['source'], 'content_hash': content_hash,
                         'reference_type': 'AUTHORED_EXPECTATION_NOT_HUMAN_ANNOTATION'},
        }
        for case in data['cases']
    ]


def judge_feedback(result):
    """Invalid Judge results and abstentions are not converted to passes."""
    feedback = [{'key': 'judge_status', 'value': result.status,
                 'comment': result.error or 'Existing Agent Eval judgment validation passed.'}]
    if result.status != 'SUCCESS' or result.judgment is None:
        return feedback + [{'key': 'verdict', 'value': 'UNAVAILABLE', 'comment': result.error or result.status}]
    judgment = result.judgment
    for name, item in judgment.dimensions.items():
        entry = {'key': name, 'comment': item.reason}
        if type(item.score) is int:
            entry['score'] = item.score
        else:
            # NA and INSUFFICIENT are recorded separately, without a numeric score.
            entry['value'] = item.score
        feedback.append(entry)
    feedback.extend([
        {'key': 'verdict', 'value': judgment.verdict, 'comment': judgment.reason},
        {'key': 'task_resolved', 'value': judgment.task_resolved},
        {'key': 'faithful_to_available', 'value': judgment.faithful_to_available},
        {'key': 'critical_errors', 'value': ','.join(judgment.critical_errors) or 'NONE'},
    ])
    if judgment.verdict in ('PASS', 'FAIL'):
        feedback.append({'key': 'answer_pass', 'score': int(judgment.verdict == 'PASS')})
    return feedback


def expected_run_feedback(answer, saved_judgment=None):
    feedback = [{'key': name, 'score': answer['retrieval_metrics'][name]}
                for name in METRICS if answer['retrieval_metrics'][name] is not None]
    if saved_judgment:
        result = SimpleNamespace(status=saved_judgment['status'], error=saved_judgment['error'],
            judgment=Judgment.model_validate(saved_judgment['judgment']) if saved_judgment['judgment'] else None)
        feedback.extend(judge_feedback(result))
    return feedback


def feedback_matches(record, expected):
    # LangSmith persists numeric scores to four decimal places. Keep full
    # precision locally, and allow only that observed storage rounding here.
    actual, score = record.score, expected.get('score')
    numeric_match = (actual is None and score is None) or (
        actual is not None and score is not None
        and math.isclose(actual, score, rel_tol=0, abs_tol=0.000050000001))
    return numeric_match and record.value == expected.get('value')


def ensure_cloud_feedback(client, project_id, expected):
    """SDK background feedback exceptions can be lost: read back every value."""
    records = list(client.list_feedback(run_ids=list(expected)))
    received = {(str(r.run_id), r.key): r for r in records}
    repaired = 0
    for run_id, items in expected.items():
        for item in items:
            found = received.get((run_id, item['key']))
            if found is not None:
                if not feedback_matches(found, item):
                    raise ValueError('CLOUD_FEEDBACK_VALUE_MISMATCH')
                continue
            # Do not redefine workspace-wide feedback configuration. Raw scores
            # keep their 0/1/2 meaning; unknown/NA values stay categorical.
            client.create_feedback(run_id, session_id=project_id,
                feedback_id=str(uuid5(NAMESPACE_URL, f'agent-eval:{run_id}:{item["key"]}')),
                feedback_source_type='api' if item['key'] in METRICS else 'model',
                source_info={'adapter': 'Agent Eval LangSmith', 'reconciled_from_saved_original_result': True},
                **{k: v for k, v in item.items() if k in ('key', 'score', 'value', 'comment')})
            repaired += 1
    records = list(client.list_feedback(run_ids=list(expected)))
    received = {(str(r.run_id), r.key): r for r in records}
    verified = all(
        (run_id, item['key']) in received
        and feedback_matches(received[(run_id, item['key'])], item)
        for run_id, items in expected.items() for item in items)
    return {'cloud_feedback_verified': verified,
            'expected_feedback_count': sum(len(items) for items in expected.values()),
            'cloud_feedback_count': len(records), 'feedback_repaired': repaired}


class TracedProvider:
    """Trace sanitized model requests and token usage using the existing transport."""
    def __init__(self, provider, client):
        self.provider, self.client_instance = provider, client

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def client(self, role):
        from langsmith import traceable
        delegate = self.provider.client(role)
        model = self.provider.config.resolved()[role]['model']

        def output(response):
            usage = usage_for(self.provider._sdk, response)
            result = {
                'choices': [{'message': {'role': 'assistant', 'content': extract_text_content(response.content)}}],
                'model': response.model,
            }
            if usage and usage.get('input_tokens') is not None and usage.get('output_tokens') is not None:
                result['usage'] = {'prompt_tokens': usage['input_tokens'],
                                   'completion_tokens': usage['output_tokens']}
            return result

        @traceable(name=f'{role}.model', run_type='llm', client=self.client_instance,
                   metadata={'ls_model_name': model, 'ls_provider': self.provider.config.provider},
                   process_outputs=output)
        async def create(**kwargs):
            return await delegate.messages.create(**kwargs)

        return SimpleNamespace(messages=SimpleNamespace(create=create))


async def run(args, values):
    from langsmith import Client, traceable, tracing_context
    model_config, model_key, _ = provider_config(values)
    judge_config, judge_key, independent_judge = provider_config(values, judge=True)
    ls_key = values.get('LANGSMITH_API_KEY', '')
    if len(ls_key) < 8 or any(c.isspace() for c in ls_key):
        raise ValueError('LANGSMITH_KEY_MISSING_OR_INVALID')
    secrets = tuple({model_key, judge_key, ls_key})
    for name in ('langsmith', 'httpx', 'httpcore', 'urllib3'):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    trace_errors = []
    def trace_error(error):
        detail = str(error)
        for secret in secrets:
            detail = detail.replace(secret, '[REDACTED]')
        trace_errors.append({'type': type(error).__name__, 'detail': detail[:1200]})
        print('Trace upload error: ' + detail[:1200], flush=True)

    client = Client(api_key=ls_key, api_url=values.get('LANGSMITH_ENDPOINT') or 'https://api.smith.langchain.com',
                    workspace_id=values.get('LANGSMITH_WORKSPACE_ID') or None, timeout_ms=30000,
                    auto_batch_tracing=False, tracing_error_callback=trace_error)
    try:
        # Authenticate before any billable model calls or dataset creation.
        await asyncio.to_thread(lambda: next(iter(client.list_datasets(limit=1)), None))
        if args.check:
            print(json.dumps({'langsmith_authenticated': True, 'model': model_config.model,
                              'independent_judge': independent_judge}, ensure_ascii=False))
            return 0
        data = load_data(args.data, args.limit)
        safe_artifact(data, secrets)
        content_hash = digest({'documents': data['documents'], 'cases': data['cases']})
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        run_dir = args.output / f'{timestamp}-{content_hash[:8]}'
        run_dir.mkdir(parents=True, exist_ok=False)
        store = JsonStore(run_dir / 'knowledge', forbidden_values=secrets)
        knowledge = FrozenKnowledge(store)
        dataset = knowledge.create(data['documents'], data['name'])
        print('Building frozen knowledge index...', flush=True)
        index = await asyncio.to_thread(knowledge.build, dataset.knowledge_dataset_id, 1, None, args.embedding)
        config = RetrievalConfig(top_k=args.top_k, query_rewrite=args.rewrite, rerank=args.rerank)
        rubric = RubricVersion(**deepcopy(RUBRIC_TEMPLATE), content_hash=digest(RUBRIC_TEMPLATE))
        fragments = args.judge_protocol == 'fragments'
        protocol = SimpleNamespace(
            output_schema='CALIBRATION_FRAGMENT_JUDGMENT_V2' if fragments else 'CALIBRATION_JUDGMENT_V1',
            prompt=ALIAS_PROMPT if fragments else (BASE_PROMPT + VERIFY_PROMPT + VERDICT_INSTRUCTIONS),
            examples=[],
        )
        examples = examples_for(data, content_hash)
        dataset_name = args.dataset_name or f'Agent Eval 电商 RAG · {content_hash[:12]}'
        if client.has_dataset(dataset_name=dataset_name):
            ls_dataset = client.read_dataset(dataset_name=dataset_name)
            if (ls_dataset.metadata or {}).get('agent_eval_content_hash') != content_hash:
                raise ValueError('LANGSMITH_DATASET_CONTENT_MISMATCH')
            existing = list(client.list_examples(dataset_id=ls_dataset.id))
            expected = {e['id']: e for e in examples}
            if len(existing) != len(examples) or any(
                str(e.id) not in expected or e.inputs != expected[str(e.id)]['inputs']
                or e.outputs != expected[str(e.id)]['outputs'] for e in existing
            ):
                raise ValueError('LANGSMITH_DATASET_EXAMPLES_CHANGED')
        else:
            ls_dataset = client.create_dataset(dataset_name, description='Agent Eval 冻结电商知识问答测试集；演示政策不代表真实商家承诺。',
                metadata={'agent_eval_content_hash': content_hash, 'source': data.get('source', str(args.data)),
                          'knowledge_hash': dataset.knowledge_hash})
            client.create_examples(dataset_id=ls_dataset.id, examples=examples)
        cases = {c['case_id']: RetrievalCase.model_validate(c) for c in data['cases']}
        acquired, judgments = {}, {}
        safe_artifact({'model': model_config.model_dump(), 'judge': judge_config.model_dump()}, secrets)

        @traceable(name='电商 Agent · 检索与回答', client=client,
                   process_inputs=lambda inputs: inputs['inputs'])
        async def target(inputs):
            case_id = inputs['case_id']
            provider = ObservedProvider(model_config, model_key)
            traced = TracedProvider(provider, client)
            try:
                retrieve = traceable(retrieve_context, name='RAG · 检索改写与重排', run_type='retriever', client=client,
                                     process_inputs=lambda _: {'query': inputs['query'], 'context': inputs['context'],
                                                               'index_id': index.index_id, 'config': config.model_dump()})
                row = await retrieve(knowledge, index, traced, inputs['query'], config,
                                     pipeline_snapshot(model_config), inputs['context'])
                if row['status'] != 'SUCCESS':
                    raise ProviderFailure(row['error'] or 'RETRIEVAL_EXECUTION_FAILED')
                answer = await grounded_answer(traced, inputs['query'], row['results'], inputs['context'])
                metrics = case_metrics(cases[case_id], row['results'], config.top_k, row['post_rerank_results'])
                result = {'answer': answer, 'retrieved_evidence': row['results'], 'retrieval': row,
                          'retrieval_metrics': metrics, 'provider_observations': provider.observations,
                          'provider_call_count': provider.call_count, 'status': 'SUCCESS'}
                safe_artifact(result, secrets)
                acquired[case_id] = result
                print(f'Answer acquired: {case_id}', flush=True)
                return result
            finally:
                await provider.close()

        def retrieval_scores(outputs):
            return {'results': [{'key': name, 'score': outputs['retrieval_metrics'][name]}
                                for name in METRICS if outputs['retrieval_metrics'][name] is not None]}

        async def judge(inputs, outputs, reference_outputs):
            sample = CalibrationSample(
                sample_id=inputs['case_id'], group_id=inputs['case_id'], partition='CALIBRATION',
                question=inputs['query'], context=inputs['context'], answer=outputs['answer'],
                retrieved_evidence=[{'evidence_id': e['chunk_id'], 'document_id': e['document_id'], 'text': e['text']}
                                    for e in outputs['retrieved_evidence']],
                reference_policy=[{'evidence_id': d['document_id'], 'document_id': d['document_id'], 'text': d['text']}
                                  for d in dataset.documents], reference_complete=True,
                expected_facts=[*(reference_outputs.get('must_do') or []),
                                *([reference_outputs['expected_answer']] if reference_outputs.get('expected_answer') else [])],
                origin='CONSTRUCTED', provenance={'source': data.get('source', 'EXPLICIT_DATA_FILE')},
            )
            provider = ObservedProvider(judge_config, judge_key)
            try:
                traced = TracedProvider(provider, client)
                result = (await score_alias_answer(traced, rubric, sample) if fragments
                          else await score_answer(traced, protocol, rubric, sample, 1))
                saved = result.model_dump(mode='json')
                saved['verdict_source'] = 'DETERMINISTIC_RUBRIC_RULES' if fragments else 'MODEL_WITH_RULE_VALIDATION'
                safe_artifact(saved, secrets)
                judgments[inputs['case_id']] = saved
                print(f'Judge: {inputs["case_id"]} {result.status} '
                      f'{result.judgment.verdict if result.judgment else result.error}', flush=True)
                return {'results': judge_feedback(result)}
            finally:
                await provider.close()

        manifest = {
            'started_at': now(), 'content_hash': content_hash, 'knowledge_hash': dataset.knowledge_hash,
            'index_id': index.index_id, 'embedding_snapshot': index.embedding_snapshot,
            'retrieval_config': config.model_dump(), 'model_configuration': model_config.model_dump(),
            'judge_configuration': judge_config.model_dump(), 'independent_judge': independent_judge,
            'rubric_hash': rubric.content_hash, 'judge_prompt_hash': digest(protocol.prompt),
            'judge_protocol': args.judge_protocol, 'human_reference_count': 0,
            'judge_adapter_version': 'EXACT_FRAGMENT_ALIASES_AND_CODE_VERDICT_V1' if fragments else 'QUOTE_PROTOCOL_V1',
            'judge_calibration_status': 'INITIAL_UNVALIDATED', 'case_count': len(cases),
            'dataset_id': str(ls_dataset.id), 'dataset_name': ls_dataset.name,
        }
        safe_artifact(manifest, secrets)
        (run_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        with tracing_context(enabled=True, client=client, project_name=values.get('LANGSMITH_PROJECT', 'Agent Eval 电商评测')):
            results = await client.aevaluate(
                target, data=client.list_examples(dataset_id=ls_dataset.id),
                evaluators=[retrieval_scores] + ([] if args.no_judge else [judge]),
                experiment_prefix=args.experiment_prefix,
                description='运行 Agent Eval 原始 RAG 流程，检索指标和四维评分分别记录。',
                max_concurrency=args.concurrency,
                metadata={**manifest, 'models': [model_config.model, judge_config.model],
                          'prompts': [pipeline_snapshot(model_config)['answer']['prompt_hash'], manifest['judge_prompt_hash']]},
            )
        returned = [row async for row in results]
        acquisition = {'answers': acquired, 'judgments': judgments,
                       'runs': {str(row['run'].id): row['example'].inputs['case_id'] for row in returned}}
        safe_artifact(acquisition, secrets)
        (run_dir / 'acquisition.json').write_text(json.dumps(acquisition, ensure_ascii=False, indent=2) + '\n')
        errors = sum(bool(row['run'].error) for row in returned)
        valid_judgments = [j for j in judgments.values() if j['status'] == 'SUCCESS']
        verdicts = dict(Counter(j['judgment']['verdict'] for j in valid_judgments))
        successful = (len(returned) == len(cases) == len(acquired) and errors == 0
                      and (args.no_judge or len(valid_judgments) == len(cases)))
        await asyncio.to_thread(client.flush)
        session = client.read_project(project_name=results.experiment_name)
        expected_ids = {str(row['run'].id) for row in returned}
        cloud_ids = set()
        for attempt in range(6):
            cloud_runs = [r async for r in client.runs.query(
                project_ids=[str(session.id)], is_root=True, min_start_time=manifest['started_at'])]
            cloud_ids = {str(r.id) for r in cloud_runs}
            if expected_ids <= cloud_ids:
                break
            if attempt < 5:
                await asyncio.sleep(2)
        trace_verified = expected_ids <= cloud_ids
        expected_feedback = {str(row['run'].id): expected_run_feedback(
            acquired[row['example'].inputs['case_id']], judgments.get(row['example'].inputs['case_id']))
            for row in returned if row['example'].inputs['case_id'] in acquired}
        feedback_check = await asyncio.to_thread(ensure_cloud_feedback, client, str(session.id), expected_feedback)
        successful = successful and trace_verified and not trace_errors and feedback_check['cloud_feedback_verified']
        summary = {
            'status': 'COMPLETE' if successful else 'PARTIAL', 'finished_at': now(),
            'experiment_name': results.experiment_name, 'experiment_url': session.url,
            'dataset_url': ls_dataset.url, 'expected_cases': len(cases), 'returned_cases': len(returned),
            'answers_acquired': len(acquired), 'run_errors': errors,
            'cloud_root_runs_verified': trace_verified, 'trace_upload_errors': trace_errors,
            'root_run_ids': sorted(expected_ids), 'cloud_root_run_ids': sorted(cloud_ids),
            **feedback_check,
            'judge_success': len(valid_judgments), 'judge_unavailable': len(judgments) - len(valid_judgments),
            'verdict_counts': verdicts, 'human_reference_count': 0,
            'judge_calibration_status': 'INITIAL_UNVALIDATED', 'output_dir': str(run_dir),
        }
        bundle = {'manifest': manifest, 'summary': summary, 'answers': acquired, 'judgments': judgments}
        safe_artifact(bundle, secrets)
        (run_dir / 'results.json').write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + '\n')
        (run_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        await asyncio.to_thread(client.flush)
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        return 0 if successful else 1
    finally:
        await asyncio.to_thread(client.close)


def main():
    parser = argparse.ArgumentParser(description='在 LangSmith 运行 Agent Eval 电商 RAG 评测')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/langsmith')
    parser.add_argument('--dataset-name')
    parser.add_argument('--experiment-prefix', default='电商 RAG Baseline')
    parser.add_argument('--limit', type=int, choices=range(1, 101), default=8)
    parser.add_argument('--top-k', type=int, default=3)
    parser.add_argument('--embedding', choices=['all-MiniLM-L6-v2', 'sha256-lexical-bigram-v1'], default='all-MiniLM-L6-v2')
    parser.add_argument('--rewrite', action='store_true')
    parser.add_argument('--rerank', action='store_true')
    parser.add_argument('--no-judge', action='store_true')
    parser.add_argument('--judge-protocol', choices=['fragments', 'quotes'], default='fragments')
    parser.add_argument('--concurrency', type=int, choices=range(1, 5), default=2)
    parser.add_argument('--check', action='store_true', help='仅验证 LangSmith 鉴权，不创建数据或调用模型')
    args = parser.parse_args()
    try:
        values = read_config(args.config)
        return asyncio.run(run(args, values))
    except Exception as error:
        # Never print SDK exception bodies, keys or user request contents.
        message = error.code if isinstance(error, ProviderFailure) else type(error).__name__
        if isinstance(error, ValueError) and str(error).isupper():
            message = str(error)
        print(json.dumps({'status': 'FAILED', 'error': message}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
