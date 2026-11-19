from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agent.services import muse_performance as performance, muse_gateway as gateway, muse_scenes as scenes, muse_queue as queue, muse_tokens as tokens


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, 'ROOT', tmp_path)
    monkeypatch.setattr(scenes, '_workers', {})
    monkeypatch.setattr(scenes, '_planning', {})
    monkeypatch.setattr(queue, 'read', lambda: {'running': False})
    monkeypatch.setattr(tokens, 'status', lambda: {'running': False})
    monkeypatch.setattr(gateway, '_services', None)
    monkeypatch.setattr(gateway, '_role_scheduler', None)
    monkeypatch.setattr(gateway, '_driver', None)


def test_default_is_balanced_six_videos(state):
    assert performance.current()['max_videos'] == 6
    assert performance.current()['max_accounts'] == 3
    assert performance.current()['poll_seconds'] == 5
    assert performance.current()['automatic']


@pytest.mark.parametrize('preset,accounts,videos', [('eco',2,1),('balanced',3,2),('fast',5,3)])
async def test_presets_are_saved_and_applied_to_pool_and_roles(state, monkeypatch, preset, accounts, videos):
    roles=SimpleNamespace(selected=['old'], prompt_id='old')
    pool=SimpleNamespace(stats=lambda: {'inflight':0})
    driver=SimpleNamespace(settings=SimpleNamespace(account_max_concurrency=3))
    monkeypatch.setattr(gateway, '_role_scheduler', roles)
    monkeypatch.setattr(gateway, '_services', SimpleNamespace(pool=pool))
    monkeypatch.setattr(gateway, '_driver', driver)
    await performance.save(preset)
    assert performance.current()['max_videos'] == accounts * videos
    assert roles.max_accounts == accounts and roles.videos_per_account == videos
    assert pool.max_concurrency == videos and driver.settings.account_max_concurrency == videos
    assert roles.selected == []


async def test_active_work_blocks_preset_change(state, monkeypatch):
    monkeypatch.setattr(scenes, '_workers', {'active': object()})
    with pytest.raises(ValueError):
        await performance.save('eco')
    assert performance.current()['preset'] == 'balanced'


async def test_busy_pool_blocks_change_even_after_queue_stopped(state, monkeypatch):
    monkeypatch.setattr(gateway, '_services', SimpleNamespace(pool=SimpleNamespace(stats=lambda: {'inflight':1})))
    with pytest.raises(ValueError):
        await performance.save('eco')


async def test_unknown_preset_rejected(state):
    with pytest.raises(ValueError):
        await performance.save('unlimited')


async def test_automatic_preference_persists_and_reconfigures_sampler(state, monkeypatch):
    from unittest.mock import Mock
    governor = SimpleNamespace(configure=Mock())
    driver = SimpleNamespace(settings=SimpleNamespace(), governor=governor)
    monkeypatch.setattr(gateway, '_driver', driver)
    await performance.save('balanced', automatic=False)
    assert not performance.current()['automatic']
    governor.configure.assert_called_once_with(6, False)
    await performance.save('eco')
    assert not performance.current()['automatic']
