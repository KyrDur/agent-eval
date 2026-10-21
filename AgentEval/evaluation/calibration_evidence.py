"""Deterministic, source-bound fragments; existence is not semantic support."""
import hashlib
import json


def evidence_fragments(sample):
    sources = [('ANSWER', None, sample.answer)]
    sources += [(scope, e.evidence_id, e.text) for scope, items in
                [('RETRIEVED', sample.retrieved_evidence), ('REFERENCE', sample.reference_policy)]
                for e in items]
    fragments = []
    for scope, evidence_id, source in sources:
        source_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()
        identity = hashlib.sha256(json.dumps([scope, evidence_id, source], ensure_ascii=False).encode('utf-8')).hexdigest()[:16]
        start = 0
        while start < len(source):
            end = min(start + 500, len(source))
            if end < len(source):
                boundary = max(source.rfind(mark, start, end) for mark in ('。', '！', '？', '\n', ';', '；'))
                if boundary >= start:
                    end = boundary + 1
            text = source[start:end]
            left = start + len(text) - len(text.lstrip())
            right = end - len(text) + len(text.rstrip())
            if right > left:
                prefix = {'ANSWER': 'A', 'RETRIEVED': 'R', 'REFERENCE': 'P'}[scope]
                fragments.append({'fragment_id': f'{prefix}-{identity}-{left}-{right}', 'scope': scope,
                                  'evidence_id': evidence_id, 'text': source[left:right],
                                  'start': left, 'end': right, 'source_sha256': source_hash})
            start = end
    return fragments


def fragment_input(sample):
    # Partition, historical scores and author identities never enter the Judge input.
    return {k: getattr(sample, k) for k in ('question', 'context', 'expected_facts', 'reference_complete')} | {
        'fragment_catalog': [{k: f[k] for k in ('fragment_id', 'scope', 'evidence_id', 'text')}
                             for f in evidence_fragments(sample)]}


def resolve_fragment_judgment(data, sample):
    """Expand IDs from this sample only, with source positions retained for auditing."""
    if not isinstance(data, dict) or not isinstance(data.get('dimensions'), dict):
        raise ValueError('FRAGMENT_SCHEMA_INVALID')
    catalog = {f['fragment_id']: f for f in evidence_fragments(sample)}
    normalized = dict(data)
    normalized['dimensions'] = {}
    provenance = []
    for dimension, value in data['dimensions'].items():
        if not isinstance(value, dict) or set(value) != {'score', 'answer_fragment_ids', 'evidence_fragment_ids', 'reason'}:
            raise ValueError('FRAGMENT_SCHEMA_INVALID')
        selected = {}
        for field, limit in [('answer_fragment_ids', 10), ('evidence_fragment_ids', 20)]:
            ids = value[field]
            if not isinstance(ids, list) or len(ids) > limit or any(not isinstance(i, str) for i in ids):
                raise ValueError('FRAGMENT_SCHEMA_INVALID')
            if len(set(ids)) != len(ids):
                raise ValueError('FRAGMENT_ID_DUPLICATED')
            selected[field] = []
            for identifier in ids:
                fragment = catalog.get(identifier)
                if fragment is None:
                    raise ValueError('FRAGMENT_ID_INVALID')
                if (fragment['scope'] == 'ANSWER') != (field == 'answer_fragment_ids'):
                    raise ValueError('FRAGMENT_SCOPE_INVALID')
                selected[field].append(fragment)
                provenance.append({'dimension': dimension, **fragment})
        normalized['dimensions'][dimension] = {
            'score': value['score'], 'reason': value['reason'],
            'answer_quotes': [f['text'] for f in selected['answer_fragment_ids']],
            'citations': [{'scope': f['scope'], 'evidence_id': f['evidence_id'], 'quote': f['text']}
                          for f in selected['evidence_fragment_ids']]}
    return normalized, provenance
