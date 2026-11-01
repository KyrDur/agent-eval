"""Durable receipts; bounded local subprocess; cancellation stops its process group."""
import asyncio,json,os,signal,sys,time
from pathlib import Path
from typing import Literal
from pydantic import Field
from .models import Artifact,uid,now
from .canonical import digest

class IndexBuild(Artifact):
    job_id:str=Field(default_factory=uid)
    request_id:str
    input_hash:str
    inputs:dict
    status:Literal['SUBMITTED','BUILDING','READY','FAILED','CANCELLED']='SUBMITTED'
    index_id:str|None=None
    error:str|None=None
    elapsed_ms:int|None=None
    finished_at:str|None=None

_tasks={}
_processes={}
_cancelled=set()

def key(store,job_id):return (str(store.root.resolve()),job_id)

def update(store,job_id,**fields):
    with store.transaction():
        job=store.get('index_builds',job_id)
        if job.status in {'READY','FAILED','CANCELLED'}:return job
        return store.put('index_builds',job.model_copy(update=fields))

async def submit(store,request_id,inputs):
    fingerprint=digest(inputs)
    for old in store.list('index_builds'):
        if old.status in {'SUBMITTED','BUILDING'}:read(store,old.job_id)
    with store.transaction():
        for old in store.list('index_builds'):
            if old.request_id==request_id:
                if old.input_hash!=fingerprint:raise ValueError('IDEMPOTENCY_CONFLICT')
                return old
        if any(j.status in {'SUBMITTED','BUILDING'} for j in store.list('index_builds')):raise ValueError('WORKSPACE_BUSY')
        job=IndexBuild(request_id=request_id,input_hash=fingerprint,inputs=inputs)
        lease=store.acquire_run_lease(job.job_id,'index_builds')
        store.put('index_builds',job)
    task=asyncio.create_task(run(store,job,lease));_tasks[key(store,job.job_id)]=task
    task.add_done_callback(lambda _: _tasks.pop(key(store,job.job_id),None))
    return job

async def run(store,job,lease):
    started=time.monotonic();process=None
    try:
        current=update(store,job.job_id,status='BUILDING')
        if current.status=='CANCELLED':return
        process=await asyncio.create_subprocess_exec(sys.executable,'-m','experiments.rag_index_worker',str(store.root),job.job_id,
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,start_new_session=True,
            env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])})
        _processes[key(store,job.job_id)]=process
        if key(store,job.job_id) in _cancelled:
            os.killpg(process.pid,signal.SIGKILL)
        # Keep stdin open: worker watchdog kills all inference children on parent exit.
        output=await asyncio.wait_for(process.stdout.read(4096),timeout=300)
        await asyncio.wait_for(process.wait(),timeout=5)
        message=json.loads(output) if output else {}
        if process.returncode or not message.get('index_id'):
            update(store,job.job_id,status='FAILED',error=message.get('error','INDEX_BUILD_FAILED'),finished_at=now())
        else:
            index=store.get('knowledge_indices',message['index_id'])
            update(store,job.job_id,status='READY',index_id=index.index_id,elapsed_ms=round((time.monotonic()-started)*1000),finished_at=now())
    except asyncio.CancelledError:
        update(store,job.job_id,status='CANCELLED',error='INDEX_BUILD_CANCELLED',finished_at=now())
    except Exception:
        update(store,job.job_id,status='FAILED',error='INDEX_BUILD_INTERRUPTED_OR_TIMEOUT',finished_at=now())
    finally:
        if process:
            if process.returncode is None:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                await process.wait()
            if process.stdin:process.stdin.close()
        _processes.pop(key(store,job.job_id),None);_cancelled.discard(key(store,job.job_id));lease.close()

def read(store,job_id):
    with store.transaction():
        job=store.get('index_builds',job_id)
        if job.status in {'SUBMITTED','BUILDING'}:
            try:lease=store.acquire_run_lease(job_id,'index_builds')
            except BlockingIOError:return job
            try:
                job=store.put('index_builds',job.model_copy(update={'status':'FAILED','error':'INDEX_BUILD_INTERRUPTED','finished_at':now()}))
            finally:lease.close()
        return job

async def cancel(store,job_id):
    job=read(store,job_id);task=_tasks.get(key(store,job_id))
    if task and job.status in {'SUBMITTED','BUILDING'}:
        _cancelled.add(key(store,job_id))
        update(store,job_id,status='CANCELLED',error='INDEX_BUILD_CANCELLED',finished_at=now())
        # Signal only a process object owned by this server, never a persisted PID.
        process=_processes.get(key(store,job_id))
        if process and process.returncode is None:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        await asyncio.shield(task)
    return read(store,job_id)
