import asyncio
import math
import os

import pytest

from agent.services.muse_adaptive import AdaptiveGovernor, WindowsLoad
from agent.services.muse_roles import AccountRoles
from muse2api.accounts.pool import AccountPool
from muse2api.accounts.model import Account
from muse2api.accounts.store import JsonAccountStore


def sample(cpu=40, ram=65, free=4):
    return {'cpu': cpu, 'ram': ram, 'free_gb': free}


def test_stable_resources_ramp_slowly_without_exceeding_user_preset():
    governor = AdaptiveGovernor(6)
    assert governor.limit(now=0) == 2
    for second in range(0, 300, 5):
        governor.observe(sample(), now=second)
        assert 1 <= governor.limit(now=second) <= 6
    assert governor.target == 6


def test_cpu_spike_does_not_throttle_but_sustained_load_does():
    governor = AdaptiveGovernor(6)
    for second in range(0, 180, 5):
        governor.observe(sample(), now=second)
    before = governor.target
    governor.observe(sample(cpu=99), now=200)
    assert governor.target == before
    governor.observe(sample(), now=205)
    assert governor.target == before
    governor.observe(sample(cpu=99), now=210)
    governor.observe(sample(cpu=99), now=215)
    assert governor.target < before
    assert governor.target >= 1


def test_critical_memory_pauses_and_requires_stable_recovery():
    governor = AdaptiveGovernor(6)
    governor.observe(sample(ram=97, free=.3), now=0)
    assert governor.limit(now=0) == 0
    governor.observe(sample(), now=5)
    governor.observe(sample(ram=94), now=10)  # Recovery was interrupted.
    assert governor.limit(now=10) == 0
    for second in (15, 20):
        governor.observe(sample(), now=second)
        assert governor.limit(now=second) == 0
    governor.observe(sample(), now=25)
    assert governor.limit(now=25) == 1


def test_low_absolute_memory_is_detected_on_large_ram_systems():
    governor = AdaptiveGovernor(6)
    governor.observe(sample(ram=80, free=.4), now=0)
    assert governor.limit(now=0) == 0


def test_missing_or_stale_sensor_uses_small_budget_not_stuck_pause():
    governor = AdaptiveGovernor(15)
    governor.observe(sample(ram=98), now=0)
    assert governor.limit(now=0) == 0
    assert governor.limit(now=25) == 2
    governor.observe(None, now=30)
    assert governor.limit(now=30) == 2
    governor.observe(sample(cpu=math.nan), now=35)
    assert governor.limit(now=35) == 2


def test_manual_mode_preserves_selected_ceiling_even_under_load():
    governor = AdaptiveGovernor(6, enabled=False)
    governor.observe(sample(cpu=100, ram=99), now=0)
    assert governor.limit(now=0) == 6


async def pool_and_governor(tmp_path):
    pool = AccountPool(JsonAccountStore(tmp_path / 'accounts.json'), max_concurrency=2)
    for ident in ('acc_A', 'acc_B', 'acc_C'):
        await pool.upsert(Account(id=ident))
    governor = AdaptiveGovernor(6)
    return pool, governor


async def enter(roles, role):
    cm = roles.lease(role)
    lease = await cm.__aenter__()
    return cm, lease


async def release(entry):
    await entry[0].__aexit__(None, None, None)


async def test_lower_budget_drains_existing_work_without_cancelling_requests(tmp_path):
    pool, governor = await pool_and_governor(tmp_path)
    roles = AccountRoles(pool, lambda: False, 3, 2, governor)
    first, second = await enter(roles, 'video'), await enter(roles, 'video')
    governor.observe(sample(ram=92))
    assert governor.target == 1
    waiter = asyncio.create_task(enter(roles, 'video'))
    try:
        await asyncio.sleep(.02)
        assert not waiter.done()
        assert roles.snapshot()['adaptive']['active_jobs'] == 2
        await release(first)
        await asyncio.sleep(.02)
        assert not waiter.done()
        await release(second)
        admitted = await asyncio.wait_for(waiter, 1)
        await release(admitted)
    finally:
        if not waiter.done():
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
    assert pool.stats()['inflight'] == 0 and not roles.held


async def test_critical_pause_blocks_new_work_and_recovers_without_restart(tmp_path):
    pool, governor = await pool_and_governor(tmp_path)
    roles = AccountRoles(pool, lambda: False, 3, 2, governor)
    governor.observe(sample(ram=97))
    waiter = asyncio.create_task(enter(roles, 'video'))
    await asyncio.sleep(.02)
    assert not waiter.done()
    for _ in range(3):
        governor.observe(sample())
    admitted = await asyncio.wait_for(waiter, 1)
    await release(admitted)
    assert pool.stats()['inflight'] == 0


async def test_prompt_keeps_reserved_slot_during_adaptive_mixed_phase(tmp_path):
    pool, governor = await pool_and_governor(tmp_path)
    governor.observe(sample(ram=92))  # One total slot: finish prompt before video.
    planning = [True]
    roles = AccountRoles(pool, lambda: planning[0], 3, 2, governor)
    roles.prompts_ready()
    video = asyncio.create_task(enter(roles, 'video'))
    await asyncio.sleep(.02)
    assert not video.done()
    prompt = await asyncio.wait_for(enter(roles, 'prompt'), 1)
    await release(prompt)
    planning[0] = False
    admitted = await asyncio.wait_for(video, 1)
    await release(admitted)


async def test_cancelled_waiter_does_not_leak_account_slots(tmp_path):
    pool, governor = await pool_and_governor(tmp_path)
    governor.observe(sample(ram=98))
    roles = AccountRoles(pool, lambda: False, 3, 2, governor)
    waiting = asyncio.create_task(enter(roles, 'video'))
    await asyncio.sleep(.02)
    waiting.cancel()
    await asyncio.gather(waiting, return_exceptions=True)
    assert not roles.held and pool.stats()['inflight'] == 0


@pytest.mark.skipif(os.name != 'nt', reason='Windows load sampler')
async def test_windows_sensor_returns_plausible_values_without_external_processes():
    sensor = WindowsLoad()
    first = sensor.sample()
    await asyncio.sleep(.05)
    second = sensor.sample()
    assert first['cpu'] is None
    assert 0 <= second['cpu'] <= 100
    assert 0 <= second['ram'] <= 100 and second['free_gb'] >= 0
