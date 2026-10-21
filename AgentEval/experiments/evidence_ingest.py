"""Deterministic business-evidence projection. Raw records are never rewritten."""
import csv
import io
import json
import unicodedata
from copy import deepcopy
from .canonical import digest

FIELDS=('source_type','sample_id','question','answer','context','reference_policy','retrieved_evidence','reference_complete',
        'conversation_id','turn_id','object_ids','question_time','question_timezone','business_domain','tools',
        'tool_results','family_id','error_type','tool_expectations')
INTERNAL={'system','system_prompt','developer','developer_prompt','prompt','instructions','internal_prompt','tool_definition','chain_of_thought'}

def parse(content,format):
    if len(content.encode('utf-8'))>5*1024*1024:raise ValueError('IMPORT_TOO_LARGE')
    if format=='csv':
        reader=csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
        headers=reader.fieldnames or []
        if not headers or len(headers)!=len(set(headers)) or any(not str(h).strip() for h in headers):raise ValueError('IMPORT_CSV_HEADERS_INVALID')
        rows=list(reader)
    elif format=='jsonl':rows=[json.loads(line) for line in content.splitlines() if line.strip()]
    else:
        value=json.loads(content)
        if not isinstance(value,(list,dict)):raise ValueError('IMPORT_RECORDS_INVALID')
        rows=value if isinstance(value,list) else value.get('records',[value])
    if not isinstance(rows,list) or not 1<=len(rows)<=100 or any(not isinstance(r,dict) or any(not isinstance(k,str) for k in r) for r in rows):raise ValueError('IMPORT_RECORDS_INVALID')
    return rows

def get_path(row,path):
    if not path:return None
    if path in row:value=row[path]
    else:
        value=row
        for part in path.split('.'):
            if not isinstance(value,dict):return None
            value=value.get(part)
    if isinstance(value,str) and value.strip()[:1] in '[{':
        try:return json.loads(value)
        except ValueError:pass
    return value

def clean_tool(value,removed,path='',preserve=()):
    if isinstance(value,dict):
        result={}
        for k,v in value.items():
            position=path+'.'+k
            if k.lower() in INTERNAL and k.lower() not in preserve:removed.append(position)
            else:result[k]=clean_tool(v,removed,position,preserve)
        return result
    if isinstance(value,list):return [clean_tool(v,removed,path+f'[{i}]',preserve) for i,v in enumerate(value)]
    return value

def evidence(values,prefix):
    if values is None:return []
    if isinstance(values,str):values=[{'text':values}] if values.strip() else []
    if isinstance(values,dict):values=[values]
    if not isinstance(values,list):raise ValueError('IMPORT_EVIDENCE_INVALID')
    rows=[]
    for i,v in enumerate(values):
        if isinstance(v,str):v={'text':v}
        if not isinstance(v,dict) or not isinstance(v.get('text'),str) or not isinstance(v.get('metadata',{}),dict):raise ValueError('IMPORT_EVIDENCE_INVALID')
        rows.append({'evidence_id':str(v.get('evidence_id') or v.get('chunk_id') or v.get('document_id') or f'{prefix}{i+1}'),
            'document_id':str(v.get('document_id') or f'{prefix}{i+1}'),'text':v['text'],'metadata':v.get('metadata',{})})
    if len({v['evidence_id'] for v in rows})!=len(rows):raise ValueError('IMPORT_EVIDENCE_IDS_DUPLICATED')
    return rows

