import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from muse2api.api.routes.videos import create_video
from muse2api.api.schemas import VideoCreateRequest
from muse2api.services.tasks import Task, TaskManager, TaskStatus
from muse2api.errors import InvalidRequest
from agent.services import muse_gateway as gateway


async def test_lost_response_and_concurrent_resubmit_create_only_one_gateway_task():
    records = {}
    def submit(kind, meta, runner, task_id=None):
        task = Task(id=task_id, kind=kind, request=meta)
        records[task_id] = task
        return task
    svc = SimpleNamespace(tasks=SimpleNamespace(get=records.get, submit=submit),
        billing=SimpleNamespace(video_cost=lambda _: 0, reserve=AsyncMock(), refund=AsyncMock()))
    req = SimpleNamespace(headers={'Idempotency-Key': 'stable-scene-key'}, state=SimpleNamespace(key_id='local'),
                          base_url='http://127.0.0.1:18610/', app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(public_base='http://127.0.0.1:18610'))))
    # public_base uses app services settings in the request; patch only transport URL.
    from muse2api.api.routes import videos
    old = videos.public_base
    videos.public_base = lambda _: 'http://127.0.0.1:18610'
    try:
        body = VideoCreateRequest(prompt='a landscape', model='muse-video', duration=8)
        first, second = await asyncio.gather(create_video(body, req, svc), create_video(body, req, svc))
        assert first['id'] == second['id']
        assert len(records) == 1
        assert svc.billing.reserve.await_count == 1
        with pytest.raises(InvalidRequest):
            await create_video(VideoCreateRequest(prompt='different', model='muse-video'), req, svc)
    finally:
        videos.public_base = old


async def test_old_task_not_in_short_history_can_still_be_polled(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, 'DATA', tmp_path)
    monkeypatch.setattr(gateway, 'history', lambda: [])
    (tmp_path / 'tasks.json').write_text(json.dumps([{'id':'task_old', 'kind':'video'}]))
    request = AsyncMock(return_value={'status':'succeeded', 'result':{'url':'http://127.0.0.1:18610/v1/media/vid_old.mp4'}})
    monkeypatch.setattr(gateway, 'request', request)
    result = await gateway.task('task_old')
    assert result['media'] == ['vid_old.mp4']
    request.assert_awaited_once_with('GET', '/v1/videos/task_old')


def test_recover_only_one_exact_unclaimed_task(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, 'DATA', tmp_path)
    rows = [{'id':'task_1', 'kind':'video', 'request':{'prompt':'exact prompt'}}]
    file = tmp_path / 'tasks.json'
    file.write_text(json.dumps(rows))
    assert gateway.find_submitted_video('exact prompt') == 'task_1'
    assert gateway.find_submitted_video('exact prompt', {'task_1'}) is None
    assert gateway.find_submitted_video('similar prompt') is None
    rows.append({'id':'task_2', 'kind':'video', 'request':{'prompt':'exact prompt'}})
    file.write_text(json.dumps(rows))
    assert gateway.find_submitted_video('exact prompt') is None


def test_running_tasks_never_evicted_when_completed_history_is_full(tmp_path):
    mgr = TaskManager(tmp_path / 'tasks.json', max_kept=1)
    mgr._tasks = {'task_running':Task(id='task_running', kind='video', created_at=1),
                  'task_done':Task(id='task_done', kind='video', status=TaskStatus.SUCCEEDED, created_at=2)}
    mgr._persist()
    assert mgr.get('task_running') is not None and mgr.get('task_done') is not None
