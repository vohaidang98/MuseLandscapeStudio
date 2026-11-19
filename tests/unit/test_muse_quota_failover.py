import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from muse2api.accounts.model import Account, AccountStatus
from muse2api.accounts.pool import AccountPool
from muse2api.accounts.store import JsonAccountStore
from muse2api.services.gateway import Gateway
from muse2api.drivers.base import ChatRequest
from muse2api.errors import UpstreamQuotaError, UpstreamGlitch, quota_reply
from agent.services import muse_gateway


async def make_pool(tmp_path, count=4):
    pool = AccountPool(JsonAccountStore(tmp_path / 'accounts.json'), strategy='lru', max_concurrency=5, acquire_timeout=.1)
    for i in range(count):
        await pool.upsert(Account(id=f'acc_{i}', label=f'Muse {i}'))
    return pool


async def test_quota_failover_visits_every_account_even_with_other_retries_disabled(tmp_path):
    pool = await make_pool(tmp_path)
    service = Gateway(pool, SimpleNamespace(requires_account=True), max_failover=0)
    calls = []
    async def run(account):
        calls.append(account.id)
        if account.id != 'acc_3':
            raise UpstreamQuotaError('daily limit reached')
        return 'video-result'
    assert await service._run(run) == 'video-result'
    assert calls == ['acc_0', 'acc_1', 'acc_2', 'acc_3']
    assert pool.stats()['available'] == 1
    assert pool.stats()['inflight'] == 0
    calls.clear()
    assert await service._run(run) == 'video-result'
    assert calls == ['acc_3']


async def test_all_quota_stops_without_duplicate_attempts_and_survives_restart(tmp_path):
    pool = await make_pool(tmp_path, 2)
    service = Gateway(pool, SimpleNamespace(requires_account=True), max_failover=0)
    run = AsyncMock(side_effect=UpstreamQuotaError('daily limit reached'))
    with pytest.raises(UpstreamQuotaError):
        await service._run(run)
    assert run.await_count == 2
    restored = AccountPool(pool.store)
    await restored.load()
    with pytest.raises(UpstreamQuotaError):
        await restored.acquire()
    assert restored.stats()['inflight'] == 0


async def test_old_parallel_success_cannot_remove_quota_block(tmp_path):
    pool = await make_pool(tmp_path, 1)
    old, failed = await pool.acquire(), await pool.acquire()
    await pool.release(failed, UpstreamQuotaError('limit reached'))
    await pool.release(old)
    assert not old.is_available()
    assert old.status == AccountStatus.COOLING
    assert pool.stats()['inflight'] == 0
    old.cooldown_until = time.time() - 1
    old.meta['quota_exhausted_until'] = time.time() - 1
    assert old.is_available()


async def test_generic_failure_does_not_automatically_duplicate_media(tmp_path):
    service = Gateway(await make_pool(tmp_path, 2), SimpleNamespace(requires_account=True), max_failover=0)
    run = AsyncMock(side_effect=UpstreamGlitch('uncertain result'))
    with pytest.raises(UpstreamGlitch):
        await service._run(run)
    assert run.await_count == 1


async def test_stream_fails_over_before_emitting_and_never_splices_partial_json(tmp_path):
    pool = await make_pool(tmp_path, 2)
    async def stream(account, req):
        if account.id == 'acc_0':
            raise UpstreamQuotaError('daily limit reached')
        yield 'complete-json'
    service = Gateway(pool, SimpleNamespace(requires_account=True, chat_stream=stream), max_failover=0)
    assert [x async for x in service.chat_stream(ChatRequest(prompt='scenes', model='muse'))] == ['complete-json']
    async def partial(account, req):
        yield 'partial-json'
        raise UpstreamQuotaError('daily limit reached')
    service.driver.chat_stream = partial
    with pytest.raises(UpstreamQuotaError):
        _ = [x async for x in service.chat_stream(ChatRequest(prompt='scenes', model='muse'))]


@pytest.mark.parametrize('text', [
    "You've reached your video limit for the last 24 hours",
    "The generation failed because you've reached your video limit",
    'Video budget exhausted', 'Daily limit reached', 'Out of credits',
    'You have hit the weekly usage limit',
    "The 24-hour video limit is still in place, so this one wasn't generated — retrying right now won't help.",
    "The video limit is still active, so I couldn't generate this one.",
    "I couldn't generate this one — your 24-hour video limit is still reached.",
    "It's blocked by the 24-hour video limit again, so no video was made or delivered.",
    "You've reached your usage limit. Your full weekly usage will reset on Monday.",
    "Your 24‑hour video limit is still reached.",
    "The 24\u2066-hour\u2069 video limit is still in place.",
])
def test_explicit_quota_replies(text):
    assert quota_reply(text)


@pytest.mark.parametrize('text', ['Video created successfully', 'What is the video limit?', 'Create a landscape without people',
    'The sky is still active with lightning', 'Generate a 24-hour time lapse video',
    'The video is still generating', 'The video has reached the beach', 'Your video is ready'])
def test_ordinary_replies_are_not_quota(text):
    assert not quota_reply(text)


async def test_partial_chat_quota_does_not_stop_other_accounts(monkeypatch):
    monkeypatch.setattr(muse_gateway, 'status', AsyncMock(return_value={'available': 1}))
    with pytest.raises(ValueError) as exc:
        await muse_gateway.chat_quota_error()
    assert not isinstance(exc.value, muse_gateway.QuotaExhausted)
    monkeypatch.setattr(muse_gateway, 'status', AsyncMock(return_value={'available': 0}))
    with pytest.raises(muse_gateway.QuotaExhausted):
        await muse_gateway.chat_quota_error()


async def test_sidebar_history_does_not_trigger_quota_but_current_reply_does():
    from muse2api.drivers.browser.driver import BrowserDriver
    driver = object.__new__(BrowserDriver)
    session = SimpleNamespace(evaluate=AsyncMock(return_value={
        'tail': 'Old thread: daily limit reached', 'lastText': 'Created the video successfully', 'generating': False}))
    tab = SimpleNamespace(session=session)
    assert (await driver._state(tab))['lastText'] == 'Created the video successfully'
    session.evaluate.return_value = {'lastText': "You've reached your video limit for the last 24 hours", 'generating': False}
    with pytest.raises(UpstreamQuotaError):
        await driver._state(tab)


@pytest.mark.parametrize('generating', [True, False])
async def test_explicit_quota_with_stuck_spinner_fails_immediately(generating):
    from muse2api.drivers.browser.driver import BrowserDriver
    driver = object.__new__(BrowserDriver)
    session = SimpleNamespace(evaluate=AsyncMock(return_value={
        'agentCount': 1, 'lastText': 'The 24-hour video limit is still in place, so no video was generated.',
        'generating': generating, 'attachments': []}))
    tab = SimpleNamespace(session=session)
    driver._send = AsyncMock()
    with pytest.raises(UpstreamQuotaError):
        await driver._wait_media(tab, {'agentCount': 0}, 'video', 600, None, None)
    driver._send.assert_not_awaited()
    assert session.evaluate.await_count == 1


def test_paced_send_checks_persisted_account_block(tmp_path, monkeypatch):
    from agent.services.speech_store import atomic_json
    monkeypatch.setattr(muse_gateway, 'DATA', tmp_path)
    atomic_json(tmp_path / 'accounts.json', [{'id': 'acc_A', 'meta': {'quota_exhausted_until': time.time() + 3600}},
                                            {'id': 'acc_B', 'meta': {}}])
    assert muse_gateway.account_quota_blocked('acc_A')
    assert not muse_gateway.account_quota_blocked('acc_B')
