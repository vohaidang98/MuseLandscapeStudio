import asyncio
import time

import pytest
from muse2api.accounts.model import Account
from muse2api.accounts.pool import AccountPool
from muse2api.accounts.store import JsonAccountStore
from muse2api.errors import UpstreamQuotaError
from agent.services.muse_roles import AccountRoles


async def setup_roles(tmp_path, planning=True, count=10):
    pool = AccountPool(JsonAccountStore(tmp_path / 'accounts.json'), max_concurrency=3)
    for n in range(count):
        await pool.upsert(Account(id=f'acc_{n}', label=str(n)))
    state = [planning]
    return pool, AccountRoles(pool, lambda: state[0]), state


async def enter(roles, role):
    cm = roles.lease(role)
    lease = await cm.__aenter__()
    return cm, lease


async def close(entries):
    for cm, _ in entries:
        await cm.__aexit__(None, None, None)


async def test_warmup_uses_five_distinct_accounts_and_sixth_waits(tmp_path):
    pool, roles, _ = await setup_roles(tmp_path)
    entries = [await enter(roles, 'prompt') for _ in range(5)]
    assert len({lease.account.id for _, lease in entries}) == 5
    pending = asyncio.create_task(enter(roles, 'prompt'))
    await asyncio.sleep(.02)
    assert not pending.done() and roles.snapshot()['active_accounts'] == 5
    await close(entries[:1])
    sixth = await asyncio.wait_for(pending, 1)
    await close(entries[1:] + [sixth])
    assert roles.snapshot()['active_accounts'] == 0 and pool.stats()['inflight'] == 0


async def test_mixed_keeps_one_prompt_and_four_disjoint_video_accounts(tmp_path):
    _, roles, _ = await setup_roles(tmp_path)
    roles.prompts_ready()
    prompt = await enter(roles, 'prompt')
    videos = [await enter(roles, 'video') for _ in range(12)]
    video_ids = {lease.account.id for _, lease in videos}
    assert len(video_ids) == 4 and prompt[1].account.id not in video_ids
    assert roles.snapshot()['active_accounts'] == 5
    pending = asyncio.create_task(enter(roles, 'video'))
    await asyncio.sleep(.02)
    assert not pending.done()
    pending.cancel()
    await asyncio.gather(pending, return_exceptions=True)
    await close(videos + [prompt])
    assert not roles.held


async def test_transition_drains_old_prompt_accounts_before_video(tmp_path):
    _, roles, _ = await setup_roles(tmp_path)
    prompts = [await enter(roles, 'prompt') for _ in range(5)]
    roles.prompts_ready()
    pending = asyncio.create_task(enter(roles, 'video'))
    await asyncio.sleep(.02)
    assert not pending.done()
    await close(prompts[1:2])
    video = await asyncio.wait_for(pending, 1)
    assert video[1].account.id not in {lease.account.id for _, lease in prompts[:1] + prompts[2:]}
    assert roles.snapshot()['active_accounts'] == 5
    await close(prompts[:1] + prompts[2:] + [video])


async def test_quota_replaces_account_with_spare_without_exceeding_five(tmp_path):
    _, roles, _ = await setup_roles(tmp_path, planning=False)
    videos = [await enter(roles, 'video') for _ in range(5)]
    failed_id = videos[0][1].account.id
    videos[0][1].fail(UpstreamQuotaError('video limit'))
    await close(videos[:1])
    replacement = await enter(roles, 'video')
    assert replacement[1].account.id not in {lease.account.id for _, lease in videos}
    assert replacement[1].account.id != failed_id
    assert roles.snapshot()['active_accounts'] == 5
    await close(videos[1:] + [replacement])


async def test_new_planner_drains_one_of_five_video_accounts_without_deadlock(tmp_path):
    _, roles, state = await setup_roles(tmp_path, planning=False)
    videos = [await enter(roles, 'video') for _ in range(5)]
    state[0] = True
    roles.prepare_plan(True)
    pending = asyncio.create_task(enter(roles, 'prompt'))
    await asyncio.sleep(.02)
    assert not pending.done()
    victim = roles.prompt_id
    drained = [entry for entry in videos if entry[1].account.id == victim]
    await close(drained)
    prompt = await asyncio.wait_for(pending, 1)
    assert prompt[1].account.id == victim
    assert roles.snapshot()['video_accounts'] == 4
    await close([entry for entry in videos if entry not in drained] + [prompt])