def project(raw,mapping,domain,history_mode='NECESSARY'):
    rows=[];seen={};duplicates=[]
    for number,original in enumerate(raw,1):
        values={k:get_path(original,mapping.get(k) or k) for k in FIELDS}
        original_hash=digest(original)
        # Exact duplicate records only; identical questions with distinct answers stay distinct.
        if original_hash in seen:
            duplicates.append({'source_row':number,'duplicate_of':seen[original_hash]});continue
        seen[original_hash]=number
        sid=str(values['sample_id'] or 'sample_'+original_hash[:16])
        issues=[];removed=[]
        question=unicodedata.normalize('NFKC',str(values['question'] or '')).strip()
        answer=values['answer'] if isinstance(values['answer'],str) else ''
        if not question or not answer.strip():issues.append('QUESTION_OR_ANSWER_MISSING')
        if len(question)>5000 or len(answer)>20000:issues.append('QUESTION_OR_ANSWER_TOO_LARGE')
        context=values['context'] or []
        if not isinstance(context,list):issues.append('CONTEXT_FORMAT_INVALID');context=[]
        history=[]
        for i,item in enumerate(context):
            if not isinstance(item,dict) or item.get('role') not in {'user','assistant'}:
                removed.append(f'context[{i}]');continue
            if not isinstance(item.get('content'),str):issues.append('CONTEXT_FORMAT_INVALID');continue
            history.append({'role':item['role'],'content':item['content']})
        full_history=deepcopy(history)
        if history_mode!='FULL':history=history[-4:]
        references=evidence(values['reference_policy'],'P');retrieved=evidence(values['retrieved_evidence'],'R')
        if len(history)>20 or sum(len(h['content']) for h in history)>50000:issues.append('SELECTED_HISTORY_TOO_LARGE')
        if len(references)>100 or len(retrieved)>100 or sum(len(v['text']) for v in references+retrieved)>500000:issues.append('EVIDENCE_TOO_LARGE')
        complete=values['reference_complete']
        if isinstance(complete,str):complete={'true':True,'false':False,'1':True,'0':False}.get(complete.lower())
        complete=complete if isinstance(complete,bool) else None
        metadata={k:values[k] for k in ('conversation_id','turn_id','object_ids','question_time','question_timezone') if values[k] is not None}
        for k in ('conversation_id','turn_id','question_time','question_timezone'):
            if k in metadata:metadata[k]=str(metadata[k])
        if not isinstance(metadata.get('object_ids',{}),dict):issues.append('OBJECT_FORMAT_INVALID');metadata.pop('object_ids',None)
        tools=values['tools'] or [];tool_results=values['tool_results'] or []
        if not isinstance(tools,list) or not isinstance(tool_results,list):issues.append('TOOL_FORMAT_INVALID');tools=[];tool_results=[]
        result_by_id={}
        for item in tool_results:
            if isinstance(item,dict) and item.get('call_id'):
                result_by_id.setdefault(str(item['call_id']),[]).append(item)
            else:issues.append('TOOL_RESULT_ID_MISSING')
        cleaned=[]
        for i,tool in enumerate(tools):
            if not isinstance(tool,dict):issues.append('TOOL_FORMAT_INVALID');continue
            preserve=domain.rules.get('preserve_tool_fields',[])
            row=clean_tool(tool,removed,f'tools[{i}]',preserve)
            call_id=str(row.get('call_id') or '')
            if tool_results:
                matches=result_by_id.get(call_id,[])
                if not call_id or len(matches)!=1:issues.append('TOOL_RESULT_LINK_INVALID')
                else:
                    row['output']=clean_tool(matches[0].get('output'),removed,f'tool_results.{call_id}',preserve)
                    row['status']=matches[0].get('status') or (row['output'].get('status') if isinstance(row['output'],dict) else None) or row.get('status','UNKNOWN')
            if isinstance(row.get('success'),bool):row.setdefault('status','SUCCESS' if row['success'] else 'FAILED')
            row['status']=str(row.get('status','UNKNOWN')).upper()
            for k in ('conversation_id','turn_id'):
                if row.get(k) is not None:row[k]=str(row[k])
            for k in ('conversation_id','turn_id','object_ids'):
                if k in metadata and row.get(k)!=metadata[k]:issues.append('TOOL_SCOPE_UNKNOWN_OR_MISMATCH:'+k)
            if not call_id:issues.append('TOOL_CALL_ID_MISSING')
            cleaned.append(row)
        call_ids=[t.get('call_id') for t in cleaned if t.get('call_id')]
        if len(call_ids)!=len(set(call_ids)):issues.append('TOOL_CALL_ID_DUPLICATED')
        if any(k not in {str(t.get('call_id')) for t in tools if isinstance(t,dict)} for k in result_by_id):issues.append('TOOL_RESULT_WITHOUT_CALL')
        declared=values['business_domain']
        scope='INCLUDE' if declared==domain.domain_id else 'PENDING'
        rows.append({'sample_id':sid,'question':question,'answer':answer,'context':history,
            'reference_policy':references,'retrieved_evidence':retrieved,'reference_complete':complete,
            'scenario_rules':{'template_id':domain.template_id,**domain.rules},'evidence_context':metadata,
            'source_type':values['source_type'] if isinstance(values['source_type'],str) and values['source_type'] in {'ACTUAL','CONSTRUCTED','AI_GENERATED'} else 'UNKNOWN',
            'business_domain':declared,'family_id':str(values['family_id'] or sid),'error_type':str(values['error_type'] or 'UNCLASSIFIED'),
            'scope':{'state':scope,'reason':'业务域匹配，仍需确认' if scope=='INCLUDE' else '请确认是否属于当前业务范围','confirmed_by':None},
            'tool_evidence':cleaned,'tool_expectations':values['tool_expectations'] or [],'issues':sorted(set(issues)),
            'provenance':{'raw_sha256':original_hash,'source_row':number,'removed_internal_fields':removed,
                'full_history_count':len(full_history),'selected_history_count':len(history),'history_mode':history_mode,
                'omitted_history':full_history[:-4] if history_mode!='FULL' else [],
                'question_normalized':question!=values['question'],'answer_preserved':True}})
    if len({r['sample_id'] for r in rows})!=len(rows):raise ValueError('IMPORT_SAMPLE_IDS_DUPLICATED')
    return rows,{'cleaning_version':'BUSINESS_PROJECTION_V1','semantic_mapping_version':digest(mapping),
        'raw_count':len(raw),'unique_count':len(rows),'duplicates':duplicates,'history_mode':history_mode}
