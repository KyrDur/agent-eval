"""Release handoff with synthetic credentials; business JSON stays byte-identical."""
import asyncio
import json
import os
from types import SimpleNamespace as NS
from pathlib import Path
import pytest
import tempfile
from experiments.memory_handoff import MemoryHandoff
from experiments.providers import ProviderConfig,ProviderSessions
from experiments.store import JsonStore

def test_handoff_uses_private_socket_without_saving_credentials(tmp_path,monkeypatch):
    async def exercise():
        identity='a'*64;directory=tmp_path/identity;directory.mkdir()
        (directory/'workspace.json').write_text('{}')
        store=JsonStore(directory/'artifacts');providers=ProviderSessions(store)
        key='synthetic-main-only-12345'
        session=providers.create(ProviderConfig(model='synthetic'),key)
        providers._keys.clear();store.forbidden_values=()
        before={str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}
        registry=NS(root=tmp_path,get=lambda i:NS(store=store,providers=providers))
        private=Path(tempfile.mkdtemp(dir='/tmp',prefix='jh-'))
        monkeypatch.setenv('AGENTEVAL_HANDOFF_SOCKET',str(private/'handoff.sock'))
        receiver=await MemoryHandoff(registry,private/'handoff.sock').start()
        async def send(payload):
            reader,writer=await asyncio.open_unix_connection(str(receiver.path))
            writer.write((json.dumps(payload)+'\n').encode());await writer.drain()
            result=json.loads(await reader.readline());writer.close();await writer.wait_closed()
            return result
        payload={'workspace_ref':identity,'provider_session_id':session.provider_session_id,'key':key,'judge_key':None}
        result=await send(payload)
        assert result['status']=='IMPORTED' and key not in json.dumps(result)
        assert providers.public(providers.get(session.provider_session_id))['credential_status']=='PRESENT'
        assert (await send(payload))==result
        assert {str(p):p.read_bytes() for p in tmp_path.rglob('*.json')}==before
        assert (receiver.path.stat().st_mode&0o777)==0o600
        assert (await send({**payload,'workspace_ref':'b'*64}))=={'status':'REJECTED'}
        assert (await send({'status':True}))['receipts']==[{'workspace_ref':identity,'provider_session_id':session.provider_session_id}]
        assert (await send({'seal':True}))['status']=='SEALED'
        assert 'AGENTEVAL_HANDOFF_SOCKET' not in os.environ
        await receiver.close()
        assert not receiver.path.exists()
        assert receiver.seal_path.read_bytes()==b''
        monkeypatch.setenv('AGENTEVAL_HANDOFF_SOCKET',str(receiver.path))
        reopened=await MemoryHandoff(registry,receiver.path).start()
        assert reopened.server is None and not receiver.path.exists()
        assert 'AGENTEVAL_HANDOFF_SOCKET' not in os.environ
        receiver.seal_path.unlink()
        private.rmdir()
    asyncio.run(exercise())

def test_handoff_rejects_shared_directory(tmp_path):
    tmp_path.chmod(0o755)
    with pytest.raises(RuntimeError,match='HANDOFF_DIRECTORY_INVALID'):
        asyncio.run(MemoryHandoff(NS(),tmp_path/'handoff.sock').start())

def test_handoff_recovers_abandoned_socket_but_preserves_live_receiver():
    import socket
    async def exercise():
        private=Path(tempfile.mkdtemp(dir='/tmp',prefix='jh-'))
        path=private/'r.sock'
        abandoned=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        abandoned.bind(str(path));path.chmod(0o600);abandoned.close()
        receiver=await MemoryHandoff(NS(),path).start()
        with pytest.raises(RuntimeError,match='HANDOFF_SOCKET_EXISTS'):
            await MemoryHandoff(NS(),path).start()
        assert receiver.server.is_serving()
        await receiver.close();private.rmdir()
    asyncio.run(exercise())

