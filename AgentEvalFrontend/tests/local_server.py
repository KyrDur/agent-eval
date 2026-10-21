"""Local scripted HTTP Provider + real Python backend for Phase 4 browser tests.
Never a commercial model claim. No fake Run/evaluator/Comparison implementation.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import uvicorn

MARKER='PHASE4_CHECK_PAYMENT_BEFORE_CLAIMS'

def provider_server(port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            messages=data['messages'];prompt=str(messages);model=data['model']
            if model=='background-slow-fixture':time.sleep(1)
            tools={t['function']['name'] for t in data.get('tools',[])}
            msg={'role':'assistant','content':'OK'};finish='stop';status=200
            error=None
            if model=='auth-failed':status=401;error={'code':'invalid_api_key'}
            elif model=='tools-unsupported' and tools=={'echo'}:
                status=400;error={'code':'tools_not_supported'}
            elif model=='tools-probe-failed' and tools=={'echo'}:
                status=429;error={'code':'rate_limit_exceeded'}
            elif tools=={'echo'}:
                value=re.search(r'echo-[a-f0-9]{12}',prompt).group()
                msg.update(content=None,tool_calls=[{'type':'function','id':'probe_echo','function':{
                    'name':'echo','arguments':json.dumps({'value':value})}}]);finish='tool_calls'
            elif 'ASSIST_KNOWLEDGE' in prompt:
                from experiments.assist import CATEGORIES
                msg['content']=json.dumps({'name':'本地脚本模拟知识','documents':[{'document_id':'topic_'+str(i),'title':category,'category':category,'text':'本条为本地脚本模拟规则。请核验订单，不承诺业务已完成。','applicability':'模拟店铺普通商品','exceptions':'定制商品需核验'} for i,category in enumerate(CATEGORIES)]},ensure_ascii=False)
            elif 'ASSIST_TESTS' in prompt:
                value=json.loads(messages[-1]['content']);offset=len(value['existing_queries']);cases=[]
                for i in range(value['count']):
                    doc=value['documents'][(offset+i)%len(value['documents'])]
                    question_type=value['requested_types'][i];outside=question_type=='知识范围外'
                    cases.append({'query':f'本地合成题 {offset+i}？','expected_answer':'资料未提供相关规则，无法确认，不编造。' if outside else doc['text'],
                        'must_do':['说明资料不足' if outside else '说明适用条件'],'must_not_do':['不能声称已完成'],
                        'relevant_document_ids':[] if outside else [doc['document_id']],'question_type':question_type,
                        'source_quotes':[] if outside else [{'document_id':doc['document_id'],'quote':doc['text'][:12]}]})
                msg['content']=json.dumps({'cases':cases},ensure_ascii=False)
            elif 'ASSIST_EVALUATION_CHAT' in prompt:
                value=json.loads(messages[-1]['content'])
                msg['content']=json.dumps({'answer':f"本地脚本说明：运行结束不等于回答通过。请核对本题参考政策是否齐全。已读取 {len(value['history'])} 轮问答。",'evidence_keys':[next(iter(value['evidence']))]},ensure_ascii=False)
            elif 'ASSIST_TRACE' in prompt:
                value=json.loads(messages[-1]['content']);ref=next(iter(value['evidence']))
                msg['content']=json.dumps({'facts':[{'claim':'本次本地脚本轨迹有记录','evidence_keys':[ref]}],'issues':[],'hypotheses':[],'suggestions':[{'change_type':'TOP_K_CHANGE','reason':'本地验收排序假设','evidence_keys':[ref],'verification':'同题复测','side_effects':'可能增加上下文'}],'limitations':['本地脚本不证明真实质量']},ensure_ascii=False)
            elif 'AGENT_EVAL_LANGSMITH_JUDGE_V1' in prompt:
                value=json.loads(messages[-1]['content']);catalog=value['sample']['fragment_catalog']
                answer=next(f['fragment_id'] for f in catalog if f['scope']=='ANSWER')
                dims={}
                for dimension in ('faithfulness','conditions','relevance','actionability'):
                    scope='RETRIEVED' if dimension=='faithfulness' else 'REFERENCE'
                    evidence=[f['fragment_id'] for f in catalog if f['scope']==scope]
                    dims[dimension]={'score':2,'answer_fragment_ids':[answer],
                        'evidence_fragment_ids':evidence[:1],'reason':'Scripted acceptance only, not Judge accuracy.'}
                if model=='trace-null-score-fixture':dims['actionability']['score']=None
                if model=='recovery-null-fixture':
                    dims['actionability']['score']='NA' if value.get('previous_validation_issues') else None
                    dims['actionability']['reason']='规格事实题无行动需求。'
                msg['content']=json.dumps({'dimensions':dims,'critical_errors':[],'error_tags':[],
                    'task_resolved':'YES','faithful_to_available':'YES','task_failure_reasons':[],
                    'insufficient_items':[],'reason':'Scripted acceptance only.'})
            elif 'CALIBRATION_JUDGE_V2' in prompt:
                value=json.loads(messages[-1]['content']);catalog=value['sample']['fragment_catalog']
                answer=next(f['fragment_id'] for f in catalog if f['scope']=='ANSWER')
                dims={}
                for dimension in ('faithfulness','conditions','relevance','actionability'):
                    scope='RETRIEVED' if dimension=='faithfulness' else 'REFERENCE'
                    evidence=[f['fragment_id'] for f in catalog if f['scope']==scope]
                    dims[dimension]={'score':2,'answer_fragment_ids':[answer],
                        'evidence_fragment_ids':evidence[:1],
                        'reason':'Scripted fragment fixture only; not real Judge quality.'}
                msg['content']=json.dumps({'dimensions':dims,'critical_errors':[],'error_tags':[],
                    'verdict':'PASS','task_resolved':'YES','faithful_to_available':'YES','task_failure_reasons':[],
                    'insufficient_items':[],'reason':'Scripted local HTTP fragment fixture only.'},ensure_ascii=False)
            elif 'CALIBRATION_JUDGE_V1' in prompt:
                value=json.loads(messages[-1]['content']);s=value['sample']
                dims={}
                for dimension in ('faithfulness','conditions','relevance','actionability'):
                    evidence=s['retrieved_evidence'] if dimension=='faithfulness' else s['reference_policy']
                    dims[dimension]={'score':2,'answer_quotes':[s['answer']],
                        'citations':[{'scope':'RETRIEVED' if dimension=='faithfulness' else 'REFERENCE',
                            'evidence_id':evidence[0]['evidence_id'],'quote':evidence[0]['text']}] if evidence else [],
                        'reason':'Scripted protocol fixture; not evidence of Judge quality.'}
                msg['content']=json.dumps({'dimensions':dims,'critical_errors':[],'error_tags':[],
                    'verdict':'PASS','task_resolved':'YES','faithful_to_available':'YES','task_failure_reasons':[],
                    'insufficient_items':[],'reason':'Scripted local HTTP fixture only.'},ensure_ascii=False)
            elif 'RAG_REWRITE_V1' in prompt:
                if model=='rag-rewrite-failed':status=503;error={'code':'rewrite_unavailable'}
                value=json.loads(messages[-1]['content'])['query']
                replacements={'拆了还能退吗？':'已拆封商品 七天无理由退货条件',
                    '钱什么时候回到卡里？':'退款审核通过 原付款方式 到账时间',
                    '包裹咋还没动？':'配送物流超时 查询运单',
                    '报销的凭证怎么弄？':'电子发票 申请 抬头 税号',
                    '进不去账户了怎么办？':'忘记密码 登录 账户重置',
                    '花的钱有奖励吗？':'会员积分 消费 兑换',
                    '送错地方能改吗？':'修改收货地址 揽收前',
                    '买的坏了找谁？':'保修质量故障 售后维修'}
                msg['content']=json.dumps({'rewritten_query':replacements.get(value,value)},ensure_ascii=False)
            elif 'RAG_RERANK_V1' in prompt:
                if model=='rag-rerank-failed':status=503;error={'code':'rerank_unavailable'}
                value=json.loads(messages[-1]['content'])
                msg['content']=json.dumps({'results':[{'chunk_id':c['chunk_id'],'score':1-i/(len(value['candidates'])+1)}
                    for i,c in enumerate(value['candidates'])]})
            elif 'RAG_ANSWER_V1' in prompt:
                if model=='rag-agent-failed':status=503;error={'code':'agent_unavailable'}
                value=json.loads(messages[-1]['content'])
                # Scripted model responses depend on actual acquired context. This
                # fixture never injects a rank, retrieval metric, or transition.
                expected={'拆了还能退吗？':'opened','钱什么时候回到卡里？':'refund','包裹咋还没动？':'delivery',
                    '报销的凭证怎么弄？':'invoice','进不去账户了怎么办？':'password','花的钱有奖励吗？':'points',
                    '送错地方能改吗？':'address','买的坏了找谁？':'warranty'}.get(value['query'])
                context=value['retrieved_knowledge']
                good=any(c['document_id']==expected for c in context)
                msg['content']=('SCRIPTED_QUALITY_GOOD' if good else 'SCRIPTED_QUALITY_NEEDS_WORK')+'：'+str([
                    {'document_id':c['document_id'],'text':c['text']} for c in context])
            elif '客服意图分析专家' in prompt:
                msg['content']=json.dumps({'intent':'refund','confidence':1,'reasoning':'scripted local protocol'})
            elif '客服质量评估专家' in prompt:
                if 'PHASE4_JUDGE_FAILURE' in prompt or model=='rag-judge-failed':status=503;error={'code':'scripted_judge_unavailable'}
                else:
                    score=.95 if 'SCRIPTED_QUALITY_GOOD' in prompt else .2
                    msg['content']=json.dumps(dict(relevance=score,accuracy=score,completeness=score,helpfulness=score))
            elif tools and not any(m['role']=='tool' for m in messages):
                name='check_billing_fields' if 'check_billing_fields' in tools else 'inspect_request_context'
                msg.update(content=None,tool_calls=[{'type':'function','id':'case_tool','function':{'name':name,'arguments':'{}'}}]);finish='tool_calls'
            elif tools:
                system='\n'.join(m['content'] for m in messages if m['role']=='system')
                after=MARKER in system
                good=('PHASE4_STILL_PASS' in prompt or 'PHASE4_REGRESSION_CASE' in prompt and not after
                      or not any(t in prompt for t in ['PHASE4_STILL_FAIL','PHASE4_REGRESSION_CASE']) and after)
                msg['content']=('SCRIPTED_QUALITY_GOOD' if good else 'SCRIPTED_QUALITY_NEEDS_WORK')+'：请核验付款凭证，再说明退款流程。'
            body={'error':error} if error else {'id':'chatcmpl_phase4_local','object':'chat.completion',
                'model':model,'choices':[{'index':0,'message':msg,'finish_reason':finish}],
                'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}
            raw=json.dumps(body,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--backend-port',type=int,default=8014)
    parser.add_argument('--provider-port',type=int,default=8124)
    parser.add_argument('--data-dir')
    args=parser.parse_args()
    frontend=Path(__file__).resolve().parents[1]
    python_root=frontend.parent/'AgentEval'
    evidence=Path(os.environ.get('AGENTEVAL_TEST_EVIDENCE_DIR',frontend.parent/'output/e2e-captures/agent-eval'))
    evidence.mkdir(exist_ok=True)
    directory=Path(args.data_dir) if args.data_dir else Path(tempfile.mkdtemp(prefix='browser-',dir=evidence))
    directory.mkdir(parents=True,exist_ok=True)
    if not (directory/'skills').exists():shutil.copytree(python_root/'skills',directory/'skills')
    os.environ['AGENTEVAL_SKILL_DIR']=str(directory/'skills')
    os.environ['AGENTEVAL_EXPERIMENT_DIR']=str(directory/'store')
    # Public locations only, no credential. Unique workspace preserves previous test evidence.
    (evidence/'local-workspace.json').write_text(json.dumps({'data_dir':str(directory),'provider_url':
        f'http://127.0.0.1:{args.provider_port}/v1','backend_url':f'http://127.0.0.1:{args.backend_port}',
        'purpose':'scripted HTTP contract and UI closure; not commercial model validation'},indent=2)+'\n')
    server=provider_server(args.provider_port)
    try:uvicorn.run('experiments.app:app',host='127.0.0.1',port=args.backend_port,log_level='warning',access_log=False)
    finally:server.shutdown();server.server_close()