async def test_single_account_finishes_prompt_before_video(tmp_path):
    _, roles, state = await setup_roles(tmp_path, count=1)
    prompt = await enter(roles, 'prompt')
    pending = asyncio.create_task(enter(roles, 'video'))
    await asyncio.sleep(.02)
    assert not pending.done()
    await close([prompt])
    assert not pending.done()
    state[0] = False
    video = await asyncio.wait_for(pending, 1)
    await close([video])


async def test_all_quota_is_reported_instead_of_waiting_forever(tmp_path):
    pool, roles, _ = await setup_roles(tmp_path)
    for account in pool.all():
        account.status = 'cooling'
        account.cooldown_until = time.time() + 3600
        account.meta['quota_exhausted_until'] = account.cooldown_until
    with pytest.raises(UpstreamQuotaError):
        await enter(roles, 'prompt')


async def test_finished_planner_joins_as_fifth_video_account(tmp_path):
    _, roles, state = await setup_roles(tmp_path)
    roles.prompts_ready()
    prompt = await enter(roles, 'prompt')
    videos = [await enter(roles, 'video') for _ in range(12)]
    former_prompt_id = prompt[1].account.id
    pending = asyncio.create_task(enter(roles, 'video'))
    await asyncio.sleep(.02)
    assert not pending.done()
    await close([prompt])
    state[0] = False
    fifth = await asyncio.wait_for(pending, 1)
    assert fifth[1].account.id == former_prompt_id
    assert roles.snapshot()['video_accounts'] == 5
    await close(videos + [fifth])


async def test_role_gateway_routes_chat_and_media_to_disjoint_roles(tmp_path):
    from types import SimpleNamespace
    from muse2api.drivers.base import ChatRequest
    from agent.services.muse_roles import RoleGateway
    pool, roles, _ = await setup_roles(tmp_path)
    async def chat(account, request):
        assert roles.held[account.id]['role'] == 'prompt'
        yield 'json'
    service = RoleGateway(pool, SimpleNamespace(chat_stream=chat), roles, max_failover=0)
    assert [x async for x in service.chat_stream(ChatRequest(prompt='scenes', model='muse-chat'))] == ['json']
    async def video(account):
        assert roles.held[account.id]['role'] == 'video'
        return 'file'
    assert await service._run(video) == 'file'
    assert not roles.held


async def test_video_reuses_same_account_when_slot_frees(tmp_path):
    _, roles, _ = await setup_roles(tmp_path, planning=False)
    entries = [await enter(roles, 'video') for _ in range(15)]
    original_ids = {lease.account.id for _, lease in entries}
    target = entries[0][1].account.id
    group = [entry for entry in entries if entry[1].account.id == target]
    pending = asyncio.create_task(enter(roles, 'video'))
    await close(group[:1])
    await asyncio.sleep(.02)
    replacement = await asyncio.wait_for(pending, 1)
    assert replacement[1].account.id == target
    await close(group[1:])
    assert roles.snapshot()['active_accounts'] == 5
    await close([entry for entry in entries if entry not in group] + [replacement])


async def test_prompt_batches_keep_same_account_until_unavailable(tmp_path):
    _, roles, _ = await setup_roles(tmp_path)
    roles.prompts_ready()
    first = await enter(roles, 'prompt')
    first_id = first[1].account.id
    await close([first])
    second = await enter(roles, 'prompt')
    assert second[1].account.id == first_id
    assert roles.snapshot()['prompt_accounts'] == 1
    await close([second])


async def test_rotation_reuses_available_account_when_no_spare_exists(tmp_path):
    _, roles, _ = await setup_roles(tmp_path, planning=False, count=1)
    first = await enter(roles, 'video')
    first_id = first[1].account.id
    await close([first])
    second = await asyncio.wait_for(enter(roles, 'video'), 1)
    assert second[1].account.id == first_id
    await close([second])
