"""Explicit opt-in shared DeepSeek connection; the credential stays server-side."""
import asyncio
import os
import time
from pathlib import Path
import httpx
from fastapi import APIRouter
from .api import service
from .providers import ProviderConfig

router = APIRouter(prefix='/experiments/site-provider')
_lock = asyncio.Lock()
_cached = None
_cached_at = 0.0
_cached_key = None


def credential():
    filename = os.getenv('AGENTEVAL_SITE_API_KEY_FILE', '/state/site-api-key')
    if not filename:
        return None
    try:
        key = Path(filename).read_text().strip()
        return key if len(key) >= 8 else None
    except OSError:
        return None


async def availability():
    global _cached, _cached_at, _cached_key
    key = credential()
    if not key:
        return {'status': 'NOT_CONFIGURED', 'available': False}
    async with _lock:
        if _cached_key == key and _cached is not None and time.monotonic() - _cached_at < 15:
            return dict(_cached)
        result = {'status': 'CHECK_FAILED', 'available': False}
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await client.get('https://api.deepseek.com/user/balance',
                                            headers={'Authorization': 'Bearer ' + key})
            if response.status_code == 200:
                body = response.json()
                if body.get('is_available') is True:
                    result = {'status': 'AVAILABLE', 'available': True}
                elif body.get('is_available') is False:
                    result = {'status': 'NO_BALANCE', 'available': False}
            elif response.status_code in (401, 403):
                result = {'status': 'AUTH_FAILED', 'available': False}
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            pass
        _cached, _cached_at, _cached_key = result, time.monotonic(), key
        return dict(result)


@router.post('/check')
async def check():
    return await availability()


@router.post('/connect')
async def connect():
    status = await availability()
    if not status['available']:
        return status
    key = credential()
    if not key:
        return {'status': 'NOT_CONFIGURED', 'available': False}
    providers = service().providers
    config = ProviderConfig(provider='openai-compatible', base_url='https://api.deepseek.com/v1',
                            model='deepseek-chat', max_tokens=1024, max_calls=100,
                            timeout_seconds=60, completion_token_parameter='max_tokens',
                            thinking_mode='disabled')
    identifier = getattr(providers, '_site_identifier', None)
    if identifier not in providers._keys or providers._keys.get(identifier) != key:
        identifier = providers.create(config, key).provider_session_id
        providers._site_identifier = identifier
    result = await providers.test(identifier)
    if result['status'] != 'SUCCESS':
        return {'status': 'CONNECTION_FAILED', 'available': False}
    return {'status': 'SUCCESS', 'available': True,
            'session': providers.public(providers.get(identifier))}
