"""Contract checks; synthetic fixtures never certify a live Muse account."""
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from agent.api import muse as api
from agent.services import muse_gateway as service


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'ROOT', tmp_path)
    monkeypatch.setattr(service, 'DATA', tmp_path / 'data')
    monkeypatch.setattr(service, 'validate_session', AsyncMock(side_effect=lambda cookies: cookies))
    return tmp_path


@pytest.fixture
async def client(state):
    app = FastAPI()
    app.include_router(api.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
        base_url='http://127.0.0.1', headers={'X-Flowkit-Local-Auth': '1'}) as client:
        yield client


@pytest.mark.parametrize('driver,ok,available,expected', [
    ('mock', True, 1, False), ('browser', True, 1, True),
    ('browser', False, 1, False), ('browser', True, 0, False),
])
async def test_ready_requires_real_browser_and_account(state, monkeypatch, driver, ok, available, expected):
    monkeypatch.setattr(service, 'request', AsyncMock(return_value={'driver': {'driver': driver, 'ok': ok}, 'accounts': {'available': available}}))
    assert (await service.status())['ready'] is expected


async def test_disconnected_does_not_generate_or_fabricate_result(state, monkeypatch):
    monkeypatch.setattr(service, 'status', AsyncMock(return_value={'ready': False}))
    request = AsyncMock()
    monkeypatch.setattr(service, 'request', request)
    with pytest.raises(ValueError):
        await service.generate('image', 'a fox', '16:9', [])
    request.assert_not_called()


async def test_update_session_without_echoing_secrets(state, monkeypatch):
    monkeypatch.setattr(service, 'status', AsyncMock(return_value={'running': True, 'driver': 'browser'}))
    request = AsyncMock(side_effect=[{'data': [{'id': 'existing', 'label': 'FrameWeaver'}]}, {'account': {'id': 'existing'}}])
    monkeypatch.setattr(service, 'request', request)
    result = await service.save_session({key: 'sensitive-session-fixture' for key in service.COOKIES})
    assert 'sensitive-session-fixture' not in json.dumps(result)
    assert request.call_args.args == ('PATCH', '/admin/accounts/existing')


async def test_named_session_adds_account_without_overwriting_first(state, monkeypatch):
    monkeypatch.setattr(service, 'status', AsyncMock(return_value={'running': True, 'driver': 'browser'}))
    request = AsyncMock(side_effect=[{'data': [{'id': 'acc_first', 'label': 'FrameWeaver'}]}, {'account': {'id': 'acc_second'}}])
    monkeypatch.setattr(service, 'request', request)
    await service.save_session({key: 'new-private-session' for key in service.COOKIES}, label='Muse 2')
    assert request.call_args.args == ('POST', '/admin/accounts')
    assert request.call_args.kwargs['body']['label'] == 'Muse 2'


async def test_same_session_cannot_be_added_under_another_name(state, monkeypatch):
    monkeypatch.setattr(service, 'status', AsyncMock(return_value={'running': True, 'driver': 'browser'}))
    request = AsyncMock(return_value={'data': [{'id': 'acc_first', 'label': 'FrameWeaver'}]})
    monkeypatch.setattr(service, 'request', request)
    service.atomic_json(service.DATA / 'accounts.json', [{'label': 'FrameWeaver', 'cookies': {'hatch_sess': 'same-session'}}])
    with pytest.raises(ValueError, match='đã lưu'):
        await service.save_session({key: 'same-session' for key in service.COOKIES}, label='Muse 2')
    assert request.await_count == 1


@pytest.mark.parametrize('code,quota', [('upstream_quota_exhausted', True), ('rate_limited', False)])
async def test_http_rate_limit_is_not_automatically_called_quota(state, monkeypatch, code, quota):
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda req: httpx.Response(429, json={'error': {'code': code}}))
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=transport, **kwargs))
    with pytest.raises(ValueError) as error:
        await service.request('GET', '/test')
    assert isinstance(error.value, service.QuotaExhausted) is quota


async def test_streaming_chat_reports_incremental_text(state, monkeypatch):
    monkeypatch.setattr(service, 'require_ready', AsyncMock())
    original = httpx.AsyncClient
    events = ''.join('data: ' + json.dumps({'choices': [{'delta': {'content': part}}]}) + '\n\n'
                     for part in ['{"scenes":[', '{"title":"Sea"}]}']) + 'data: [DONE]\n\n'
    transport = httpx.MockTransport(lambda req: httpx.Response(200, headers={'content-type': 'text/event-stream'}, text=events))
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(transport=transport, **kwargs))
    callback = AsyncMock()
    result = await service.chat('Write scene prompts', on_text=callback)
    assert callback.await_count == 2
    assert callback.await_args_list[0].args[0] == '{"scenes":['
    assert result['text'] == '{"scenes":[{"title":"Sea"}]}'


