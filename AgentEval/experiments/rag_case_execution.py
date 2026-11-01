"""Small bounded batches, independent SDK state, one run-wide call ceiling."""
import asyncio
from types import SimpleNamespace
from .providers import ProviderFailure

CASE_CONCURRENCY = 3

class CaseProviders:
    def __init__(self, factory, config, key, judge_key, limit, stop):
        self.factory,self.config,self.key,self.judge_key=factory,config,key,judge_key
        self.limit,self.stop,self.reserved=limit,stop,0
        self.providers=[]

    def create(self):
        provider=self.factory(self.config,self.key,self.judge_key)
        provider.stop_requested=self.stop
        self.providers.append(provider)
        group=self
        class Bounded:
            def __getattr__(self,name):return getattr(provider,name)
            def client(self,role,*args,**kwargs):
                client=provider.client(role,*args,**kwargs)
                async def create(**values):
                    if group.stop and group.stop():raise asyncio.CancelledError()
                    # No await between checking and reserving: all cases share one loop.
                    if group.reserved>=group.limit:
                        provider.errors.append({'stage':role,'status':'CALL_BUDGET_EXCEEDED'})
                        raise ProviderFailure('CALL_BUDGET_EXCEEDED')
                    group.reserved+=1
                    return await client.messages.create(**values)
                return SimpleNamespace(messages=SimpleNamespace(create=create))
        return Bounded()

    @property
    def call_count(self):return sum(p.call_count for p in self.providers)
    @property
    def observations(self):return [v for p in self.providers for v in p.observations]
    @property
    def errors(self):return [v for p in self.providers for v in p.errors]
    async def close(self):
        await asyncio.gather(*(p.close() for p in self.providers),return_exceptions=True)

async def run_cases(cases,worker,concurrency=CASE_CONCURRENCY):
    slots=asyncio.Semaphore(concurrency)
    async def one(case):
        async with slots:await worker(case)
    tasks=[asyncio.create_task(one(case)) for case in cases]
    try:await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        raise
