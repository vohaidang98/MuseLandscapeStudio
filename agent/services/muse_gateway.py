"""Private, browser-backed Muse gateway for the Windows preview."""
import asyncio
import json
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlsplit

import httpx
import uvicorn

from agent.config import BASE_DIR
from agent.services.speech_store import atomic_json, read_json

URL = 'http://127.0.0.1:18610'
ROOT = BASE_DIR / '.flowkit' / 'muse-gateway'
DATA = ROOT / 'data'
COOKIES = {'hatch_sess', 'hatch_gw', 'hatch_vml', 'hatch_native_auth_device'}
REQUIRED_COOKIES = COOKIES - {'hatch_gw'}
_server = None
_task = None
_driver = None
_role_scheduler = None
_services = None
_login = None
_lock = asyncio.Lock()
_login_label = 'FrameWeaver'
_auto_start_state = {'auto_starting': False, 'auto_error': None}


class QuotaExhausted(ValueError):
    def __init__(self):
        super().__init__('Không còn tài khoản Muse khả dụng do hết hạn mức. Đã dừng hàng đợi; thêm tài khoản hoặc chờ hạn mức phục hồi rồi tiếp tục.')


async def _serve(server):
    # Uvicorn exits on failed lifespan startup; isolate that from FrameWeaver.
    try:
        await server.serve()
    except SystemExit:
        return


def api_key():
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / 'api_key'
    if not path.exists():
        try:
            with path.open('x', encoding='utf-8') as stream:
                stream.write(secrets.token_urlsafe(32))
        except FileExistsError:
            pass
    return path.read_text(encoding='utf-8').strip()


def chrome():
    candidates = [Path(os.environ.get(name, '')) / suffix for name, suffix in (
        ('PROGRAMFILES', 'Google/Chrome/Application/chrome.exe'),
        ('PROGRAMFILES(X86)', 'Google/Chrome/Application/chrome.exe'),
        ('LOCALAPPDATA', 'Google/Chrome/Application/chrome.exe'),
    )]
    return next((str(path) for path in candidates if path.is_file()), '')


async def request(method, path, *, body=None, timeout=15, headers=None):
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=timeout) as client:
            response = await client.request(method, URL + path,
                headers={'Authorization': 'Bearer ' + api_key(), **(headers or {})}, json=body)
        if response.is_error:
            try:
                code = response.json().get('error', {}).get('code')
            except (ValueError, AttributeError, TypeError):
                code = None
            if code == 'upstream_quota_exhausted':
                raise QuotaExhausted()
            messages = {401: 'Khóa gateway không khớp. Dừng gateway khác đang dùng cổng 18610.',
                        403: 'Phiên Muse không hợp lệ hoặc tài khoản chưa có quyền sử dụng.',
                        429: 'Muse đang giới hạn yêu cầu hoặc tài khoản đã hết hạn mức.',
                        503: 'Gateway chưa có tài khoản Muse khả dụng.'}
            raise ValueError(messages.get(response.status_code,
                f'Muse trả lỗi HTTP {response.status_code}. Kiểm tra phiên đăng nhập và nhật ký.'))
        return response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise ValueError('Không liên lạc được gateway Muse. Hãy khởi động gateway rồi thử lại.') from exc


def saved_account_rows():
    # Only return explicit public fields. A transient gateway outage must never
    # make saved accounts disappear, or expose credential fragments.
    rows = None
    for name in ('accounts.json', 'accounts.json.bak'):
        try:
            candidate = read_json(DATA / name)
        except (OSError, ValueError):
            continue
        if isinstance(candidate, list):
            rows = candidate
            break
    if rows is None:
        if any((DATA / name).exists() for name in ('accounts.json', 'accounts.json.bak')):
            raise ValueError('Không đọc được dữ liệu tài khoản đã lưu. Giữ dữ liệu để kiểm tra, không thêm lại tài khoản.')
        rows = []
    return [{**{key: row.get(key) for key in ('id', 'label', 'enabled', 'status', 'cooldown_until')},
             'quota_exhausted': row.get('meta', {}).get('quota_exhausted_until', 0) > time.time()}
            for row in rows if isinstance(row, dict)]