async def test_auto_start_uses_saved_enabled_session_without_login_window(state, monkeypatch):
    monkeypatch.setattr(service, '_auto_start_state', {'auto_starting': False, 'auto_error': None})
    service.atomic_json(service.DATA / 'accounts.json', [{'enabled': True, 'cookies': {key: 'fixture' for key in service.REQUIRED_COOKIES}}])
    monkeypatch.setattr(service, 'validate_storage', AsyncMock())
    start = AsyncMock(return_value={'ready': True})
    login = AsyncMock()
    monkeypatch.setattr(service, 'start', start)
    monkeypatch.setattr(service, 'start_login', login)
    await service.auto_start_saved()
    start.assert_awaited_once()
    login.assert_not_called()
    assert service._auto_start_state == {'auto_starting': False, 'auto_error': None}


async def test_auto_start_skips_first_use_and_disabled_accounts(state, monkeypatch):
    start = AsyncMock()
    monkeypatch.setattr(service, 'start', start)
    monkeypatch.setattr(service, 'validate_storage', AsyncMock())
    await service.auto_start_saved()
    service.atomic_json(service.DATA / 'accounts.json', [{'enabled': False, 'cookies': {key: 'fixture' for key in service.REQUIRED_COOKIES}}])
    await service.auto_start_saved()
    start.assert_not_called()


async def test_auto_start_failure_does_not_crash_app_and_reports_reason(state, monkeypatch):
    monkeypatch.setattr(service, '_auto_start_state', {'auto_starting': False, 'auto_error': None})
    service.atomic_json(service.DATA / 'accounts.json', [{'enabled': True, 'cookies': {key: 'fixture' for key in service.REQUIRED_COOKIES}}])
    monkeypatch.setattr(service, 'validate_storage', AsyncMock())
    monkeypatch.setattr(service, 'start', AsyncMock(side_effect=ValueError('Không đọc được dữ liệu Muse')))
    await service.auto_start_saved()
    assert not service._auto_start_state['auto_starting']
    assert 'Không đọc được' in service._auto_start_state['auto_error']


async def test_incomplete_session_is_rejected_before_network(state, monkeypatch):
    request = AsyncMock()
    monkeypatch.setattr(service, 'request', request)
    with pytest.raises(ValueError):
        await service.save_session({'hatch_sess': 'private'})
    request.assert_not_called()


@pytest.mark.parametrize('kind', ['image', 'video'])
async def test_generate_persists_task_not_reference_or_session(state, monkeypatch, kind):
    monkeypatch.setattr(service, 'require_ready', AsyncMock())
    request = AsyncMock(return_value={'id': 'task_123abc', 'status': 'queued'})
    monkeypatch.setattr(service, 'request', request)
    refs = ['data:image/png;base64,aGVsbG8=']
    await service.generate(kind, 'A fox', '9:16', refs)
    body = request.call_args.kwargs['body']
    assert body['model'] == 'muse-' + kind
    assert body['size'] == '9:16'
    if kind == 'image':
        assert body['async'] and body['n'] == 1 and body['image'] == refs
    else:
        assert body['duration'] == 8 and body['image'] == refs[0]
    saved = (state / 'history.json').read_text()
    assert 'task_123abc' in saved and 'base64' not in saved


async def test_video_accepts_text_without_starting_frame(state, monkeypatch):
    monkeypatch.setattr(service, 'require_ready', AsyncMock())
    request = AsyncMock(return_value={'id': 'task_textvideo'})
    monkeypatch.setattr(service, 'request', request)
    await service.generate('video', 'Ocean cliffs and moving waves', '16:9', [])
    body = request.call_args.kwargs['body']
    assert 'image' not in body
    assert body['duration'] == 8 and body['model'] == 'muse-video'

async def test_task_exposes_only_local_media_names_and_sanitized_error(state, monkeypatch):
    service.atomic_json(state / 'history.json', [{'id': 'task_abc', 'kind': 'image'}])
    monkeypatch.setattr(service, 'request', AsyncMock(return_value={
        'status': 'failed', 'error': {'message': 'do-not-expose-secret'},
        'result': {'data': [{'url': url} for url in [
            'http://127.0.0.1:18610/v1/media/img_safe.png',
            'https://attacker.example/img.png',
            'http://127.0.0.1:18610/v1/media/../../api_key',
        ]]}}))
    result = await service.task('task_abc')
    assert result['media'] == ['img_safe.png']
    assert 'do-not-expose-secret' not in json.dumps(result)


@pytest.mark.parametrize('origin', ['https://evil.test', 'http://localhost.evil.test', 'null'])
async def test_other_origins_cannot_read_account_or_generate(client, origin):
    assert (await client.get('/api/muse/status', headers={'Origin': origin})).status_code == 403
    assert (await client.post('/api/muse/session', headers={'Origin': origin}, json={'cookies': {}, 'consent': True})).status_code == 403


