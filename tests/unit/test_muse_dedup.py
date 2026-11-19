import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from agent.services import muse_dedup as dedup
from agent.services import muse_scenes as scenes


def test_normalized_duplicate_and_distinct_landscapes():
    assert dedup.near('A rice field, beside a river!', 'a RICE field beside a river') == 'exact'
    assert dedup.near('A rocky beach with a lighthouse', 'Terraced rice fields surrounding a mountain village') is None
    assert dedup.local_conflicts([
        {'image_prompt': 'rice fields', 'camera': 'static'},
        {'image_prompt': 'rice fields', 'camera': 'aerial'},
    ], [])[0]['index'] == 1


async def test_rewrite_preserves_camera_ids_and_unique_scene(monkeypatch):
    original = [dict(id=str(i), camera='static', title='Scene', image_prompt=p, video_prompt='Clouds move')
                for i, p in enumerate(['rice fields', 'rice fields'])]
    monkeypatch.setattr(dedup, 'semantic_conflicts', AsyncMock(return_value=[]))
    chat = AsyncMock(return_value={'text': json.dumps({'scenes': [dict(title='Beach', image_prompt='Rocky beach and lighthouse', video_prompt='Waves break')]})})
    monkeypatch.setattr(dedup.gateway, 'chat', chat)
    result, report = await dedup.repair(original, [], {}, scenes.parse_plan)
    assert result[0] == original[0]
    assert result[1]['id'] == '1' and result[1]['camera'] == 'static'
    assert result[1]['image_prompt'] == 'Rocky beach and lighthouse'
    assert report['rewritten_scenes'] == 1
    assert report['fingerprint'] == dedup.fingerprint(result)
    assert original[1]['image_prompt'] == 'rice fields'


async def test_invalid_semantic_review_fails_closed(monkeypatch):
    monkeypatch.setattr(dedup.gateway, 'chat', AsyncMock(return_value={'text': '{"duplicates":[{"scene":1,"against":"C1"}]}'}))
    with pytest.raises(ValueError):
        await dedup.semantic_conflicts([{'image_prompt': 'sea'}, {'image_prompt': 'forest'}], [])


def test_partial_reply_followed_by_complete_json():
    complete = json.dumps({'scenes': [dict(title='Sea', image_prompt='Ocean cliffs', video_prompt='Waves')]})
    assert len(scenes.parse_plan('{"scenes":[\nAnswer:\n' + complete, 1)) == 1
    with pytest.raises(ValueError):
        scenes.parse_plan(complete[:-3], 1)


async def test_stop_planning_cancels_wait_and_clears_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(scenes, 'ROOT', tmp_path)
    monkeypatch.setattr(scenes, '_planning', {})
    started = asyncio.Event()
    async def waiting(settings):
        started.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(scenes, 'plan', waiting)
    job = await scenes.begin_plan(scenes.Settings(topic='Sea', count=1, cameras=['static']))
    await started.wait()
    stopped = await scenes.stop_plan(job['id'])
    assert stopped['status'] == 'stopped'
    assert not scenes._planning
    assert not list(tmp_path.glob('*.json'))


async def test_stop_before_worker_starts_preserves_existing_task(tmp_path, monkeypatch):
    monkeypatch.setattr(scenes, 'ROOT', tmp_path)
    monkeypatch.setattr(scenes, '_workers', {})
    import uuid
    ident = str(uuid.uuid4())
    item = {'id': ident, 'title': 'Sea', 'status': 'running', 'scenes': [{'image_task': 'already-submitted'}]}
    scenes.save(item)
    scenes._workers[ident] = asyncio.create_task(asyncio.Event().wait())
    result = await scenes.stop(ident)
    assert result['status'] == 'paused'
    assert result['scenes'][0]['image_task'] == 'already-submitted'
    assert not scenes._workers


def test_gateway_does_not_accept_partial_json():
    from muse2api.drivers.browser.dom import structured_reply_complete
    assert not structured_reply_complete('{"scenes":[', required=True)
    assert not structured_reply_complete('I am preparing your scenes', required=True)
    assert structured_reply_complete('```json\n{"scenes": []}\n```', required=True)
