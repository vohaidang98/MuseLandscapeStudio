import asyncio
from unittest.mock import AsyncMock

import pytest

from agent.services import muse_gateway as gateway
from agent.services import muse_pacing


async def test_account_pacing_is_independent(monkeypatch):
    now = [100.0]
    sleeps = []
    monkeypatch.setattr(muse_pacing.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(muse_pacing.random, 'uniform', lambda low, high: 1.5)
    async def sleep(delay):
        sleeps.append(delay)
        now[0] += delay
    monkeypatch.setattr(muse_pacing.asyncio, 'sleep', sleep)
    pacer = muse_pacing.AccountPacer()
    callback = AsyncMock()
    await pacer.send('A', callback)
    await pacer.send('B', callback)
    await pacer.send('A', callback)
    assert sleeps == [0, 0, 1.5]
    assert callback.await_count == 3


async def test_waiting_account_does_not_block_other_account():
    pacer = muse_pacing.AccountPacer()
    gate = asyncio.Event()
    entered = asyncio.Event()
    async def blocked():
        entered.set()
        await gate.wait()
    task = asyncio.create_task(pacer.send('A', blocked))
    await entered.wait()
    other = AsyncMock()
    await asyncio.wait_for(pacer.send('B', other), 1)
    other.assert_awaited_once()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_accounts_api_does_not_return_cookie_fragments(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(gateway, 'DATA', tmp_path)
    (tmp_path / 'accounts.json').write_text(json.dumps([
        {'id': 'acc_123', 'label': 'Muse 2', 'enabled': True, 'status': 'active',
         'cookies': {'hatch_sess': 'secret-fragment'}, 'email': 'private@example.test'}]))
    request = AsyncMock(side_effect=ValueError('gateway unavailable'))
    monkeypatch.setattr(gateway, 'request', request)
    rows = await gateway.accounts()
    assert rows[0]['label'] == 'Muse 2'
    assert 'cookies' not in rows[0] and 'email' not in rows[0]
    request.assert_not_called()


async def test_saved_accounts_remain_visible_during_gateway_timeout(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(gateway, 'DATA', tmp_path)
    (tmp_path / 'accounts.json').write_text(json.dumps([
        {'id': 'acc_A', 'label': 'A', 'enabled': True, 'status': 'active'}]))
    monkeypatch.setattr(gateway, 'request', AsyncMock(side_effect=ValueError('timed out')))
    state = await gateway.status()
    assert state['saved_accounts'] == 1
    assert state['connection_uncertain'] and not state['ready']
    assert (await gateway.accounts())[0]['label'] == 'A'


async def test_saved_account_list_uses_valid_backup_without_leaking_secrets(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(gateway, 'DATA', tmp_path)
    (tmp_path / 'accounts.json').write_text('invalid json')
    (tmp_path / 'accounts.json.bak').write_text(json.dumps([
        {'id': 'acc_A', 'label': 'A', 'cookies': {'hatch_sess': 'secret'}}]))
    rows = await gateway.accounts()
    assert rows[0]['label'] == 'A' and 'cookies' not in rows[0]


async def test_delete_account_disables_then_removes_from_live_pool(monkeypatch):
    start = AsyncMock()
    request = AsyncMock()
    remaining = [{'id': 'acc_B', 'label': 'Muse B'}]
    monkeypatch.setattr(gateway, 'start', start)
    monkeypatch.setattr(gateway, 'request', request)
    monkeypatch.setattr(gateway, 'accounts', AsyncMock(return_value=remaining))
    assert await gateway.delete_account('acc_A') == remaining
    start.assert_awaited_once()
    assert request.await_args_list[0].args == ('PATCH', '/admin/accounts/acc_A')
    assert request.await_args_list[0].kwargs == {'body': {'enabled': False}}
    assert request.await_args_list[1].args == ('DELETE', '/admin/accounts/acc_A')
    assert request.await_count == 2


async def test_delete_account_rejects_invalid_identifier_before_any_action(monkeypatch):
    start = AsyncMock()
    monkeypatch.setattr(gateway, 'start', start)
    with pytest.raises(ValueError):
        await gateway.delete_account('../accounts.json')
    start.assert_not_called()


async def test_delete_account_endpoint_requires_local_auth(monkeypatch):
    import httpx
    from agent.muse_app import app
    delete = AsyncMock(return_value=[])
    monkeypatch.setattr(gateway, 'delete_account', delete)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8100') as client:
        assert (await client.post('/api/muse/accounts/acc_A/delete')).status_code == 403
        delete.assert_not_called()
        result = await client.post('/api/muse/accounts/acc_A/delete', headers={'X-Flowkit-Local-Auth': '1'})
        assert result.status_code == 200 and result.json() == []
        delete.assert_awaited_once_with('acc_A')