async def test_session_requires_explicit_storage_consent(client):
    response = await client.post('/api/muse/session', json={'cookies': {}, 'consent': False})
    assert response.status_code == 422


async def test_remote_reference_fetch_not_allowed(client):
    response = await client.post('/api/muse/generate', json={'kind': 'image', 'prompt': 'test', 'references': ['http://192.168.1.1/private']})
    assert response.status_code == 422


async def test_gateway_start_failure_keeps_parent_alive():
    class FailedServer:
        async def serve(self):
            raise SystemExit(3)
    await service._serve(FailedServer())


async def test_successful_reconnect_clears_previous_startup_error(monkeypatch):
    monkeypatch.setattr(service, '_auto_start_state', {'auto_starting': False, 'auto_error': 'Old startup failure'})
    monkeypatch.setattr(service, 'status', AsyncMock(return_value={
        'running': True, 'ready': True, 'driver': 'browser', 'auto_error': 'Old startup failure'}))
    result = await service.start()
    assert result['auto_error'] is None
    assert service._auto_start_state['auto_error'] is None


def test_private_key_is_stable(state):
    first = service.api_key()
    assert len(first) >= 32 and service.api_key() == first


async def test_login_does_not_read_normal_chrome_profile(state, monkeypatch):
    monkeypatch.setattr(service, '_login', None)
    with pytest.raises(ValueError):
        await service.finish_login()


async def test_verified_session_without_optional_gateway_cookie_is_saved(state, monkeypatch):
    monkeypatch.setattr(service, 'status', AsyncMock(return_value={'running': True, 'driver': 'browser'}))
    request = AsyncMock(side_effect=[{'data': []}, {'account': {'id': 'new'}}])
    monkeypatch.setattr(service, 'request', request)
    result = await service.save_session({key: 'private-fixture' for key in service.REQUIRED_COOKIES}, verified=True)
    assert result['saved']
    assert set(request.call_args.kwargs['body']['cookies']) == service.REQUIRED_COOKIES
    assert 'private-fixture' not in json.dumps(result)


async def test_finish_login_refreshes_session_before_reading_cookies(state, monkeypatch):
    from unittest.mock import MagicMock
    from muse2api.drivers.browser.cdp import CDPSession
    browser = MagicMock()
    browser.close = AsyncMock()
    browser.send = AsyncMock(side_effect=[{'targetInfos': [{'type': 'page', 'url': 'https://muse.ai/thread/new', 'targetId': 'test'}]},
        {'cookies': [{'name': key, 'value': 'private-fixture', 'domain': '.muse.ai'} for key in service.REQUIRED_COOKIES]}])
    page = MagicMock(); page.close = AsyncMock(); page.evaluate = AsyncMock(return_value={'http': 200, 'status': 'assigned'})
    monkeypatch.setattr(CDPSession, 'connect', AsyncMock(side_effect=[browser, page]))
    login = MagicMock(); login.browser_ws_url = AsyncMock(return_value='ws://127.0.0.1:19211/test'); login.stop = AsyncMock()
    monkeypatch.setattr(service, '_login', login)
    saved = AsyncMock(return_value={'saved': True}); monkeypatch.setattr(service, 'save_session', saved)
    assert (await service.finish_login())['saved']
    assert saved.call_args.kwargs['verified'] is True
    assert 'hatch_gw' not in saved.call_args.args[0]
    assert "fetch('/api/session'" in page.evaluate.call_args.args[0]
    login.stop.assert_awaited_once()


async def test_finish_login_does_not_save_unassigned_session(state, monkeypatch):
    from unittest.mock import MagicMock
    from muse2api.drivers.browser.cdp import CDPSession
    browser = MagicMock(); browser.close = AsyncMock(); browser.send = AsyncMock(return_value={'targetInfos': [{'type': 'page', 'url': 'https://muse.ai/', 'targetId': 'test'}]})
    page = MagicMock(); page.close = AsyncMock(); page.evaluate = AsyncMock(return_value={'http': 401, 'status': 'expired'})
    monkeypatch.setattr(CDPSession, 'connect', AsyncMock(side_effect=[browser, page]))
    login = MagicMock(); login.browser_ws_url = AsyncMock(return_value='ws://127.0.0.1:19211/test')
    monkeypatch.setattr(service, '_login', login)
    saved = AsyncMock(); monkeypatch.setattr(service, 'save_session', saved)
    with pytest.raises(ValueError):
        await service.finish_login()
    saved.assert_not_called()


def test_browser_driver_supports_session_without_legacy_gateway_cookie():
    from muse2api.upstream.muse import missing_session_cookies
    cookies = {key: 'fixture' for key in service.REQUIRED_COOKIES}
    assert missing_session_cookies(cookies) == []
    cookies.pop('hatch_vml')
    assert 'hatch_vml' in missing_session_cookies(cookies)

