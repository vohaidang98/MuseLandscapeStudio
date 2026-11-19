"""Read the Additional tokens label from an isolated Muse settings tab."""
import asyncio
import contextlib
import re
import time

from agent.services import muse_gateway as gateway
from agent.services.speech_store import atomic_json, read_json

_task = None
_refresh_lock = asyncio.Lock()
_state = {'running': False, 'completed': 0, 'total': 0, 'account_id': None}


def cache():
    return read_json(gateway.ROOT / 'additional-tokens.json') or {}


def parse_tokens(text):
    section = re.search(r'Additional\s+tokens\b([\s\S]{0,350})', text, re.I)
    if not section:
        raise ValueError('Chưa đọc được mục Token bổ sung trên Muse.')
    match = re.search(r'([\d.,]+\s*[KMBT]?)\s+tokens?\s+left', section[1], re.I)
    if not match:
        raise ValueError('Muse chưa hiển thị số token bổ sung còn lại.')
    # Preserve Muse's displayed unit; do not infer zero from a missing label.
    return {'remaining_label': re.sub(r'\s+', '', match[1]).upper()}


async def read_account(driver, account):
    tab = await driver._checkout(account)
    try:
        await tab.session.send('Page.navigate', {'url': 'https://muse.ai/thread/new'})
        deadline = time.monotonic() + 45
        opened = False
        while time.monotonic() < deadline:
            opened = await tab.session.evaluate("""(()=>{
                const b=document.querySelector('button[aria-label="Settings"]');
                if(!b||!Object.keys(b).some(k=>k.startsWith('__reactProps')))return false;
                b.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true,button:0,buttons:1,pointerType:'mouse',isPrimary:true}));
                return true;
            })()""")
            if opened:
                break
            await asyncio.sleep(.5)
        if not opened:
            raise ValueError('Không mở được Usage; có thể cần đăng nhập lại tài khoản.')
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            await tab.session.evaluate("""(()=>{
                const b=[...document.querySelectorAll('[role=menuitem]')].find(x=>x.innerText.trim().startsWith('Settings'));
                if(b)b.click();
            })()""")
            text = await tab.session.evaluate('document.body.innerText') or ''
            if re.search(r'Additional\s+tokens\b', text, re.I):
                try:
                    return parse_tokens(text)
                except ValueError:
                    pass  # The usage widget can appear before its data arrives.
            else:
                await tab.session.evaluate("""(()=>{
                    const b=[...document.querySelectorAll('[role=tab]')].find(x=>x.innerText.trim()==='General');
                    if(b)b.click();
                })()""")
            await asyncio.sleep(.5)
        raise ValueError('Chưa đọc được token bổ sung; thử cập nhật lại sau.')
    finally:
        with contextlib.suppress(Exception):
            await driver._close_tab(tab)


def status():
    return dict(_state)


async def refresh(ident=None):
    async with _refresh_lock:
        return await _begin_refresh(ident)


async def _begin_refresh(ident=None):
    global _task
    from agent.services import muse_scenes
    if muse_scenes._workers or muse_scenes._planning:
        raise ValueError('Tạm ngừng kiểm tra token khi đang tạo video hoặc viết prompt để giảm tải máy.')
    if _task and not _task.done():
        return status()
    rows = read_json(gateway.DATA / 'accounts.json') or []
    if ident:
        if not re.fullmatch(r'acc_[A-Za-z0-9]+', ident):
            raise ValueError('Mã tài khoản không hợp lệ.')
        rows = [row for row in rows if row.get('id') == ident]
    else:
        previous = cache()
        rows = [row for row in rows if row.get('meta', {}).get('quota_exhausted_until', 0) > time.time()
                and row.get('meta', {}).get('quota_exhausted_until', 0) > previous.get(row['id'], {}).get('quota_observed_until', 0)]
    if not rows:
        return status()
    await gateway.start()
    driver = gateway._driver
    if driver is None:
        raise ValueError('Cần dùng gateway của ứng dụng để đọc token từng tài khoản.')
    return _launch_refresh(rows, driver)


def _launch_refresh(rows, driver):
    global _task
    _state.update(running=True, completed=0, total=len(rows), account_id=None)

    pending = {row['id'] for row in rows}
    driver_pending = getattr(driver, 'muse_token_pending', None)
    if driver_pending is not None:
        driver_pending.update(pending)

    async def run():
        from muse2api.accounts.model import Account
        try:
            for row in rows:
                ident = row['id']
                _state['account_id'] = ident
                values = cache()
                previous = values.get(ident, {})
                try:
                    value = await asyncio.wait_for(read_account(driver, Account.model_validate(row)), timeout=80)
                    values[ident] = {**value, 'checked_at': time.time(), 'error': None}
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    values[ident] = {**previous, 'error': str(exc) if isinstance(exc, ValueError) else 'Chưa đọc được token; kiểm tra kết nối hoặc đăng nhập lại.',
                                     'attempted_at': time.time()}
                values[ident]['quota_observed_until'] = row.get('meta', {}).get('quota_exhausted_until', 0)
                atomic_json(gateway.ROOT / 'additional-tokens.json', values)
                _state['completed'] += 1
        finally:
            if driver_pending is not None:
                driver_pending.difference_update(pending)
            _state.update(running=False, account_id=None)
    _task = asyncio.create_task(run())
    return status()


async def refresh_quota_idle(driver):
    """Read once after a quota account drains; other accounts may keep working."""
    if not getattr(driver, 'muse_gateway_ready', True):
        return
    async with _refresh_lock:
        if _task and not _task.done():
            return
        pool = getattr(driver, 'muse_pool', None)
        if pool is None:
            return
        previous = cache()
        for account in pool.all():
            until = account.meta.get('quota_exhausted_until', 0)
            if until <= time.time() or until <= previous.get(account.id, {}).get('quota_observed_until', 0):
                continue
            if pool._inflight.get(account.id, 0) or driver._opening.get(account.id, 0):
                continue
            if any(tab.busy for tab in driver._tabs.get(account.id, []) if not tab.closed):
                continue
            # One lightweight check at a time; never send a generation prompt.
            if not hasattr(driver, 'muse_token_pending'):
                driver.muse_token_pending = set()
            _launch_refresh([account.model_dump(mode='json')], driver)
            return


async def shutdown():
    if _task and not _task.done():
        _task.cancel()
        await asyncio.gather(_task, return_exceptions=True)
