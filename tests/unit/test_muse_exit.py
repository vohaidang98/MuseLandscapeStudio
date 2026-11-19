import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.services import muse_browser_cleanup as cleanup


@pytest.mark.parametrize('profile,port', [('chrome-profile', '19210'), ('login-profile', '19211'), ('login-' + 'a' * 20, '19211')])
def test_only_private_muse_profiles_qualify(tmp_path, profile, port):
    root = tmp_path / 'muse-gateway'
    assert cleanup.owns_browser(['chrome.exe', '--user-data-dir=' + str(root / profile), '--remote-debugging-port=' + port], root)


@pytest.mark.parametrize('profile,port', [('Default', '19210'), ('chrome-profile', '9222'), ('login-other', '19211')])
def test_ordinary_chrome_and_unknown_profiles_are_not_owned(tmp_path, profile, port):
    root = tmp_path / 'muse-gateway'
    assert not cleanup.owns_browser(['chrome.exe', '--user-data-dir=' + str(root / profile), '--remote-debugging-port=' + port], root)
    assert not cleanup.owns_browser(['chrome.exe', '--user-data-dir=' + str(tmp_path / 'other' / 'chrome-profile'), '--remote-debugging-port=19210'], root)


def test_windows_command_line_parser_preserves_profile_spaces(tmp_path):
    root = tmp_path / 'Muse Data' / 'muse-gateway'
    args = cleanup.command_args(f'"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" "--user-data-dir={root / "chrome-profile"}" --remote-debugging-port=19210')
    assert cleanup.owns_browser(args, root)


def test_cleanup_never_terminates_normal_chrome(tmp_path, monkeypatch):
    root = tmp_path / 'muse-gateway'
    rows = [
        {'ProcessId': 111, 'CommandLine': f'chrome.exe "--user-data-dir={root / "chrome-profile"}" --remote-debugging-port=19210'},
        {'ProcessId': 222, 'CommandLine': 'chrome.exe --profile-directory=Default'},
        {'ProcessId': 333, 'CommandLine': f'chrome.exe "--user-data-dir={root / "chrome-profile"}" --remote-debugging-port=9222'},
    ]
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=json.dumps(rows) if args[0] == 'powershell.exe' else '')
    monkeypatch.setattr(cleanup.subprocess, 'run', run)
    assert cleanup.close_owned_chrome(root) == [111]
    assert calls[1:] == [['taskkill.exe', '/PID', '111', '/T', '/F']]


async def test_exit_stops_work_before_chrome_and_is_idempotent(monkeypatch):
    from agent.muse_app import shutdown_services
    from agent.services import muse_gateway, muse_queue, muse_scenes, muse_tokens
    calls = []
    def operation(name):
        async def call():
            calls.append(name)
        return AsyncMock(side_effect=call)
    for owner, method, name in [(muse_queue, 'stop', 'queue'), (muse_scenes, 'shutdown', 'scenes'),
                                 (muse_tokens, 'shutdown', 'tokens'), (muse_gateway, 'shutdown', 'gateway')]:
        monkeypatch.setattr(owner, method, operation(name))
    monkeypatch.setattr(cleanup, 'close_owned_chrome', lambda root: calls.append('chrome'))
    connection = asyncio.create_task(asyncio.sleep(100))
    app = SimpleNamespace(state=SimpleNamespace(shutdown_lock=asyncio.Lock(), services_stopped=False, connection_task=connection))
    await shutdown_services(app)
    await shutdown_services(app)
    assert connection.cancelled()
    assert calls == ['queue', 'scenes', 'tokens', 'chrome', 'gateway']