def test_handoff_never_removes_unexpected_files():
    async def exercise():
        private=Path(tempfile.mkdtemp(dir='/tmp',prefix='jh-'))
        path=private/'r.sock';path.write_text('preserve');path.chmod(0o600)
        with pytest.raises(RuntimeError,match='HANDOFF_SOCKET_INVALID'):
            await MemoryHandoff(NS(),path).start()
        assert path.read_text()=='preserve'
        path.unlink();private.rmdir()
    asyncio.run(exercise())

def test_existing_worker_pipe_can_handoff_without_stopping_original_vault(tmp_path):
    import ast
    import sys
    from experiments.operations_models import DomainVersion,EvidenceBatch,InferenceJob
    from experiments.canonical import digest
    from evaluation.calibration import RUBRIC_TEMPLATE
    async def exercise():
        identity='c'*64;directory=tmp_path/identity;directory.mkdir();(directory/'workspace.json').write_text('{}')
        old_store=JsonStore(directory/'artifacts');old=ProviderSessions(old_store)
        key='isolated-private-pipe-credential-12345'
        session=old.create(ProviderConfig(model='fixture-worker'),key)
        new_store=JsonStore(directory/'artifacts');new=ProviderSessions(new_store)
        registry=NS(root=tmp_path,get=lambda i:NS(store=new_store,providers=new))
        private=Path(tempfile.mkdtemp(dir='/tmp',prefix='jh-'))
        receiver=await MemoryHandoff(registry,private/'r.sock').start()
        marker='handoff_fixture_'
        profile=DomainVersion(domain_id='release_handoff_fixture',version=1,name='Internal handoff',business_scope='No inference',
            judge_prompt='No model calls',rubric=RUBRIC_TEMPLATE,content_hash=digest('fixture'))
        batch=EvidenceBatch(domain_id=profile.domain_id,profile_id=profile.profile_id,name='Empty maintenance batch',raw_records=[],records=[],
            mapping={},processing={'raw_count':0},confirmed_by='isolated-test',confirmation_reason='In-memory handoff only',content_hash=digest([]))
        job=InferenceJob(job_id=marker+'job',request_id='fixture',domain_id=profile.domain_id,batch_id=batch.batch_id,
            profile_id=profile.profile_id,provider_session_id=session.provider_session_id,provider_configuration=session.configuration.model_dump(),
            rule_snapshot=profile.model_dump(),expected_ids=[],window={'kind':'MEMORY_ONLY_RELEASE_TRANSFER','socket':str(receiver.path)})
        old_store.put('operation_domains',profile);old_store.put('evidence_batches',batch);old_store.put('inference_jobs',job)
        # The public regression must run without private deployment helpers.
        source=Path(__file__).parent/'fixtures/handoff_worker_bridge.py'
        raw=source.read_text()
        deployment=Path(__file__).resolve().parents[2]/'deployment/deploy-preserving-connections.py'
        if deployment.exists():
            tree=ast.parse(deployment.read_text())
            deployed=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.startswith('# --MEMORY-HANDOFF--'))
            assert raw==deployed
        prefix=raw.replace('MARKER',repr(marker)).replace('SOCKET_PATH',repr(str(receiver.path)))
        program="__package__='experiments'\n"+prefix
        process=await asyncio.create_subprocess_exec(sys.executable,'-c',program,str(old_store.root),job.job_id,
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout,stderr=await process.communicate(json.dumps({'key':key,'judge_key':None}).encode())
        assert process.returncode==0,(stdout,stderr)
        assert not stdout and not stderr
        assert old.public(old.get(session.provider_session_id))['credential_status']=='PRESENT'
        assert new.public(new.get(session.provider_session_id))['credential_status']=='PRESENT'
        assert old_store.get('inference_jobs',job.job_id).status=='COMPLETE'
        assert all(key not in p.read_text() for p in tmp_path.rglob('*.json'))
        await receiver.close();private.rmdir()
    asyncio.run(exercise())
