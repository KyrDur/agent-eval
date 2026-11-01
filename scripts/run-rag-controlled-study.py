#!/usr/bin/env python3
"""Sealed real local retrieval Baseline/Change/Retest. No commercial model call."""
import argparse,asyncio,json,secrets,socket,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'AgentEval'));sys.path.insert(0,str(ROOT/'AgentEvalFrontend/tests'))
from core.skill_loader import SkillManager
from experiments.store import JsonStore
from experiments.service import ExperimentService
from experiments.retrieval_service import RetrievalService
from experiments.providers import ProviderConfig
from experiments.rag_policy_pack import public_pack
from local_server import provider_server

async def run(folder):
    pack=public_pack();manager=SkillManager(ROOT/'AgentEval/skills');manager.load_strict()
    exp=ExperimentService(JsonStore(folder/'store'),manager);rag=RetrievalService(exp)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=provider_server(port)
    try:
        session=exp.providers.create(ProviderConfig(provider='openai-compatible',base_url=f'http://127.0.0.1:{port}/v1',model='retrieval-only-local-readiness-fixture',max_calls=10),secrets.token_hex(24))
        await exp.providers.test(session.provider_session_id)
        dataset=rag.knowledge.create(pack['documents'],pack['name'])
        config={'chunk_size':200,'chunk_overlap':20,'algorithm':'normalized-character-window-v1'}
        baseline_index=rag.knowledge.build(dataset.knowledge_dataset_id,1,config,'all-MiniLM-L6-v2')
        candidate_index=rag.knowledge.build(dataset.knowledge_dataset_id,1,config,'BAAI/bge-small-zh-v1.5')
        ev=rag.create_evalset(baseline_index.index_id,'16-family draft retrieval study',pack['debug_cases'])
        baseline=await rag.run(session.provider_session_id,ev.retrieval_eval_set_id,retrieval_config={'top_k':3},verify_answers=False)
        change=rag.propose_change(baseline.run_id,'EMBEDDING_CHANGE',baseline.retrieval_config.model_dump(),
            '本轮授权的工程与草稿检索对照：只换中文向量模型，固定政策、切块、题目、Top K 和检索流程；不声称人工金标或回答质量改善。',
            [c['case_id'] for c in pack['debug_cases']],True,target_index_id=candidate_index.index_id)
        change=rag.apply(change.change_id)
        retest=await rag.run(session.provider_session_id,change.target_eval_set_id,run_type='RETEST',parent_run_id=baseline.run_id,change_id=change.change_id,verify_answers=False)
        comparison=rag.compare(baseline.run_id,retest.run_id)
        receipt={'purpose':'ACTUAL_LOCAL_RETRIEVAL_CODEX_DRAFT_LABELS','baseline_id':baseline.run_id,'retest_id':retest.run_id,'change_id':change.change_id,'comparison_id':comparison.comparison_id,
            'comparable':comparison.comparable,'reasons':comparison.comparability_reasons,'baseline_status':baseline.status,'retest_status':retest.status,
            'retrieval_provider_requests':baseline.provider_call_count+retest.provider_call_count,'local_fixture_connection_tests':1,'commercial_requests':0,'verified_answers':False,'holdout_used':False,'human_calibration_complete':False}
        (folder/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(receipt,ensure_ascii=False))
        if not comparison.comparable or baseline.status!='COMPLETE' or retest.status!='COMPLETE':raise ValueError('controlled study failed')
    finally:server.shutdown();server.server_close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    asyncio.run(run(args.output))
