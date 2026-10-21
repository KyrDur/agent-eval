import asyncio
import json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from experiments.app import app
from experiments.api import configure
from experiments.evaluation_chat import EvaluationChatService
from experiments.evidence_explanation import decision_reasons
from experiments.providers import ProviderFailure
from experiments.retrieval_service import RetrievalService
from test_experiment_service import setup
from test_ai_assistance import assistant_server, ready, knowledge


def run_fixture(rag, session):
    index=knowledge(rag)
    dataset=rag.create_evalset(index.index_id,'解释证据不足',[
        {'case_id':'gap','query':'退款何时到账？','group_id':'refund_time','relevant_document_ids':['refund']},
        {'case_id':'holdout','query':'HOLDOUT_PRIVATE_UNEXECUTED_QUESTION','group_id':'private_unseen',
         'partition':'HOLDOUT','relevant_document_ids':['refund']}],split_reviewed=True)
    return asyncio.run(rag.run(session.provider_session_id,dataset.retrieval_eval_set_id,
        verify_answers=True,scoring_profile_id='initial-evidence-v1'))


def ask(chat,session,run,question='为什么不能判断？',**kwargs):
    return asyncio.run(chat.chat(str(uuid4()),session.provider_session_id,question,run_id=run.run_id,**kwargs))


def test_chat_reads_frozen_scope_follows_up_and_keeps_evaluation_unchanged(tmp_path):
    service,_,_=setup(tmp_path);rag=RetrievalService(service);chat=EvaluationChatService(rag)
    with assistant_server() as (url,state):
        session=ready(service,url);run=run_fixture(rag,session)
        path=rag.store.path('retrieval_runs',run.run_id);before=path.read_bytes()
        request_id=str(uuid4());calls=len(state['calls'])
        first=asyncio.run(chat.chat(request_id,session.provider_session_id,'为什么不能判断？',run_id=run.run_id))
        assert first['provider_call_count']==1 and len(state['calls'])==calls+1
        assert first['usage']=={'known_total_tokens':2,'unknown_usage_requests':0}
        again=asyncio.run(chat.chat(request_id,session.provider_session_id,'为什么不能判断？',run_id=run.run_id))
        assert again==first and len(state['calls'])==calls+1
        with pytest.raises(ValueError,match='IDEMPOTENCY_CONFLICT'):
            asyncio.run(chat.chat(request_id,session.provider_session_id,'改过的问题',run_id=run.run_id))
        second=ask(chat,session,run,'我已经有知识库了，还缺什么？',parent_turn_id=first['turn_id'])
        payload=json.loads(state['calls'][-1]['body']['messages'][0]['content'])
        assert payload['history']==[{'question':first['question'],'answer':first['answer']}]
        assert payload['evidence']['run_overview']['cases'][0]['reference_complete'] is None
        assert payload['evidence']['run_overview']['cases'][0]['decision_reasons'][0]['code']=='REFERENCE_COMPLETENESS_UNCONFIRMED'
        assert 'HOLDOUT_PRIVATE' not in json.dumps(payload)
        assert 'model_inputs' not in json.dumps(payload) and 'api_key' not in json.dumps(payload)
        assert path.read_bytes()==before and not rag.store.list('retrieval_changes')
        assert [t['turn_id'] for t in chat.history(run_id=run.run_id)['turns']]==[first['turn_id'],second['turn_id']]
        assert len(state['calls'])==calls+2  # Restoring history has no model call.
        focused=ask(chat,session,run,'这道题呢？',case_id='gap')
        assert 'focused_case' in focused['sources']
        assert chat.history(run_id=run.run_id,case_id='gap')['turns'][0]['turn_id']==focused['turn_id']
        assert len(chat.history(run_id=run.run_id)['turns'])==2


def test_chat_rejects_cross_context_unknown_cases_and_forged_client_context(tmp_path):
    service,_,_=setup(tmp_path);rag=RetrievalService(service);chat=EvaluationChatService(rag)
    with assistant_server() as (url,state):
        session=ready(service,url);run=run_fixture(rag,session)
        first=ask(chat,session,run);calls=len(state['calls'])
        with pytest.raises(ValueError,match='CHAT_CONTEXT_MISMATCH'):
            ask(chat,session,run,case_id='gap',parent_turn_id=first['turn_id'])
        with pytest.raises(ValueError,match='CHAT_CASE_NOT_IN_RUN'):
            ask(chat,session,run,case_id='holdout')
        with pytest.raises(ValueError,match='CHAT_QUESTION_REQUIRED'):
            ask(chat,session,run,'  ')
        assert len(state['calls'])==calls
        (tmp_path/'other-workspace').mkdir()
        other,_,_=setup(tmp_path/'other-workspace')
        with pytest.raises(FileNotFoundError):
            EvaluationChatService(RetrievalService(other)).history(run_id=run.run_id)
        configure(lambda:service);service.retrieval=rag;client=TestClient(app)
        body={'request_id':str(uuid4()),'provider_session_id':session.provider_session_id,'run_id':run.run_id,'question':'解释结果'}
        for field in ('evidence','history','answer'):
            assert client.post('/experiments/ai/evaluation-chat',json={**body,field:'forged'}).status_code==422
        assert client.get('/experiments/ai/evaluation-chat',params={'run_id':run.run_id}).status_code==200


def test_chat_invalid_references_are_not_saved_and_recent_history_is_bounded(tmp_path):
    service,_,_=setup(tmp_path);rag=RetrievalService(service);chat=EvaluationChatService(rag)
    with assistant_server() as (url,state):
        session=ready(service,url);run=run_fixture(rag,session)
        state['mode']='bad_ref'
        with pytest.raises(ProviderFailure,match='AI_OUTPUT_INVALID'):
            ask(chat,session,run)
        assert chat.history(run_id=run.run_id)['turns']==[]
        state['mode']=None;parent=None
        for i in range(8):
            turn=ask(chat,session,run,f'请继续解释第 {i} 个问题。',parent_turn_id=parent)
            parent=turn['turn_id']
        payload=json.loads(state['calls'][-1]['body']['messages'][0]['content'])
        assert len(payload['history'])==6 and payload['history'][0]['question']=='请继续解释第 1 个问题。'
        assert len(chat.history(run_id=run.run_id)['turns'])==8
        new=ask(chat,session,run,'开始新一段。')
        assert len(chat.history(run_id=run.run_id)['turns'])==1
        assert new['conversation_id']!=turn['conversation_id']
        assert len([d for d in rag.store.list('ai_drafts') if d.kind=='EVALUATION_CHAT'])==9


def test_evidence_explanations_keep_unknowns_and_never_change_outcome():
    assert decision_reasons(None,None,'PASS')==[]
    missing=decision_reasons(None,None,'EVIDENCE_INSUFFICIENT')
    assert missing[0]['code']=='FROZEN_INPUT_MISSING'
    unknown=decision_reasons(None,{},'EVIDENCE_INSUFFICIENT')
    assert unknown[0]['code']=='INSUFFICIENT_REASON_UNRECORDED'
    gap=decision_reasons(None,{'missing_items':['REFERENCE_COMPLETENESS_UNCONFIRMED'],
        'item_checks':[{'status':'EVIDENCE_INSUFFICIENT','reason':'REFERENCE_COMPLETENESS_UNCONFIRMED'}]},'EVIDENCE_INSUFFICIENT')
    assert len(gap)==1 and '尚未确认' in gap[0]['message']
    assert '没有' not in gap[0]['message']  # Unconfirmed completeness is not absent knowledge.