async def status():
    result = dict(running=False, ready=False, driver=None, available=0,
                  managed=_task is not None and not _task.done(), chrome_installed=bool(chrome()),
                  login_running=_login is not None, quota_accounts=[], connection_uncertain=False, saved_accounts=0)
    from agent.services.muse_performance import current
    result['performance'] = current()
    result.update(_auto_start_state)
    result['scheduling'] = _role_scheduler.snapshot() if _role_scheduler else {'max_accounts': current()['max_accounts'], 'active_accounts': 0}
    saved = await asyncio.to_thread(saved_account_rows)
    result['saved_accounts'] = len(saved)
    result['quota_accounts'] = [row.get('label') or row['id'] for row in saved if row['quota_exhausted'] and row.get('enabled', True)]
    try:
        if _services and _server and _server.started and _task and not _task.done():
            health = {'driver': await _driver.health(), 'accounts': _services.pool.stats()}
        else:
            health = await request('GET', '/admin/status', timeout=15)
        driver = health.get('driver', {})
        result.update(running=True, driver=driver.get('driver'),
                      available=health.get('accounts', {}).get('available', 0))
        result['ready'] = bool(driver.get('ok') and result['driver'] == 'browser' and result['available'] > 0)
    except ValueError:
        result['connection_uncertain'] = True
    return result


async def auto_start_saved():
    _auto_start_state.update(auto_starting=False, auto_error=None)
    if not (DATA / 'accounts.json').exists():
        return
    try:
        await validate_storage()
        accounts = read_json(DATA / 'accounts.json') or []
        if not any(account.get('enabled', True) and REQUIRED_COOKIES.issubset(account.get('cookies', {}))
                   for account in accounts):
            return
        _auto_start_state['auto_starting'] = True
        state = await start()
        if not state.get('ready'):
            _auto_start_state['auto_error'] = 'Chưa có tài khoản Muse khả dụng. Kiểm tra phiên đăng nhập hoặc hạn mức trong phần Tài khoản Muse.'
    except asyncio.CancelledError:
        await shutdown()
        raise
    except Exception as exc:
        _auto_start_state['auto_error'] = str(exc) if isinstance(exc, ValueError) else 'Không tự kết nối được Muse. Mở Tài khoản Muse để kiểm tra.'
    finally:
        _auto_start_state['auto_starting'] = False


