"""Optional DeepEval 4.3.1 sidecar. Private stdin; no defaults, retries, or hosted eval."""
import os
os.environ['DEEPEVAL_TELEMETRY_OPT_OUT']='YES'
os.environ['CONFIDENT_TRACING_ENABLED']='NO'
os.environ['CONFIDENT_TRACE_INTERNAL']='NO'
os.environ['DEEPEVAL_DISABLE_TIMEOUTS']='1'
import asyncio,hashlib,json,sys,time,urllib.request
from importlib.metadata import version
from deepeval.models import DeepEvalBaseLLM
from deepeval.metrics import FaithfulnessMetric,ContextualRecallMetric
from deepeval.test_case import LLMTestCase

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('REDIRECT_REJECTED')

class BoundedJudge(DeepEvalBaseLLM):
    def __init__(self,config,credential,budget,smoke=False):
        self.config=config;self.credential=credential;self.budget=budget;self.smoke=smoke;self.calls=[]
        super().__init__(model=config['model'])
    def load_model(self):return self
    def get_model_name(self):return self.config['model']
    def generate(self,prompt,schema=None,**kwargs):return self.generate_with_schema(prompt,schema,**kwargs)
    async def a_generate(self,prompt,schema=None,**kwargs):return self.generate_with_schema(prompt,schema,**kwargs)
    async def a_generate_with_schema(self,prompt,schema,**kwargs):return self.generate_with_schema(prompt,schema,**kwargs)
    def generate_with_schema(self,prompt,schema,**kwargs):
        if len(self.calls)>=self.budget:raise ValueError('DEEPEVAL_REQUEST_BUDGET_EXCEEDED')
        if not isinstance(prompt,str):raise ValueError('TEXT_ONLY')
        if len(prompt)>50000:raise ValueError('DEEPEVAL_INPUT_TOO_LONG')
        call={'request_number':len(self.calls)+1,'prompt_hash':hashlib.sha256(prompt.encode()).hexdigest(),'schema':schema.__name__,'status':'STARTED','usage':None}
        started=time.monotonic()
        try:
            if self.smoke:
                self.calls.append(call)
                # Schema wiring test only. Never a quality estimate or human label.
                shapes={'Truths':{'truths':['schema smoke']},'Claims':{'claims':['schema smoke']},
                    'Verdicts':{'verdicts':[{'verdict':'yes','reason':'schema smoke','statement':'schema smoke','expected_output':'schema smoke'}]},
                    'FaithfulnessScoreReason':{'reason':'schema smoke'},'ContextualRecallScoreReason':{'reason':'schema smoke'}}
                data=shapes[schema.__name__]
            else:
                c=self.config;content=prompt+'\nReturn only JSON conforming to this schema:\n'+json.dumps(schema.model_json_schema())
                if c['provider']=='openai-compatible':
                    url=c['base_url'].rstrip('/')+'/chat/completions'
                    body={'model':c['model'],'messages':[{'role':'user','content':content}],'temperature':c.get('temperature',0),'max_tokens':c.get('max_tokens',4096)}
                    headers={'Authorization':'Bearer '+self.credential}
                else:
                    base=c['base_url'].rstrip('/');url=base+('/messages' if base.endswith('/v1') else '/v1/messages')
                    body={'model':c['model'],'messages':[{'role':'user','content':content}],'temperature':c.get('temperature',0),'max_tokens':c.get('max_tokens',4096)}
                    headers={'x-api-key':self.credential,'anthropic-version':'2023-06-01'}
                # Conservative input estimate, declared rather than called exact tokens.
                if len(content.encode())+body['max_tokens']>c.get('context_window_tokens',32768):raise ValueError('DEEPEVAL_CONTEXT_BUDGET_EXCEEDED')
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
                request=urllib.request.Request(url,data=json.dumps(body).encode(),headers={**headers,'Content-Type':'application/json'},method='POST')
                self.calls.append(call)
                with opener.open(request,timeout=min(c.get('timeout_seconds',30),30)) as response:raw=json.loads(response.read(2_000_000))
                call['usage']=raw.get('usage')
                if c['provider']=='openai-compatible':
                    choice=raw['choices'][0]
                    if choice.get('finish_reason')!='stop':raise ValueError('INCOMPLETE_RESPONSE')
                    value=choice['message']['content']
                else:
                    if raw.get('stop_reason')!='end_turn':raise ValueError('INCOMPLETE_RESPONSE')
                    value=''.join(b.get('text','') for b in raw['content'] if b['type']=='text')
                if value.startswith('```'):value=value.split('\n',1)[1].rsplit('```',1)[0]
                data=json.loads(value)
            result=schema.model_validate(data);call['status']='SUCCESS';return result
        except Exception as e:
            call['status']='FAILED';call['error']='BUDGET_EXCEEDED' if 'BUDGET_EXCEEDED' in str(e) else 'JUDGE_REQUEST_OR_SCHEMA_FAILED'
            raise ValueError(call['error']) from None
        finally:call['elapsed_ms']=round((time.monotonic()-started)*1000)

def run(payload):
    if version('deepeval')!='4.3.1':raise ValueError('DEEPEVAL_VERSION_MISMATCH')
    judge=BoundedJudge(payload['configuration'],payload.get('credential',''),payload['request_limit'],payload.get('schema_smoke',False));observations=[]
    for row in payload['test_cases']:
        tc=LLMTestCase(input=row['input'],actual_output=row['actual_output'],retrieval_context=row['retrieval_context'],expected_output=row.get('expected_output'))
        for metric_cls in [FaithfulnessMetric,ContextualRecallMetric]:
            name=metric_cls.__name__;before=len(judge.calls)
            if metric_cls is ContextualRecallMetric and not (row.get('reference_reviewed') and row.get('expected_output')):
                observations.append({'case_id':row['case_id'],'metric':name,'status':'SKIPPED_UNREVIEWED_REFERENCE','score':None,'request_count':0});continue
            metric=metric_cls(model=judge,async_mode=False,eval_mode='llm',include_reason=True,threshold=.5)
            try:
                metric.measure(tc,_show_indicator=False)
                observations.append({'case_id':row['case_id'],'metric':name,'status':'COMPLETE','score':metric.score,'reason':metric.reason,'threshold':.5,'threshold_is_business_verdict':False,'request_count':len(judge.calls)-before})
            except Exception:
                observations.append({'case_id':row['case_id'],'metric':name,'status':'FAILED','score':None,'error':'DEEPEVAL_BUDGET_OR_JUDGE_FAILED','request_count':len(judge.calls)-before})
    return {'deepeval_version':version('deepeval'),'eval_mode':'llm','cache':'DISABLED_DIRECT_MEASURE','fixed_answer_replay':True,'human_reference':False,'metric_settings':{'threshold':0.5,'include_reason':True,'faithfulness_penalize_ambiguous_claims':False},
        'schema_smoke_only':judge.smoke,'observations':observations,'provider_requests':judge.calls,'request_count':len(judge.calls),'monetary_cost':None,
        'faithfulness_policy':'DeepEval original 4.3.1; score is not a business-rule verdict; unsupported noncontradicted claims require human review.'}

if __name__=='__main__':
    payload=json.load(sys.stdin)
    result=run(payload)
    json.dump(result,sys.stdout,ensure_ascii=False)
