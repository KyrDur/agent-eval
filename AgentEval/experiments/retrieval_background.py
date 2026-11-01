"""Short HTTP submission around the unchanged, leased RAG execution engine.

The RetrievalRun is the durable progress record. No answer/scoring semantics or
historical implementation fingerprints are altered by this HTTP lifecycle.
"""
import asyncio
import re
from .canonical import digest

class RetrievalBackground:
    def __init__(self,rag):
        self.rag=rag
        self.pending={}
        self.stops=set()

    def saved(self,request_id,group='retrieval_runs'):
        return next((r for r in self.rag.store.list(group) if r.request_id==request_id),None)

    async def submit(self,arguments,capacity):
        request_id=arguments.get('request_id')
        if not isinstance(request_id,str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}',request_id):
            raise ValueError('IDEMPOTENCY_REQUEST_INVALID')
        fingerprint=digest(arguments)
        group=arguments.get('_sink_group','retrieval_runs')
        active=self.pending.get(request_id)
        if active:
            if active[0]!=fingerprint:raise ValueError('IDEMPOTENCY_CONFLICT')
            task=active[2]
        elif self.saved(request_id,group):
            # Reuse the original engine's exact request-hash compatibility check.
            return await self.rag.run(**arguments)
        else:
            if capacity.locked():raise ValueError('WORKSPACE_BUSY')
            await capacity.acquire()
            async def execute_run():
                try:return await self.rag.run(**arguments,_cancel_check=lambda:request_id in self.stops)
                finally:
                    capacity.release();self.pending.pop(request_id,None)
            task=asyncio.create_task(execute_run())
            task.add_done_callback(lambda value:None if value.cancelled() else value.exception())
            self.pending[request_id]=(fingerprint,None,task)
        # The engine seals RUNNING before its first external request. Wait only
        # for that receipt, never for the sequence of paid model requests.
        while not task.done():
            run=self.saved(request_id,group)
            if run:return run
            await asyncio.sleep(0.02)
        return task.result()

    def request_stop(self,request_id):
        self.stops.add(request_id)

    async def close(self):
        tasks=[value[2] for value in self.pending.values()]
        for task in tasks:task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)

def background(rag):
    if not hasattr(rag,'background_controller'):rag.background_controller=RetrievalBackground(rag)
    return rag.background_controller

async def close_background(rag):
    from .retest_flow import close
    await close(rag)
    controller=getattr(rag,'background_controller',None)
    if controller:await controller.close()
