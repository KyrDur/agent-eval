"""Optional, temporary release handoff. No HTTP endpoint or disk credential store.

An existing worker's private stdin pipe is the source. The receiver is a Unix
socket in an owner-only directory, available only during an explicit release.
"""
import asyncio
import errno
import json
import os
import re
import socket
import stat
import struct
from pathlib import Path

class MemoryHandoff:
    def __init__(self, registry, path):
        self.registry=registry;self.path=Path(path);self.server=None;self.receipts=set()
        self.seal_path=self.path.with_name(self.path.name+'.sealed')

    async def start(self):
        parent=self.path.parent
        if not parent.is_dir() or parent.stat().st_uid!=os.geteuid() or stat.S_IMODE(parent.stat().st_mode)!=0o700:
            raise RuntimeError('HANDOFF_DIRECTORY_INVALID')
        # A release remains sealed across a crash/restart. This marker contains
        # no credential, session ID, or other payload from the private pipe.
        if self.seal_path.exists():
            sealed=self.seal_path.lstat()
            if not stat.S_ISREG(sealed.st_mode) or sealed.st_uid!=os.geteuid() or stat.S_IMODE(sealed.st_mode)!=0o600:
                raise RuntimeError('HANDOFF_SEAL_INVALID')
            self.clear_handoff_hint()
            return self
        if self.path.exists():
            existing=self.path.lstat()
            if not stat.S_ISSOCK(existing.st_mode) or existing.st_uid!=os.geteuid() or stat.S_IMODE(existing.st_mode)!=0o600:
                raise RuntimeError('HANDOFF_SOCKET_INVALID')
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as probe:
                probe.settimeout(0.25)
                try:probe.connect(str(self.path))
                except OSError as error:
                    if error.errno not in {errno.ECONNREFUSED,errno.ENOENT}:raise RuntimeError('HANDOFF_SOCKET_EXISTS') from None
                else:raise RuntimeError('HANDOFF_SOCKET_EXISTS')
            self.path.unlink(missing_ok=True)
        self.server=await asyncio.start_unix_server(self.accept,path=str(self.path),limit=65536)
        self.path.chmod(0o600)
        return self

    def clear_handoff_hint(self):
        # Retrieval reconciliation is suspended only during the live transfer,
        # rather than for the lifetime of this Docker environment setting.
        if os.getenv('AGENTEVAL_HANDOFF_SOCKET')==str(self.path):
            os.environ.pop('AGENTEVAL_HANDOFF_SOCKET',None)

    def import_connection(self,payload):
        if set(payload)!={'workspace_ref','provider_session_id','key','judge_key'}:raise ValueError()
        identity=payload['workspace_ref'];sid=payload['provider_session_id']
        if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{64}',identity):raise ValueError()
        if not isinstance(sid,str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}',sid):raise ValueError()
        if not (self.registry.root/identity/'workspace.json').is_file():raise ValueError()
        key=payload['key'];judge_key=payload['judge_key']
        if not isinstance(key,str) or not 8<=len(key)<=16000:raise ValueError()
        if judge_key is not None and (not isinstance(judge_key,str) or not 8<=len(judge_key)<=16000):raise ValueError()
        service=self.registry.get(identity)
        session=service.store.get('provider_sessions',sid)
        if session.status=='DELETED':raise ValueError()
        judge_id=session.configuration.judge_provider_session_id
        if bool(judge_id)!=bool(judge_key):raise ValueError()
        if judge_id and service.store.get('provider_sessions',judge_id).status=='DELETED':raise ValueError()
        # All checks precede the memory-only update. Never return a key-derived ID.
        pairs=[(sid,key)]+([(judge_id,judge_key)] if judge_id else [])
        for identifier,value in pairs:
            prior=service.providers._keys.get(identifier)
            if prior is not None and prior!=value:raise ValueError()
        for identifier,value in pairs:
            service.providers._keys[identifier]=value
            if value not in service.store.forbidden_values:service.store.forbidden_values+=(value,)
            self.receipts.add((identity,identifier))
        return {'status':'IMPORTED','workspace_ref':identity,'session_ids':[identifier for identifier,_ in pairs]}

    async def accept(self,reader,writer):
        try:
            peer=writer.get_extra_info('socket')
            if hasattr(socket,'SO_PEERCRED'):
                _,uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                if uid not in {os.geteuid(),0}:raise ValueError()
            line=await asyncio.wait_for(reader.readline(),timeout=5)
            if len(line)>65535:raise ValueError()
            payload=json.loads(line)
            if payload=={'status':True}:
                result={'status':'OPEN','receipts':[{'workspace_ref':a,'provider_session_id':b} for a,b in sorted(self.receipts)]}
            elif payload=={'seal':True}:
                descriptor=os.open(self.seal_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                try:os.fsync(descriptor)
                finally:os.close(descriptor)
                self.server.close()
                self.path.unlink(missing_ok=True)
                self.clear_handoff_hint()
                result={'status':'SEALED','imported_session_count':len(self.receipts)}
            else:result=self.import_connection(payload)
        except Exception:
            result={'status':'REJECTED'}  # Never log input or exception details.
        try:
            writer.write((json.dumps(result)+'\n').encode());await writer.drain()
        finally:
            writer.close();await writer.wait_closed()

    async def close(self):
        if self.server:
            self.server.close();await self.server.wait_closed()
            self.path.unlink(missing_ok=True)