async def start():
    global _server, _task, _driver, _role_scheduler, _services
    async with _lock:
        current = await status()
        if current['running']:
            if current['driver'] != 'browser':
                raise ValueError('Cổng 18610 đang dùng gateway giả lập. Hãy dừng gateway đó; Muse cần driver browser.')
            if current.get('ready'):
                _auto_start_state['auto_error'] = None
                current['auto_error'] = None
            return current
        if not chrome():
            raise ValueError('Chưa tìm thấy Google Chrome. Cài Chrome rồi mở lại FrameWeaver.')
        await validate_storage()
        # Refuse an occupied port, even if it belongs to an unrelated service.
        import socket
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', 18610)) == 0:
                raise ValueError('Cổng 18610 đang được ứng dụng khác sử dụng hoặc khóa gateway không khớp.')
        from muse2api.app import create_app
        from muse2api.config import Settings
        from muse2api.drivers.browser.driver import BrowserDriver
        from agent.services.muse_performance import current
        performance = current()
        settings = Settings(_env_file=None, host='127.0.0.1', port=18610,
            driver='browser', chromium_path=chrome(), headless=True,
            data_dir=DATA, browser_profile_dir=ROOT / 'chrome-profile',
            api_key=api_key(), admin_key=api_key(), cdp_port=19210,
            billing_enabled=False, keepalive_enabled=False, max_failover=0,
            account_max_concurrency=performance['videos_per_account'], pool_strategy='round_robin',
            public_base=URL)
        from agent.services.muse_idle_browser import IdleBrowserMixin
        class ManagedBrowserDriver(IdleBrowserMixin, BrowserDriver):
            def __init__(self, settings):
                super().__init__(settings)
                self.muse_gateway_ready = False
                from agent.services.muse_pacing import AccountPacer
                self.pacer = AccountPacer()
                from agent.services.muse_adaptive import AdaptiveGovernor
                self.governor = AdaptiveGovernor(performance['max_videos'], performance['automatic'])

            async def _send(self, tab, prompt):
                parent = super()._send
                async def send_if_available():
                    from muse2api.errors import UpstreamQuotaError
                    if account_quota_blocked(tab.account_id):
                        raise UpstreamQuotaError('account quota exhausted; queued send skipped')
                    return await parent(tab, prompt)
                return await self.pacer.send(tab.account_id, send_if_available)

            async def _state(self, tab):
                from agent.services.muse_roles import _role
                if _role.get() == 'video':
                    # Video generation is remote. Scanning every browser tab's
                    # DOM at 0.6s intervals wastes local CPU while it renders.
                    elapsed = time.monotonic() - getattr(tab, 'muse_state_at', 0)
                    if elapsed < 5:
                        await asyncio.sleep(5 - elapsed)
                    tab.muse_state_at = time.monotonic()
                return await super()._state(tab)

            async def startup(self):
                if self._browser is None or self._browser.closed:
                    await super().startup()
                self.governor.start()

            async def shutdown(self):
                await self.governor.stop()
                await super().shutdown()
        _driver = ManagedBrowserDriver(settings)
        try:
            await _driver.startup()
        except Exception as exc:
            await _driver.shutdown()
            _driver = None
            raise ValueError('Chrome chưa khởi động được cho Muse. Đóng gateway cũ và chạy FrameWeaver trực tiếp trên Windows rồi thử lại.') from exc
        gateway_app = create_app(settings, driver=_driver)
        from agent.services import muse_scenes
        from agent.services.muse_roles import AccountRoles, RoleGateway
        services = gateway_app.state.services
        _services = services
        _role_scheduler = AccountRoles(services.pool, lambda: bool(muse_scenes._planning), performance['max_accounts'], performance['videos_per_account'], _driver.governor)
        _driver.muse_pool = services.pool
        _driver.muse_roles = _role_scheduler
        services.gateway = RoleGateway(services.pool, _driver, _role_scheduler, max_failover=0)
        _server = uvicorn.Server(uvicorn.Config(gateway_app, host='127.0.0.1', port=18610, log_config=None, access_log=False))
        _task = asyncio.create_task(_serve(_server))
        # Loading retained task history can exceed 40 seconds on a busy disk.
        # Do not start token tabs until the local server is actually ready.
        for _ in range(1200):
            if _server.started:
                _driver.muse_gateway_ready = True
                _auto_start_state['auto_error'] = None
                return await status()
            if _task.done():
                break
            await asyncio.sleep(.1)
        await _shutdown_owned()
        raise ValueError('Gateway Muse không khởi động được sau khi Chrome đã chạy. Kiểm tra dữ liệu và nhật ký app.log.')


async def validate_storage():
    from muse2api.core.json_storage import load_json
    from muse2api.accounts.model import Account
    from muse2api.services.tasks import Task
    for name, model, label in (('accounts.json', Account, 'tài khoản'), ('tasks.json', Task, 'tác vụ')):
        file = DATA / name
        if not file.exists():
            continue
        try:
            rows = await asyncio.to_thread(load_json, file)
            if not isinstance(rows, list):
                raise ValueError('Expected a list')
            for row in rows:
                model.model_validate(row)
        except (ValueError, TypeError, OSError) as exc:
            raise ValueError(f'Dữ liệu {label} Muse ({name}) không đọc được và chưa có bản dự phòng hợp lệ. Giữ nguyên thư mục Data để khôi phục; đây không phải lỗi Chrome.') from exc


async def _shutdown_owned():
    global _server, _task, _driver, _role_scheduler, _services
    _role_scheduler = None
    _services = None
    if _server:
        _server.should_exit = True
    if _task:
        try:
            await asyncio.wait_for(asyncio.shield(_task), 12)
        except (Exception, asyncio.CancelledError):
            if not _task.done():
                _task.cancel()
                await asyncio.gather(_task, return_exceptions=True)
    if _driver:
        try:
            await _driver.shutdown()
        except Exception:
            pass
    _server = _task = _driver = None


async def shutdown():
    global _login
    async with _lock:
        await _shutdown_owned()
        if _login:
            await _login.stop()
            _login = None


