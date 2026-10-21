"""Bounded model-call evidence, without credentials or HTTP headers."""
import math
import re
SENSITIVE = re.compile(r'(^|_)(api_key|authorization|secret|password|credential|access_token|refresh_token)($|_)', re.I)


def snapshot(value, secrets=(), limit=48000):
    remaining = limit
    flags = {'truncated': False, 'redacted': False}

    def visit(item, depth=0):
        nonlocal remaining
        if depth > 12:
            flags['truncated'] = True
            return '[内容过深，已省略]'
        if isinstance(item, str):
            for secret in secrets:
                if secret and secret in item:
                    flags['redacted'] = True
                    item = item.replace(secret, '[已隐藏凭据]')
            item, count = re.subn(r'(?i)bearer\s+[a-z0-9._-]{8,}|(?:sk-ant-|sk-|lsv2_)[a-z0-9_-]{8,}', '[已隐藏凭据]', item)
            flags['redacted'] |= bool(count)
            count = min(len(item), 12000, remaining)
            remaining -= count
            if count < len(item):
                flags['truncated'] = True
                return item[:count] + '\n[内容过长，已截取]'
            return item
        if isinstance(item, dict):
            result = {}
            for key, child in list(item.items())[:100]:
                key = str(key)
                normalized = re.sub(r'([a-z])([A-Z])', r'\1_\2', key)
                if SENSITIVE.search(normalized) or normalized.lower() == 'token':
                    flags['redacted'] = True
                    continue
                result[visit(key, depth+1)] = visit(child, depth+1)
            flags['truncated'] |= len(item) > 100
            return result
        if isinstance(item, (list, tuple)):
            flags['truncated'] |= len(item) > 100
            return [visit(child, depth+1) for child in item[:100]]
        if item is None or type(item) in (bool, int):
            return item
        if type(item) is float:
            return item if math.isfinite(item) else None
        if hasattr(item, 'model_dump'):
            return visit(item.model_dump(mode='json'), depth+1)
        flags['truncated'] = True
        return '[未保存此类型的内容]'

    return {'data': visit(value), **flags}


def operation(role, system):
    for prefix, name in [('RAG_REWRITE_V1', 'QUERY_REWRITE'), ('RAG_RERANK_V1', 'RERANK'), ('RAG_ANSWER_V1', 'ANSWER')]:
        if isinstance(system, str) and system.startswith(prefix):
            return name
    return 'JUDGE' if role == 'judge' else role.upper()


def usage_for(sdk, response):
    # OpenAI's internal Message has placeholder zeros; only last_usage is real.
    usage = getattr(sdk, 'last_usage', None) if hasattr(sdk, 'last_usage') else (
        response.usage.model_dump() if getattr(response, 'usage', None) is not None else None)
    if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0
                                         for k in ('input_tokens', 'output_tokens')):
        return None
    return {**usage, 'total_tokens': usage['input_tokens'] + usage['output_tokens']}
