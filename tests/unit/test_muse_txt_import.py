import asyncio
from unittest.mock import Mock

import pytest
import httpx
from fastapi import FastAPI

from agent.services import muse_queue as queue, muse_scenes as scenes


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(scenes, 'ROOT', tmp_path / 'projects')
    monkeypatch.setattr(scenes, 'OUTPUT_ROOT', tmp_path / 'output')
    monkeypatch.setattr(scenes, '_workers', {})
    monkeypatch.setattr(queue, '_task', None)
    monkeypatch.setattr(queue, '_lock', asyncio.Lock())
    monkeypatch.setattr(scenes.gateway, 'prompts_ready', Mock())


async def test_import_preserves_order_duplicates_unicode_and_exact_video_prompt(isolated):
    result = await queue.import_prompts('\ufeff Biển lúc bình minh \r\n\r\nThành phố về đêm\nBiển lúc bình minh', 'cảnh.txt', '9:16')
    assert result['imported'] == 3
    project = scenes.load(result['project_id'])
    assert project['settings']['size'] == '9:16'
    assert [scenes.video_prompt(project, row) for row in project['scenes']] == ['Biển lúc bình minh', 'Thành phố về đêm', 'Biển lúc bình minh']
    assert not result['queue']['running']
    assert queue.prompt_list()['items'][0]['camera_label'] == 'Theo prompt TXT'
    assert all(not row['video_task'] for row in project['scenes'])
    await queue.import_prompts('Other context')
    assert queue.status()['total_prompts'] == 4


@pytest.mark.parametrize('text', ['', '\n \r\n', 'x' * 6001, 'abc\x00def', 'x\n' * 10000])
async def test_invalid_file_imports_nothing(isolated, text):
    with pytest.raises(ValueError):
        await queue.import_prompts(text)
    assert queue.status()['total_prompts'] == 0
    assert scenes.listing() == []


async def test_9999_lines_and_running_queue_append(isolated, monkeypatch):
    class Running:
        def done(self):
            return False
    monkeypatch.setattr(queue, '_task', Running())
    queue.write({'running': True, 'items': []})
    result = await queue.import_prompts('\n'.join(f'Prompt {i}' for i in range(9999)))
    assert result['queue']['running']
    assert result['imported'] == 9999
    assert result['queue']['total_prompts'] == 9999


async def test_import_api_and_local_access(isolated):
    from agent.api.muse_scenes import router
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
        route = '/api/muse/scenes/queue/import-txt'
        assert (await client.post(route, json={'text': 'A coastal sunrise'})).status_code == 403
        headers = {'X-Flowkit-Local-Auth': '1'}
        response = await client.post(route, headers=headers, json={'text': 'A coastal sunrise\nA quiet mountain lake', 'size': '1:1'})
        assert response.status_code == 200
        assert response.json()['imported'] == 2
        assert not response.json()['queue']['running']
        assert (await client.post(route, headers=headers, json={'text': 'hello', 'size': 'wrong'})).status_code == 422