async def start_login(label='FrameWeaver'):
    global _login, _login_label
    label = label.strip()
    if not label or len(label) > 80:
        raise ValueError('Nhập tên tài khoản từ 1 đến 80 ký tự.')
    if not chrome():
        raise ValueError('Cài Google Chrome trước khi đăng nhập Muse.')
    if not (await status())['running']:
        await start()
    if _login:
        if label != _login_label:
            raise ValueError('Hoàn tất cửa sổ đăng nhập hiện tại trước khi thêm tài khoản khác.')
        return {'opened': True}
    import socket
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', 19211)) == 0:
            raise ValueError('Cổng đăng nhập 19211 đang được sử dụng. Đóng cửa sổ đăng nhập cũ rồi thử lại.')
    from muse2api.drivers.browser.chromium import ChromiumProcess
    from muse2api.drivers.browser.cdp import CDPSession
    import hashlib
    profile = 'login-profile' if label == 'FrameWeaver' else 'login-' + hashlib.sha256(label.encode()).hexdigest()[:20]
    _login_label = label
    _login = ChromiumProcess(chrome(), 19211, ROOT / profile, headless=False)
    try:
        browser = await CDPSession.connect(await _login.start())
        try:
            await browser.send('Target.createTarget', {'url': 'https://muse.ai'})
        finally:
            await browser.close()
    except Exception as exc:
        await _login.stop()
        _login = None
        raise ValueError('Chưa mở được Chrome đăng nhập Muse. Thử lại hoặc dùng phần nhập phiên thủ công.') from exc
    return {'opened': True}


async def finish_login():
    global _login
    if not _login:
        raise ValueError('Bấm Mở Chrome đăng nhập trước, rồi đăng nhập Muse trong cửa sổ đó.')
    from muse2api.drivers.browser.cdp import CDPSession
    url = await _login.browser_ws_url()
    if not url:
        raise ValueError('Cửa sổ đăng nhập đã đóng. Mở lại Chrome đăng nhập để tiếp tục.')
    browser = await CDPSession.connect(url)
    try:
        # Session GET refreshes routing cookies. A visible connected page can have
        # only hatch_sess/device until this endpoint has been requested again.
        targets = (await browser.send('Target.getTargets')).get('targetInfos', [])
        target = next((t for t in targets if t.get('type') == 'page' and
            urlsplit(t.get('url', '')).hostname == 'muse.ai'), None)
        if not target:
            raise ValueError('Mở muse.ai trong cửa sổ đăng nhập của ứng dụng rồi thử lại.')
        page = await CDPSession.connect(f"ws://127.0.0.1:19211/devtools/page/{target['targetId']}")
        try:
            session = await page.evaluate("""(async()=>{
                const response=await fetch('/api/session',{credentials:'include'});
                let body={}; try { body=await response.json(); } catch {}
                return {http:response.status,status:body.status};
            })()""", await_promise=True)
        finally:
            await page.close()
        if not session or session.get('http') != 200 or session.get('status') != 'assigned':
            raise ValueError('Muse chưa xác nhận phiên đăng nhập. Hoàn tất đăng nhập và đợi trạng thái Connected rồi thử lại.')
        values = (await browser.send('Storage.getCookies')).get('cookies', [])
        cookies = {item['name']: item['value'] for item in values
            if item.get('name') in COOKIES and
            (item.get('domain', '').lstrip('.') == 'muse.ai' or item.get('domain', '').endswith('.muse.ai'))}
    finally:
        await browser.close()
    if not REQUIRED_COOKIES.issubset(cookies):
        missing = ', '.join(sorted(REQUIRED_COOKIES - cookies.keys()))
        raise ValueError('Muse đã nhận đăng nhập nhưng thiếu thành phần phiên: ' + missing + '. Tải lại trang Muse rồi thử lại.')
    result = await save_session(cookies, verified=True, label=_login_label)
    await _login.stop()
    _login = None
    return result


def account_quota_blocked(ident):
    return any(row.get('id') == ident and row.get('meta', {}).get('quota_exhausted_until', 0) > time.time()
               for row in (read_json(DATA / 'accounts.json') or []))


async def require_ready():
    state = await status()
    if not state['ready']:
        if state.get('running') and state.get('quota_accounts') and not state.get('available'):
            raise QuotaExhausted()
        raise ValueError('Muse chưa sẵn sàng. Khởi động gateway và kết nối phiên đăng nhập Muse rồi thử lại.')


async def validate_session(cookies):
    from muse2api.upstream.muse import renew_session
    try:
        session = await renew_session(cookies, wake_vm=False)
    except Exception as exc:
        raise ValueError('Muse chưa xác nhận được phiên. Dùng Mở Chrome đăng nhập rồi kết nối lại.') from exc
    if not session.ok:
        raise ValueError('Phiên chưa được Muse xác nhận hoạt động. Hãy đăng nhập lại.')
    return {key: value for key, value in session.cookies.items() if key in COOKIES and value}


