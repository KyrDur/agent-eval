"""One index process, no credentials. EOF watcher stops its entire process group."""
import json,os,signal,sys,threading
from pathlib import Path

def orphan_guard():
    while os.read(0,4096):pass
    os.killpg(os.getpgrp(),signal.SIGKILL)

if __name__=='__main__':
    threading.Thread(target=orphan_guard,daemon=True).start()
    try:
        from .store import JsonStore
        from .retrieval_knowledge import FrozenKnowledge
        store=JsonStore(sys.argv[1]);job=store.get('index_builds',sys.argv[2])
        index=FrozenKnowledge(store).build(**job.inputs)
        print(json.dumps({'index_id':index.index_id}),flush=True)
    except Exception as error:
        code=str(error)
        allowed={'INDEX_RESOURCE_BUSY','CHINESE_EMBEDDING_NOT_PREPARED','EMBEDDING_INPUT_TOO_LONG','EMBEDDING_TIMEOUT','EMBEDDING_MODEL_UNAVAILABLE'}
        print(json.dumps({'error':code if code in allowed else 'INDEX_BUILD_FAILED'}),flush=True)
