#!/usr/bin/env python3
"""Explicit one-time download of the pinned official model, never on a query."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'AgentEval'))
from experiments.bge_embeddings import MODEL,REVISION
from huggingface_hub import snapshot_download
folder=snapshot_download(MODEL,revision=REVISION,allow_patterns=['config.json','tokenizer*','vocab.txt','special_tokens_map.json','model.safetensors'])
print('Prepared:',MODEL,REVISION,folder)
