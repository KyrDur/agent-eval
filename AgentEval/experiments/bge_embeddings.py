"""Pinned optional Chinese encoder in a bounded, isolated Python worker."""
import hashlib,json,math,os,subprocess,sys
from pathlib import Path
from functools import lru_cache

MODEL='BAAI/bge-small-zh-v1.5'
REVISION='7999e1d3359715c523056ef9478215996d62a620'


def python_path():
    local=Path(__file__).resolve().parents[2]/'.venv-rag-model/bin/python'
    return os.environ.get('AGENTEVAL_EMBEDDING_PYTHON',str(local) if local.exists() else sys.executable)


@lru_cache(maxsize=1)
def model_path():
    from huggingface_hub import snapshot_download
    return snapshot_download(MODEL,revision=REVISION,local_files_only=True,
        allow_patterns=['config.json','tokenizer*','vocab.txt','special_tokens_map.json','model.safetensors'])


@lru_cache(maxsize=1)
def backend_state():
    command='import importlib.metadata as m,json,platform;print(json.dumps({k:m.version(k) for k in ["torch","transformers","tokenizers","safetensors"]}|{"python":platform.python_version()}))'
    state=json.loads(subprocess.check_output([python_path(),'-c',command],text=True,timeout=10))
    if state['torch']!='2.8.0' or state['transformers']!='4.57.1':raise ValueError('CHINESE_EMBEDDING_BACKEND_VERSION_MISMATCH')
    return state

def snapshot():
    folder=Path(model_path());hashes={}
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix in {'.json','.txt','.safetensors','.bin'}:
            h=hashlib.sha256()
            with p.open('rb') as f:
                for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
            hashes[p.name]=h.hexdigest()
    if not any(n.endswith(('.bin','.safetensors')) for n in hashes):raise ValueError('CHINESE_EMBEDDING_NOT_PREPARED')
    return {'provider':'local','model':MODEL,'dimension':512,'model_version':REVISION,
        'normalization':'NFKC whitespace lowercase L2','distance_metric':'cosine',
        'configuration':{'backend':'torch-cpu-subprocess','backend_versions':backend_state(),'pooling':'CLS','max_input_tokens':512,'query_instruction':'',
            'overflow_policy':'REJECT_NO_TRUNCATION','threads':1,'worker_timeout_seconds':120,
            'files_sha256':hashes,'implementation_hash':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}


def normalize(text):
    import re,unicodedata
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',text)).strip().lower()

def encode(texts):
    from .retrieval_embeddings import EmbeddingFailure
    try:
        result=subprocess.run([python_path(),str(Path(__file__).resolve()),model_path()],
            input=json.dumps([normalize(t) for t in texts],ensure_ascii=False),text=True,capture_output=True,timeout=120,
            env={**os.environ,'HF_HUB_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false'})
        if result.returncode:
            if 'EMBEDDING_INPUT_TOO_LONG' in result.stderr:raise EmbeddingFailure('EMBEDDING_INPUT_TOO_LONG')
            raise EmbeddingFailure('CHINESE_EMBEDDING_NOT_PREPARED')
        vectors=json.loads(result.stdout)
        if len(vectors)!=len(texts) or any(len(v)!=512 or any(not math.isfinite(x) for x in v) for v in vectors):
            raise ValueError('invalid vectors')
        return vectors
    except EmbeddingFailure:raise
    except subprocess.TimeoutExpired:raise EmbeddingFailure('EMBEDDING_TIMEOUT') from None
    except Exception:raise EmbeddingFailure('CHINESE_EMBEDDING_NOT_PREPARED') from None


if __name__=='__main__':
    import torch
    from transformers import AutoModel,AutoTokenizer
    torch.set_num_threads(1)
    tokenizer=AutoTokenizer.from_pretrained(sys.argv[1],local_files_only=True)
    model=AutoModel.from_pretrained(sys.argv[1],local_files_only=True).eval()
    texts=json.load(sys.stdin);output=[]
    with torch.no_grad():
        for text in texts:
            inputs=tokenizer(text,return_tensors='pt',truncation=False)
            if inputs['input_ids'].shape[1]>512:raise ValueError('EMBEDDING_INPUT_TOO_LONG')
            vector=torch.nn.functional.normalize(model(**inputs).last_hidden_state[:,0],p=2,dim=1)
            output.append(vector[0].tolist())
    json.dump(output,sys.stdout)
