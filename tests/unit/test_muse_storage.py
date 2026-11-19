import json

import pytest

from muse2api.core.json_storage import durable_write, load_json
from muse2api.accounts.store import JsonAccountStore
from agent.services import muse_gateway


def test_durable_write_keeps_known_good_backup_and_recovers_null_file(tmp_path):
    file = tmp_path / 'accounts.json'
    durable_write(file, '[{"id":"one"}]')
    durable_write(file, '[{"id":"two"}]')
    file.write_bytes(b'\0' * 100)
    assert load_json(file) == [{'id': 'one'}]
    assert json.loads(file.read_text()) == [{'id': 'one'}]
    assert len(list(tmp_path.glob('accounts.json.corrupt-*'))) == 1


def test_corrupt_primary_and_backup_fail_without_silently_erasing_data(tmp_path):
    file = tmp_path / 'tasks.json'
    file.write_bytes(b'\0' * 100)
    file.with_name('tasks.json.bak').write_text('invalid')
    with pytest.raises(ValueError):
        load_json(file)
    assert file.read_bytes() == b'\0' * 100


async def test_account_store_restores_backup_before_load(tmp_path):
    file = tmp_path / 'accounts.json'
    file.write_bytes(b'\0' * 20)
    file.with_name('accounts.json.bak').write_text(json.dumps([
        {'id': 'acc_test', 'label': 'Test', 'cookies': {'hatch_sess': 'fixture'}}]))
    rows = await JsonAccountStore(file).load()
    assert rows[0].id == 'acc_test'


async def test_startup_validates_data_and_reports_account_problem_precisely(tmp_path, monkeypatch):
    monkeypatch.setattr(muse_gateway, 'DATA', tmp_path)
    (tmp_path / 'accounts.json').write_bytes(b'\0' * 40)
    with pytest.raises(ValueError, match='accounts.json') as error:
        await muse_gateway.validate_storage()
    assert 'không phải lỗi Chrome' in str(error.value)


async def test_startup_recovers_backup_and_accepts_valid_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr(muse_gateway, 'DATA', tmp_path)
    (tmp_path / 'accounts.json').write_bytes(b'\0' * 40)
    (tmp_path / 'accounts.json.bak').write_text('[]')
    (tmp_path / 'tasks.json').write_text('[]')
    await muse_gateway.validate_storage()
    assert json.loads((tmp_path / 'accounts.json').read_text()) == []
