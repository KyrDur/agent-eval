"""Versioned, exact-source coverage. Inclusion is not semantic correctness."""
from pydantic import Field, model_validator
from typing import Literal
from .retrieval_models import InputModel
from .canonical import text_hash


class SourceEvidence(InputModel):
    document_id: str = Field(min_length=1, max_length=128)
    quote: str = Field(min_length=1, max_length=10000)
    source_hash: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')
    source_start: int | None = Field(default=None,ge=0,strict=True)
    source_end: int | None = Field(default=None,ge=0,strict=True)
    offset_unit: Literal['UNICODE_CODEPOINT'] | None = None
    knowledge_version: int | None = Field(default=None,ge=1)

    @model_validator(mode='after')
    def valid_location(self):
        located=self.source_start is not None or self.source_end is not None
        if located and (self.source_start is None or self.source_end is None or self.source_end<=self.source_start or self.offset_unit!='UNICODE_CODEPOINT'):
            raise ValueError('SOURCE_LOCATION_INVALID')
        return self


class RequiredFact(InputModel):
    fact_id: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=2000)
    review_action: Literal['MATCH','EDIT','UNCERTAIN'] | None = None
    draft_origin: Literal['EXACT_REFERENCE_SOURCE_MATCH'] | None = None
    # OR between alternatives; AND between passages within one alternative.
    alternatives: list[list[SourceEvidence]] = Field(default_factory=list, max_length=12)

    @model_validator(mode='after')
    def bounded(self):
        if any(not a or len(a)>12 for a in self.alternatives):
            raise ValueError('FACT_EVIDENCE_INVALID')
        return self


class RequirementSet(InputModel):
    facts: list[RequiredFact] = Field(default_factory=list, max_length=30)
    review_status: Literal['DRAFT','CONFIRMED'] = 'DRAFT'
    reviewer: str = Field(default='', max_length=100)
    reviewed_at: str | None = None
    reviewed_answer_hash: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')
    source: Literal['USER','AI','CODEX'] = 'USER'
    origin_source: Literal['USER','AI','CODEX'] | None = None
    expected_behavior: Literal['ANSWER','CLARIFY','UNSUPPORTED','HANDOFF'] = 'ANSWER'
    user_information: Literal['SUFFICIENT','NEEDS_CLARIFICATION','UNKNOWN'] = 'UNKNOWN'
    scope: Literal['IN_SCOPE','OUT_OF_SCOPE','CONFLICT'] = 'IN_SCOPE'

    @model_validator(mode='after')
    def reviewed(self):
        if sum(len(e.quote) for f in self.facts for a in f.alternatives for e in a)>120000:
            raise ValueError('FACT_EVIDENCE_TOO_LARGE')
        if len({f.fact_id for f in self.facts}) != len(self.facts):
            raise ValueError('DUPLICATE_FACT_ID')
        if self.review_status=='CONFIRMED' and (not self.reviewer.strip() or self.source!='USER'):
            raise ValueError('HUMAN_REVIEW_DECLARATION_REQUIRED')
        return self


def included_quote(e,doc,chunks):
    from .retrieval_knowledge import normalize
    matches=[c for c in chunks if c['document_id']==e.document_id]
    if any(normalize(e.quote) in normalize(c['text']) for c in matches):return True
    # Joint adjacent/overlapping original spans can contain one fact. Only trust
    # offsets after validating the exact frozen original text, hash and unit.
    raw=doc['text'];spans=[]
    for c in matches:
        a,b=c.get('source_start'),c.get('source_end')
        if (isinstance(a,int) and isinstance(b,int) and 0<=a<b<=len(raw) and
            c.get('source_hash')==text_hash(raw) and c.get('offset_unit')=='UNICODE_CODEPOINT' and raw[a:b]==c['text']):
            spans.append((a,b))
    merged=[]
    for a,b in sorted(spans):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    start=raw.find(e.quote)
    while start>=0:
        if any(a<=start and start+len(e.quote)<=b for a,b in merged):return True
        start=raw.find(e.quote,start+1)
    return False


