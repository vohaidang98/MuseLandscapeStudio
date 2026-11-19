from types import SimpleNamespace
from unittest.mock import AsyncMock
import json

import pytest

from agent.services import muse_tokens as tokens
from agent.services import muse_gateway as gateway
from agent.services.speech_store import atomic_json


@pytest.mark.parametrize('label', ['29B', '30B', '1.5B', '250M', '0'])
def test_reads_only_additional_tokens_left_label(label):
    text = f'Usage\nFree plan\n100% used\nAdditional tokens\nNever expires\n3% used ({label} tokens left)\nUpgrade'
    assert tokens.parse_tokens(text) == {'remaining_label': label}


@pytest.mark.parametrize('text', ['Free plan 100% used', 'Additional tokens\nLoading…', 'Video limit for the last 24 hours'])
def test_missing_data_is_not_zero_tokens(text):
    with pytest.raises(ValueError):
        tokens.parse_tokens(text)


async def test_reads_settings_in_separate_tab_and_always_closes_it():
    session = SimpleNamespace(send=AsyncMock(), evaluate=AsyncMock(side_effect=[True, None, 'Additional tokens\n3% used (29B tokens left)']))
    tab = SimpleNamespace(session=session)
    driver = SimpleNamespace(_checkout=AsyncMock(return_value=tab), _close_tab=AsyncMock())
    assert (await tokens.read_account(driver, object()))['remaining_label'] == '29B'
    driver._close_tab.assert_awaited_once_with(tab)
    assert not any('fill_input' in str(call) or 'CLICK_SEND' in str(call) for call in session.evaluate.await_args_list)


@pytest.fixture
def token_state(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, 'ROOT', tmp_path)
    monkeypatch.setattr(gateway, 'DATA', tmp_path)
    monkeypatch.setattr(gateway, 'start', AsyncMock())
    monkeypatch.setattr(gateway, '_driver', object())
    monkeypatch.setattr(tokens, '_task', None)
    monkeypatch.setattr(tokens, '_state', {'running': False, 'completed': 0, 'total': 0, 'account_id': None})
    (tmp_path / 'accounts.json').write_text(json.dumps([{'id': 'acc_A', 'label': 'A', 'cookies': {'hatch_sess': 'secret'}}]))
    return tmp_path


async def test_refresh_caches_only_usage_data(token_state, monkeypatch):
    monkeypatch.setattr(tokens, 'read_account', AsyncMock(return_value={'remaining_label': '29B'}))
    assert (await tokens.refresh('acc_A'))['running']
    await tokens._task
    value = tokens.cache()['acc_A']
    assert value['remaining_label'] == '29B' and value['checked_at'] > 0
    assert 'secret' not in json.dumps(tokens.cache())
    assert not tokens.status()['running']


async def test_failed_refresh_keeps_last_known_value(token_state, monkeypatch):
    atomic_json(token_state / 'additional-tokens.json', {'acc_A': {'remaining_label': '29B', 'checked_at': 100}})
    monkeypatch.setattr(tokens, 'read_account', AsyncMock(side_effect=ValueError('Chưa đọc được')))
    await tokens.refresh('acc_A')
    await tokens._task
    value = tokens.cache()['acc_A']
    assert value['remaining_label'] == '29B' and value['checked_at'] == 100
    assert value['error'] == 'Chưa đọc được'


async def test_auto_refresh_reads_only_quota_exhausted_accounts(token_state, monkeypatch):
    import time
    rows = [{'id':'acc_A', 'meta':{'quota_exhausted_until': time.time() + 3600}}, {'id':'acc_B', 'meta':{}}]
    (token_state / 'accounts.json').write_text(json.dumps(rows))
    reader = AsyncMock(return_value={'remaining_label':'29B'})
    monkeypatch.setattr(tokens, 'read_account', reader)
    await tokens.refresh()
    await tokens._task
    assert reader.await_count == 1
    assert reader.await_args.args[1].id == 'acc_A'
    assert 'acc_B' not in tokens.cache()
    await tokens.refresh()
    assert reader.await_count == 1


async def test_failed_usage_read_also_closes_its_tab():
    session = SimpleNamespace(send=AsyncMock(), evaluate=AsyncMock(side_effect=RuntimeError('page closed')))
    tab = SimpleNamespace(session=session)
    driver = SimpleNamespace(_checkout=AsyncMock(return_value=tab), _close_tab=AsyncMock())
    with pytest.raises(RuntimeError):
        await tokens.read_account(driver, object())
    driver._close_tab.assert_awaited_once_with(tab)


@pytest.mark.parametrize('fails', [False, True])
async def test_quota_drained_account_checked_once_during_video_production(token_state, monkeypatch, fails):
    import time
    from muse2api.accounts.model import Account
    from agent.services import muse_scenes
    until = time.time() + 3600
    limited = Account(id='acc_A', meta={'quota_exhausted_until': until})
    healthy = Account(id='acc_B')
    driver = SimpleNamespace(muse_pool=SimpleNamespace(all=lambda: [limited, healthy], _inflight={}),
        _opening={}, _tabs={})
    monkeypatch.setattr(muse_scenes, '_workers', {'running': object()})
    reader = AsyncMock(side_effect=ValueError('Không rõ') if fails else None,
        return_value={'remaining_label': '145M'})
    monkeypatch.setattr(tokens, 'read_account', reader)
    await tokens.refresh_quota_idle(driver)
    assert driver.muse_token_pending == {'acc_A'}
    await tokens._task
    assert driver.muse_token_pending == set()
    value = tokens.cache()['acc_A']
    assert value['quota_observed_until'] == until
    assert value.get('attempted_at' if fails else 'checked_at', 0) > 0
    await tokens.refresh_quota_idle(driver)
    assert reader.await_count == 1
    assert reader.await_args.args[1].id == 'acc_A'


@pytest.mark.parametrize('busy_source', ['inflight', 'opening', 'tab'])
async def test_quota_token_read_waits_for_account_work_to_drain(token_state, monkeypatch, busy_source):
    import time
    from muse2api.accounts.model import Account
    account = Account(id='acc_A', meta={'quota_exhausted_until': time.time() + 3600})
    driver = SimpleNamespace(muse_pool=SimpleNamespace(all=lambda: [account], _inflight={'acc_A': 1} if busy_source == 'inflight' else {}),
        _opening={'acc_A': 1} if busy_source == 'opening' else {},
        _tabs={'acc_A': [SimpleNamespace(busy=True, closed=False)]} if busy_source == 'tab' else {})
    reader = AsyncMock()
    monkeypatch.setattr(tokens, 'read_account', reader)
    await tokens.refresh_quota_idle(driver)
    assert tokens._task is None
    reader.assert_not_awaited()


async def test_quota_scanner_does_not_open_chrome_tabs_during_gateway_startup(token_state, monkeypatch):
    reader = AsyncMock()
    monkeypatch.setattr(tokens, 'read_account', reader)
    await tokens.refresh_quota_idle(SimpleNamespace(muse_gateway_ready=False))
    assert tokens._task is None
    reader.assert_not_awaited()