async def save_session(cookies, verified=False, label='FrameWeaver'):
    label = label.strip()
    if not label or len(label) > 80:
        raise ValueError('Nhập tên tài khoản từ 1 đến 80 ký tự.')
    cookies = {key: value.strip() for key, value in cookies.items() if key in COOKIES and value.strip()}
    if not REQUIRED_COOKIES.issubset(cookies):
        raise ValueError('Cần hatch_sess, hatch_vml và hatch_native_auth_device. hatch_gw chỉ nhập nếu Muse có cấp.')
    if not verified:
        cookies = await validate_session(cookies)
    state = await status()
    if not state['running'] or state['driver'] != 'browser':
        raise ValueError('Khởi động gateway thật trước khi lưu phiên Muse.')
    accounts = (await request('GET', '/admin/accounts')).get('data', [])
    account = next((item for item in accounts if item.get('label') == label), None)
    # Compare raw local storage only; masked admin values cannot identify a session.
    stored = read_json(DATA / 'accounts.json') or []
    if any(row.get('label') != label and row.get('cookies', {}).get('hatch_sess') == cookies.get('hatch_sess') for row in stored):
        raise ValueError('Phiên này đã lưu dưới một tên khác. Hãy đăng nhập tài khoản Muse khác.')
    body = {'label': label, 'cookies': {key: value.strip() for key, value in cookies.items()}, 'enabled': True}
    if account:
        await request('PATCH', '/admin/accounts/' + account['id'], body=body)
    else:
        await request('POST', '/admin/accounts', body=body)
    # Availability is not proof of an authenticated or entitled upstream session.
    return {'saved': True, 'message': 'Đã lưu phiên trên máy. Gửi một câu thử để xác nhận Muse thật.'}


async def accounts():
    from agent.services import muse_tokens
    rows = await asyncio.to_thread(saved_account_rows)
    tokens = await asyncio.to_thread(muse_tokens.cache)
    state = muse_tokens.status()
    roles = _role_scheduler.snapshot()['roles'] if _role_scheduler else {}
    return [{**row, 'additional_tokens': tokens.get(row['id']),
             'work_role': roles.get(row['id'], 'standby'),
             'token_loading': state['running'] and state['account_id'] == row['id']} for row in rows]


def prepare_plan_roles():
    if _role_scheduler:
        from agent.services import muse_queue
        queued = muse_queue.status()
        _role_scheduler.prepare_plan(any(row.get('count', 0) > row.get('videos', 0) for row in queued['items']))


def prompts_ready():
    if _role_scheduler:
        _role_scheduler.prompts_ready()


async def delete_account(ident):
    if not re.fullmatch(r'acc_[A-Za-z0-9]+', ident):
        raise ValueError('Mã tài khoản không hợp lệ.')
    # Use the live pool so later persistence cannot restore stale account data.
    await start()
    await request('PATCH', '/admin/accounts/' + ident, body={'enabled': False})
    await request('DELETE', '/admin/accounts/' + ident)
    return await accounts()


async def enable_account(ident, enabled):
    if not re.fullmatch(r'acc_[A-Za-z0-9]+', ident):
        raise ValueError('Mã tài khoản không hợp lệ.')
    await request('PATCH', '/admin/accounts/' + ident, body={'enabled': enabled})
    return await accounts()


async def chat_quota_error():
    if (await status()).get('available', 0) > 0:
        raise ValueError('Một tài khoản hết hạn mức. Phần prompt đã nhận được giữ; lô lỗi sẽ thử lại bằng tài khoản còn khả dụng.')
    raise QuotaExhausted()