def coverage(requirements, documents, chunks=None):
    req=RequirementSet.model_validate(requirements or {})
    docs={d['document_id']:d for d in documents}
    facts=[]
    for fact in req.facts:
        alternatives=[]
        for alternative in fact.alternatives:
            checks=[]
            for e in alternative:
                doc=docs.get(e.document_id)
                exists=bool(doc and e.quote in doc['text'])
                if exists and e.source_start is not None:
                    exists=doc['text'][e.source_start:e.source_end]==e.quote
                drift=bool(doc and e.source_hash and text_hash(doc['text'])!=e.source_hash)
                if chunks is not None:
                    included=bool(doc and included_quote(e,doc,chunks))
                else: included=exists
                checks.append({'document_id':e.document_id,'quote':e.quote,
                    'present_in_source':exists,'version_conflict':drift,
                    'included':exists and not drift and included})
            alternatives.append(checks)
        supported=any(all(c['included'] for c in a) for a in alternatives)
        facts.append({'fact_id':fact.fact_id,'description':fact.description,'included':supported,
            'alternatives':alternatives,'stale_reference_count':sum(c['version_conflict'] for a in alternatives for c in a)})
    count=sum(f['included'] for f in facts)
    conflict=req.scope=='CONFLICT' or any(not f['included'] and any(c['version_conflict'] for a in f['alternatives'] for c in a) for f in facts)
    status=('UNREVIEWED' if req.review_status!='CONFIRMED' else
        'OUT_OF_SCOPE' if req.scope=='OUT_OF_SCOPE' else 'CONFLICT' if conflict else
        'UNREVIEWED' if not facts else
        'FULL' if count==len(facts) else 'PARTIAL' if count else 'MISSING')
    eligible=req.review_status=='CONFIRMED' and bool(facts) and req.scope=='IN_SCOPE' and not conflict
    return {'schema_version':'RAG_COVERAGE_V1','status':status,'facts':facts,
        'included_count':count,'required_count':len(facts),
        'coverage':count/len(facts) if eligible else None,
        'review_status':req.review_status,'reviewer':req.reviewer,'source':req.source,'origin_source':req.origin_source,
        'expected_behavior':req.expected_behavior,'user_information':req.user_information,
        'method':'EXACT_SOURCE_INCLUSION_NOT_SEMANTIC_JUDGMENT'}


def evidence_path(requirements, documents, row,index_chunks=None):
    stages={'knowledge':coverage(requirements,documents),
        'chunks':coverage(requirements,documents,index_chunks) if index_chunks is not None else {'status':'NOT_CHECKED','coverage':None},
        'candidates':coverage(requirements,documents,row.get('pre_rerank_results',[])),
        'selected':coverage(requirements,documents,row.get('selected_results',row.get('results',[]))),
        'context':coverage(requirements,documents,row.get('results',[]))}
    if row.get('status')!='SUCCESS':
        for name in ('candidates','selected','context'):
            stages[name].update(status='NOT_CHECKED',coverage=None)
    return stages


def summarize(rows):
    rows=[r for r in rows if r.get('partition','DEBUG')=='DEBUG']
    stages={}
    for stage in ('knowledge','chunks','candidates','selected','context'):
        values=[r.get('evidence_path',{}).get(stage,{}) for r in rows]
        usable=[c for r,c in zip(rows,values) if c.get('coverage') is not None and (stage=='knowledge' or r.get('status')=='SUCCESS')]
        stages[stage]={'confirmed_eligible_count':len(usable),'total_case_count':len(rows),
            'mean_inclusion':sum(c['coverage'] for c in usable)/len(usable) if usable else None,
            'full_count':sum(c.get('status')=='FULL' for c in usable),'unreviewed_or_unavailable_count':len(rows)-len(usable)}
    return {'method':'EXACT_SOURCE_INCLUSION_NOT_SEMANTIC_JUDGMENT','stages':stages}


def paired_summary(left,right):
    a={r['case_id']:r for r in left};b={r['case_id']:r for r in right};stages={}
    for stage in ('knowledge','chunks','candidates','selected','context'):
        pairs=[]
        for case_id in sorted(a.keys()&b.keys()):
            x,y=a[case_id],b[case_id]
            cx=x.get('evidence_path',{}).get(stage,{}).get('coverage');cy=y.get('evidence_path',{}).get(stage,{}).get('coverage')
            if cx is not None and cy is not None and (stage=='knowledge' or x.get('status')==y.get('status')=='SUCCESS'):
                pairs.append((cx,cy))
        stages[stage]={'common_confirmed_cases':len(pairs),'baseline_mean':sum(x for x,y in pairs)/len(pairs) if pairs else None,
            'retest_mean':sum(y for x,y in pairs)/len(pairs) if pairs else None,'improved_count':sum(y>x for x,y in pairs),'regressed_count':sum(y<x for x,y in pairs)}
    return {'scope':'COMMON_CONFIRMED_FACT_CASES','stages':stages}
