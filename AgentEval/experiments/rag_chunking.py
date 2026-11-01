"""Structure-aware chunks with original Unicode-codepoint offsets (not JS UTF16)."""
import re
from .canonical import digest,text_hash


def structure_chunks(dataset, config):
    result=[]
    for doc in sorted(dataset.documents,key=lambda d:d['document_id']):
        raw=doc['text'];heading=doc.get('title','');start=0;sections=[]
        # Keep headings with the section they introduce; preserve original text.
        for match in re.finditer(r'(?m)^#{1,6}\s+[^\n]+',raw):
            if match.start()>start: sections.append((start,match.start(),heading))
            start=match.start();heading=match.group().lstrip('#').strip()
        if start<len(raw):sections.append((start,len(raw),heading))
        for s,e,title in sections:
            parent=digest({'document_id':doc['document_id'],'hash':text_hash(raw),'start':s,'end':e})
            pos=s
            while pos<e:
                stop=min(pos+config.chunk_size,e)
                if stop<e:
                    boundaries=list(re.finditer(r'[。！？；\n]',raw[pos:stop]))
                    if boundaries and boundaries[-1].end()>config.chunk_size//3:
                        stop=pos+boundaries[-1].end()
                text=raw[pos:stop]
                if text.strip():
                    index=len([c for c in result if c['document_id']==doc['document_id']])
                    result.append({'chunk_id':digest({'parent':parent,'start':pos,'end':stop,'algorithm':config.algorithm}),
                        'document_id':doc['document_id'],'chunk_index':index,'text':text,'text_hash':text_hash(text),
                        'title':title,'parent_id':parent,'source_start':pos,'source_end':stop,
                        'parent_start':s,'parent_end':e,'source_hash':text_hash(raw),
                        'offset_unit':'UNICODE_CODEPOINT','algorithm':config.algorithm})
                if stop==e:break
                pos=max(pos+1,stop-config.chunk_overlap)
    return result