async def chat(prompt, on_text=None):
    await require_ready()
    if on_text:
        text = ''
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=330) as client:
                async with client.stream('POST', URL + '/v1/chat/completions',
                    headers={'Authorization': 'Bearer ' + api_key()},
                    json={'model': 'muse-chat', 'messages': [{'role': 'user', 'content': prompt}], 'stream': True}) as response:
                    if response.is_error:
                        body = json.loads(await response.aread())
                        if body.get('error', {}).get('code') == 'upstream_quota_exhausted':
                            await chat_quota_error()
                        raise ValueError('Không nhận được phản hồi Muse. Prompt đã hoàn thành vẫn được giữ.')
                    async for line in response.aiter_lines():
                        if not line.startswith('data:'):
                            continue
                        data = line[5:].strip()
                        if data == '[DONE]':
                            break
                        event = json.loads(data)
                        if event.get('error'):
                            if event['error'].get('code') == 'upstream_quota_exhausted':
                                await chat_quota_error()
                            raise ValueError('Muse ngắt phản hồi. Prompt đã hoàn thành vẫn được giữ.')
                        for choice in event.get('choices', []):
                            delta = choice.get('delta', {}).get('content') or ''
                            text += delta
                            if delta:
                                await on_text(text)
            return {'text': text}
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise ValueError('Mất kết nối khi lập prompt. Phần đã hoàn thành được giữ lại.') from exc
    result = await request('POST', '/v1/chat/completions', timeout=330,
        body={'model': 'muse-chat', 'messages': [{'role': 'user', 'content': prompt}], 'stream': False})
    return {'text': result['choices'][0]['message']['content']}


def history():
    return read_json(ROOT / 'history.json') or []


async def generate(kind, prompt, size, references, request_id=None):
    await require_ready()
    body = {'model': 'muse-image' if kind == 'image' else 'muse-video', 'prompt': prompt, 'size': size}
    if references:
        body['image'] = references if kind == 'image' else references[0]
    if kind == 'image':
        body.update({'async': True, 'n': 1})
    else:
        body['duration'] = 8
    result = await request('POST', '/v1/images/generations' if kind == 'image' else '/v1/videos', body=body, timeout=90,
                           headers={'Idempotency-Key': request_id} if request_id and kind == 'video' else None)
    ident = result['id']
    if not re.fullmatch(r'task_[A-Za-z0-9_-]+', ident):
        raise ValueError('Gateway trả mã tác vụ không hợp lệ.')
    rows = history()
    rows.insert(0, {'id': ident, 'kind': kind, 'prompt': prompt, 'created_at': time.time()})
    atomic_json(ROOT / 'history.json', rows)
    return result


_task_index_stamp = None
_task_index = {}


def stored_task_index():
    global _task_index_stamp, _task_index
    file = DATA / 'tasks.json'
    if not file.exists():
        return {}
    stat = file.stat()
    stamp = (str(file), stat.st_mtime_ns, stat.st_size)
    if stamp != _task_index_stamp:
        rows = read_json(file) or []
        _task_index = {row['id']: row for row in rows}
        _task_index_stamp = stamp
    return _task_index


def find_submitted_video(prompt, claimed=()):
    matches = [row for row in stored_task_index().values()
               if row.get('kind') == 'video' and row.get('request', {}).get('prompt') == prompt
               and row.get('id') not in claimed]
    if len(matches) == 1:
        return matches[0]['id']
    return None


async def task(ident):
    row = next((row for row in history() if row['id'] == ident), None)
    if not row:
        stored = stored_task_index().get(ident)
        if stored and stored.get('kind') in {'video', 'image'}:
            row = {'kind': stored['kind']}
        else:
            raise ValueError('Không tìm thấy mã tác vụ trong dữ liệu gateway. Giữ cảnh để đối chiếu, không tự tạo trùng.')
    path = '/v1/images/generations/' if row['kind'] == 'image' else '/v1/videos/'
    result = await request('GET', path + ident)
    payload = result.get('result') or {}
    urls = [entry.get('url') for entry in payload.get('data', [])]
    if payload.get('url'):
        urls.append(payload['url'])
    media = []
    for value in urls:
        if not value:
            continue
        parsed = urlsplit(value)
        if parsed.scheme == 'http' and parsed.netloc == '127.0.0.1:18610' and parsed.path.startswith('/v1/media/'):
            name = parsed.path.removeprefix('/v1/media/')
            if re.fullmatch(r'[A-Za-z0-9_-]+\.(png|jpg|jpeg|webp|gif|mp4|webm|mov)', name):
                media.append(name)
    error_code = result.get('error', {}).get('code') if isinstance(result.get('error'), dict) else None
    if error_code == 'upstream_quota_exhausted' and (await status()).get('available', 0) > 0:
        error_code = 'upstream_account_quota'
    return {'id': ident, 'status': result['status'], 'progress': result.get('progress', 0), 'media': media,
            'error_code': error_code,
            'error': 'Muse chưa hoàn thành yêu cầu. Kiểm tra phiên, quyền tạo media và hạn mức.' if result.get('error') else None}
