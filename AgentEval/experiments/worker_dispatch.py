"""Shared domain-worker launcher. Credentials only cross the existing private pipe."""
import asyncio
import json
import os
import sys
from pathlib import Path

async def launch_worker(root,job_id,key,judge_key=None,kind='operations'):
    args=[sys.executable,'-m','experiments.domain_worker',str(root),job_id]
    if kind=='score':args.append('--score')
    process=await asyncio.create_subprocess_exec(*args,stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,
        env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])})
    try:
        await process.communicate(json.dumps({'key':key,'judge_key':judge_key}).encode())
        return process.returncode
    except asyncio.CancelledError:
        if process.returncode is None:process.terminate()
        await process.wait()
        raise
