import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agent.services.muse_idle_browser import IdleBrowserMixin


def setup_driver(selected=('A',), available=True):
    class Driver(IdleBrowserMixin):
        pass
    driver = Driver()
    driver._tab_cond = asyncio.Condition()
    driver._opening = {}
    driver._tabs = {}
    account = SimpleNamespace(is_available=lambda: available)
    driver.muse_pool = SimpleNamespace(get=lambda ident: account)
    driver.muse_roles = SimpleNamespace(selected=list(selected))
    driver._close_tab = AsyncMock()
    return driver


def tab(busy=False, since=100):
    return SimpleNamespace(busy=busy, closed=False, muse_idle_since=since)


async def test_busy_tabs_survive_even_when_account_is_out_of_quota():
    driver = setup_driver(available=False)
    busy, idle = tab(True), tab()
    driver._tabs = {'A': [busy, idle]}
    assert await driver.close_idle_tabs(now=110) == 1
    driver._close_tab.assert_awaited_once_with(idle)
    assert busy.busy


async def test_quota_tabs_wait_for_token_snapshot_then_close():
    driver = setup_driver(available=False)
    idle = tab()
    driver._tabs = {'A': [idle]}
    driver.muse_token_pending = {'A'}
    assert await driver.close_idle_tabs(now=200) == 0
    driver.muse_token_pending.clear()
    assert await driver.close_idle_tabs(now=201) == 1
    driver._close_tab.assert_awaited_once_with(idle)


async def test_selected_idle_tab_has_grace_then_closes():
    driver = setup_driver()
    idle = tab()
    driver._tabs = {'A': [idle]}
    assert await driver.close_idle_tabs(now=129) == 0
    assert await driver.close_idle_tabs(now=130) == 1
    driver._close_tab.assert_awaited_once_with(idle)


async def test_standby_account_closes_without_waiting_thirty_seconds():
    driver = setup_driver(selected=('B',))
    idle = tab()
    driver._tabs = {'A': [idle]}
    assert await driver.close_idle_tabs(now=101) == 1


async def test_opening_new_tab_defers_disposing_account_context():
    driver = setup_driver(selected=())
    driver._opening['A'] = 1
    driver._tabs = {'A': [tab()]}
    assert await driver.close_idle_tabs(now=200) == 0


async def test_cleanup_reserves_tab_before_checkout_can_reuse_it():
    driver = setup_driver()
    idle = tab()
    driver._tabs = {'A': [idle]}
    async def close(target):
        assert target.busy
    driver._close_tab.side_effect = close
    assert await driver.close_idle_tabs(now=200) == 1


async def test_failed_close_marks_tab_stale_instead_of_leaving_slot_busy():
    driver = setup_driver()
    idle = tab()
    driver._tabs = {'A': [idle]}
    driver._close_tab.side_effect = RuntimeError('connection closed')
    await driver.close_idle_tabs(now=200)
    assert idle.stale and not idle.busy
