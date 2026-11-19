import asyncio
import json
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest

from agent.services import muse_scenes as scenes
from agent.services import muse_gateway as gateway


@pytest.fixture
def state(tmp_path, monkeypatch):
    from agent.services import muse_performance
    monkeypatch.setattr(muse_performance, 'current', lambda: {'max_accounts': 5, 'videos_per_account': 3, 'max_videos': 15})
    monkeypatch.setattr(scenes, 'ROOT', tmp_path / 'projects')
    monkeypatch.setattr(scenes, 'OUTPUT_ROOT', tmp_path / 'Videos' / 'Muse Landscape Studio')
    monkeypatch.setattr(gateway, 'DATA', tmp_path / 'data')
    monkeypatch.setattr(scenes, '_workers', {})
    monkeypatch.setattr(scenes, '_pause', set())
    monkeypatch.setattr(scenes, '_lock', asyncio.Lock())
    monkeypatch.setattr(scenes, '_plan_lock', asyncio.Lock())
    monkeypatch.setattr(scenes, '_planning', {})
    from agent.services import muse_queue
    monkeypatch.setattr(muse_queue, '_task', None)
    monkeypatch.setattr(muse_queue, '_auto_blocked', False)
    monkeypatch.setattr(muse_queue, '_lock', asyncio.Lock())
    monkeypatch.setattr(scenes.dedup, 'semantic_conflicts', AsyncMock(return_value=[]))
    monkeypatch.setattr(gateway, 'require_ready', AsyncMock())
    monkeypatch.setattr(gateway, 'status', AsyncMock(return_value={'available': 1}))
    drafts = {'scenes': [{'title': f'Cảnh {n}', 'image_prompt': f'A distinct landscape {n}', 'video_prompt': f'Soft waves moving {n}'} for n in range(3)]}
    monkeypatch.setattr(gateway, 'chat', AsyncMock(return_value={'text': json.dumps(drafts)}))
    return tmp_path


async def make():
    return await scenes.plan(scenes.Settings(topic='Biển Việt Nam', count=3, cameras=['static', 'aerial']))


async def test_plan_exact_count_random_camera_selected_from_pool_and_persisted(state, monkeypatch):
    choices = iter(['static', 'aerial', 'static'])
    monkeypatch.setattr(scenes.secrets, 'choice', lambda pool: next(choices))
    item = await make()
    assert [s['camera'] for s in item['scenes']] == ['static', 'aerial', 'static']
    assert scenes.load(item['id']) == item
    assert item['status'] == 'draft'
    assert not any(s['image_task'] for s in item['scenes'])
    for scene in item['scenes']:
        prompt = scenes.image_prompt(item, scene)
        assert scenes.CAMERAS[scene['camera']][1] in prompt
        assert 'no people' in prompt and '16:9' in prompt


@pytest.mark.parametrize('text', ['not JSON', '{"scenes": []}', '{"scenes":[{"title":"one"}]}', '[]'])
def test_bad_muse_plan_is_not_silently_replaced(text):
    with pytest.raises(ValueError):
        scenes.parse_plan(text, 3)


async def test_invalid_camera_never_sends_request(state):
    with pytest.raises(ValueError):
        await scenes.plan(scenes.Settings(topic='Biển', count=3, cameras=['not-known']))
    gateway.chat.assert_not_called()


async def test_custom_camera_saved_selected_and_snapshotted(state, monkeypatch):
    camera = await scenes.add_camera('Sát mặt nước', 'Camera gần mặt nước, nhìn về chân trời')
    item = await scenes.plan(scenes.Settings(topic='Biển', count=3, cameras=[camera['id']]))
    assert all(s['camera'] == camera['id'] for s in item['scenes'])
    assert 'nhìn về chân trời' in scenes.image_prompt(item, item['scenes'][0])
    assert 'nhìn về chân trời' in scenes.video_prompt(item, item['scenes'][0])
    scenes.atomic_json(scenes.ROOT / 'cameras.json', {})
    assert 'nhìn về chân trời' in scenes.image_prompt(scenes.load(item['id']), item['scenes'][0])


async def test_edit_camera_before_submission_but_freeze_afterwards(state):
    item = await make()
    changes = [scenes.SceneEdit(**{key: s[key] for key in ('title', 'camera', 'image_prompt', 'video_prompt')}) for s in item['scenes']]
    changes[0].camera = 'zoom_in'
    item = await scenes.edit(item['id'], changes)
    assert item['scenes'][0]['camera'] == 'zoom_in'
    item['scenes'][0]['image_task'] = 'task_already_sent'
    scenes.save(item)
    changes[0].camera = 'static'
    with pytest.raises(ValueError, match='đã gửi'):
        await scenes.edit(item['id'], changes)
    assert scenes.load(item['id'])['scenes'][0]['camera'] == 'zoom_in'


async def install_media_fixtures(state, monkeypatch):
    events = []
    gateway.DATA.joinpath('media').mkdir(parents=True)
    async def generate(kind, prompt, size, references, **kwargs):
        if kind == 'video':
            assert references == []
            assert 'Scenery:' in prompt and 'Style:' in prompt and 'Lighting:' in prompt
        ident = 'task_' + str(len(events))
        events.append(('submit', kind, ident))
        return {'id': ident}
    async def wait(ident, kind):
        events.append(('finish', kind, ident))
        filename = ident + ('.png' if kind == 'image' else '.mp4')
        (gateway.DATA / 'media' / filename).write_bytes(b'test-media-not-real')
        return filename
    monkeypatch.setattr(gateway, 'generate', generate)
    monkeypatch.setattr(scenes, 'wait_result', wait)
    return events


async def test_queue_runs_direct_video_and_resume_skips_finished(state, monkeypatch):
    item = await make()
    events = await install_media_fixtures(state, monkeypatch)
    await scenes.start(item['id'], 'videos')
    await scenes._workers[item['id']]
    assert [event[:2] for event in events] == [('submit', 'video'), ('finish', 'video')] * 3
    finished = scenes.load(item['id'])
    assert finished['status'] == 'completed' and all(s['video'] for s in finished['scenes'])
    events.clear()
    await scenes.start(item['id'], 'videos')
    await scenes._workers[item['id']]
    assert events == []


async def test_pause_after_current_stage_does_not_submit_video(state, monkeypatch):
    item = await make()
    events = await install_media_fixtures(state, monkeypatch)
    actual = scenes.wait_result
    async def pause(ident, kind):
        result = await actual(ident, kind)
        scenes._pause.add(item['id'])
        return result
    monkeypatch.setattr(scenes, 'wait_result', pause)
    await scenes.start(item['id'], 'videos')
    await scenes._workers[item['id']]
    saved = scenes.load(item['id'])
    assert saved['status'] == 'paused' and saved['scenes'][0]['video']
    assert [event[:2] for event in events] == [('submit', 'video'), ('finish', 'video')]


async def test_resume_polls_existing_task_without_submitting(state, monkeypatch):
    item = await make()
    for scene in item['scenes']:
        scene['image_task'] = 'task_existing'
    scenes.save(item)
    events = await install_media_fixtures(state, monkeypatch)
    await scenes.start(item['id'], 'images')
    await scenes._workers[item['id']]
    assert all(event[0] == 'finish' for event in events)


async def test_unknown_submission_not_automatically_retried(state, monkeypatch):
    item = await make()
    item['scenes'][0]['video_task'] = 'submission_unknown'
    scenes.save(item)
    events = await install_media_fixtures(state, monkeypatch)
    await scenes.start(item['id'], 'videos')
    await scenes._workers[item['id']]
    final = scenes.load(item['id'])
    assert final['status'] == 'error'
    assert final['scenes'][0]['video_task'] == 'submission_unknown'
    assert len([event for event in events if event[0] == 'submit']) == 2


async def test_confirmed_failed_task_can_be_retried_but_running_task_kept(state, monkeypatch):
    item = await make()
    item['scenes'][0].update(status='error', image_task='task_failed')
    item['scenes'][1].update(status='error', image_task='task_running')
    scenes.save(item)
    monkeypatch.setattr(gateway, 'task', AsyncMock(side_effect=[{'status': 'failed'}, {'status': 'running'}]))
    result = await scenes.retry_failed(item['id'])
    assert result['scenes'][0]['image_task'] is None
    assert result['scenes'][1]['image_task'] == 'task_running'


def test_restarted_worker_is_paused_without_losing_task(state):
    ident = str(uuid.uuid4())
    item = {'id': ident, 'title': 'Test', 'status': 'running', 'scenes': [{'image_task': 'task_keep'}]}
    scenes.save(item)
    result = scenes.load(ident)
    assert result['status'] == 'paused' and result['scenes'][0]['image_task'] == 'task_keep'


@pytest.mark.parametrize('name', ['../api_key', '..\\api_key', 'C:\\Windows\\secret'])
def test_media_path_cannot_escape_private_media_directory(state, name):
    with pytest.raises(ValueError):
        scenes.media_file(name)


async def test_app_has_no_google_flow_routes_and_download_requires_local_guard(state):
    from agent.muse_app import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
        assert (await client.get('/health')).json()['application'] == 'Muse Landscape Studio'
        assert (await client.get('/api/flow/status')).status_code == 404
        assert (await client.get('/api/muse/scenes/options')).status_code == 403
        assert (await client.get('/api/muse/scenes/options', headers={'X-Flowkit-Local-Auth': '1'})).status_code == 200


async def test_exact_plan_count_and_request_validation(state):
    from agent.muse_app import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1', headers={'X-Flowkit-Local-Auth': '1'}) as client:
        for count in (0, 10000):
            assert (await client.post('/api/muse/scenes/plan', json={'topic': 'biển', 'count': count, 'cameras': ['static']})).status_code == 422
        assert (await client.post('/api/muse/scenes/plan', json={'topic': 'biển', 'count': 3, 'cameras': []})).status_code == 422


async def test_export_zip_has_media_and_plan_not_credentials(state, monkeypatch):
    from agent.muse_app import app
    from zipfile import ZipFile
    import io
    item = await make()
    media = gateway.DATA / 'media'; media.mkdir(parents=True)
    (media / 'img_safe.png').write_bytes(b'image-fixture')
    item['scenes'][0]['image'] = 'img_safe.png'
    scenes.save(item)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1', headers={'X-Flowkit-Local-Auth': '1'}) as client:
        result = await client.get('/api/muse/scenes/' + item['id'] + '/download')
        assert result.status_code == 200
        with ZipFile(io.BytesIO(result.content)) as archive:
            assert set(archive.namelist()) == {'scenes.json', 'scene-01-image.png'}
    assert not list(scenes.ROOT.glob('download-*'))


def test_default_cameras_match_requested_six_presets():
    assert [label for label, _ in scenes.CAMERAS.values()] == [
        'Fly cam', 'Zoom xa đến gần', 'Góc tĩnh',
        'Góc pan', 'Gần đến xa', 'Góc quay cận',
    ]


async def test_custom_landscape_persists_without_changing_existing_project(state):
    project = await make()
    original = scenes.load(project['id'])
    item = await scenes.add_landscape(' Rừng núi ', ' Rừng thông trên núi, không có người ')
    assert item['label'] == 'Rừng núi'
    assert scenes.landscape_options() == [item]
    assert scenes.load(project['id']) == original
    with pytest.raises(ValueError):
        await scenes.add_landscape('Rừng núi', 'Mô tả mới')
    with pytest.raises(ValueError):
        await scenes.add_landscape('   ', '     ')


async def test_custom_landscape_endpoint_is_local_and_returns_saved_options(state):
    from agent.muse_app import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
        body = {'label': 'Hồ nước', 'description': 'Hồ nước trong xanh giữa rừng núi'}
        assert (await client.post('/api/muse/scenes/landscapes', json=body)).status_code == 403
        headers = {'X-Flowkit-Local-Auth': '1'}
        result = await client.post('/api/muse/scenes/landscapes', json=body, headers=headers)
        assert result.status_code == 200
        options = (await client.get('/api/muse/scenes/options', headers=headers)).json()
        assert options['landscapes'] == [result.json()]
        assert len(options['cameras']) == 6


async def test_landscape_can_be_saved_by_name_with_description_added_later(state):
    from agent.muse_app import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1', headers={'X-Flowkit-Local-Auth': '1'}) as client:
        result = await client.post('/api/muse/scenes/landscapes', json={'label': 'Sa mạc'})
        assert result.status_code == 200
        assert result.json()['description'] == ''
        assert scenes.landscape_options()[0]['label'] == 'Sa mạc'


async def test_completed_media_is_automatically_copied_with_readable_scene_names(state, monkeypatch):
    item = await make()
    await install_media_fixtures(state, monkeypatch)
    await scenes.start(item['id'], 'videos')
    await scenes._workers[item['id']]
    folder = scenes.output_directory(item)
    assert folder.is_relative_to(scenes.OUTPUT_ROOT)
    assert {p.name for p in folder.iterdir()} == {f"{item['id']}-{i:03d}-video.mp4" for i in range(1, 4)}
    assert (folder / f"{item['id']}-001-video.mp4").read_bytes() == b'test-media-not-real'
    assert scenes.load(item['id'])['output_directory'] == str(folder)


async def test_export_retains_user_existing_file_and_ignores_saved_arbitrary_path(state):
    item = await make()
    item['output_directory'] = 'C:/Windows'
    folder = scenes.output_directory(item)
    assert folder.is_relative_to(scenes.OUTPUT_ROOT)
    media = gateway.DATA / 'media'; media.mkdir(parents=True)
    (media / 'vid_safe.mp4').write_bytes(b'generated-fixture')
    item['scenes'][0]['video'] = 'vid_safe.mp4'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{item['id']}-001-video.mp4").write_bytes(b'existing-user-copy')
    scenes.export_scene(item, item['scenes'][0])
    assert (folder / f"{item['id']}-001-video.mp4").read_bytes() == b'existing-user-copy'


async def test_output_folder_is_visible_and_opening_is_local_only(state, monkeypatch):
    from agent.muse_app import app
    opened = []
    monkeypatch.setattr('os.startfile', lambda p: opened.append(p))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
        assert (await client.post('/api/muse/scenes/storage/open')).status_code == 403
        headers = {'X-Flowkit-Local-Auth': '1'}
        result = await client.get('/api/muse/scenes/storage', headers=headers)
        assert result.json()['directory'] == str(scenes.OUTPUT_ROOT)
        result = await client.post('/api/muse/scenes/storage/open', headers=headers)
        assert result.status_code == 200 and opened == [str(scenes.OUTPUT_ROOT)]


async def test_selected_folder_persists_and_copies_existing_results(state):
    item = await make()
    media = gateway.DATA / 'media'
    media.mkdir(parents=True)
    (media / 'existing.png').write_bytes(b'generated-image')
    item['scenes'][0]['image'] = 'existing.png'
    scenes.save(item)
    target = state / 'chosen-output'
    result = await scenes.set_output_directory(str(target), item['id'])
    assert scenes.output_directory() == target
    loaded = scenes.load(item['id'])
    assert scenes.output_directory(loaded).is_relative_to(target)
    assert (scenes.output_directory(loaded) / f"{item['id']}-001-image.png").read_bytes() == b'generated-image'
    assert result['project']['output_directory'] == loaded['output_directory']
    assert len(scenes.listing()) == 1


async def test_invalid_or_running_folder_change_does_not_save(state):
    with pytest.raises(ValueError):
        await scenes.set_output_directory('relative-folder')
    scenes._workers['busy'] = object()
    with pytest.raises(ValueError, match='Dừng'):
        await scenes.set_output_directory(str(state / 'new-output'))
    assert not (scenes.ROOT / 'storage-settings.json').exists()


async def test_folder_picker_cancel_and_storage_require_local_auth(state, monkeypatch):
    from agent.muse_app import app
    from agent.services import muse_folder_picker
    monkeypatch.setattr(muse_folder_picker, 'choose', AsyncMock(return_value=''))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
        assert (await client.post('/api/muse/scenes/storage/choose')).status_code == 403
        assert (await client.post('/api/muse/scenes/storage', json={'directory': str(state)})).status_code == 403
        result = await client.post('/api/muse/scenes/storage/choose', headers={'X-Flowkit-Local-Auth': '1'})
        assert result.status_code == 200 and result.json()['directory'] is None
        assert not (scenes.ROOT / 'storage-settings.json').exists()


async def test_planning_no_longer_audits_or_rewrites_duplicates(state, monkeypatch):
    draft = dict(title='Sea', image_prompt='Identical ocean scenery', video_prompt='Waves moving')
    monkeypatch.setattr(gateway, 'chat', AsyncMock(return_value={'text': json.dumps({'scenes': [draft] * 3})}))
    repair = AsyncMock(side_effect=AssertionError('Duplicate filter must not run'))
    monkeypatch.setattr(scenes.dedup, 'repair', repair)
    item = await make()
    assert item['deduplication']['enabled'] is False
    assert gateway.chat.await_count == 1
    repair.assert_not_called()
    events = await install_media_fixtures(state, monkeypatch)
    await scenes.start(item['id'], 'images')
    await scenes._workers[item['id']]
    assert len([event for event in events if event[0] == 'submit']) == 3


async def test_9999_scenes_batched_and_numbered(state, monkeypatch):
    calls = []
    async def chunk(settings, persist, offset, total, on_scene=None):
        calls.append((offset, settings.count))
        return {'id': str(uuid.uuid4()), 'title': settings.topic, 'settings': settings.model_dump(),
                'status': 'draft', 'scenes': [{'id': str(uuid.uuid4()), 'number': n + 1} for n in range(settings.count)]}
    monkeypatch.setattr(scenes, '_plan', chunk)
    job = await scenes.begin_plan(scenes.Settings(topic='Sea', count=9999, cameras=['static']))
    await scenes._planning[job['id']]
    done = scenes.planning_status(job['id'])
    item = scenes.load(done['project_id'])
    assert done['status'] == 'completed' and done['completed_scenes'] == 9999
    assert len(calls) == 334 and calls[-1] == (9990, 9)
    assert [s['number'] for s in item['scenes']] == list(range(1, 10000))
    assert item['settings']['count'] == 9999


async def test_batch_failure_keeps_completed_scenes_and_resumes(state, monkeypatch):
    async def single_attempt(call, on_retry):
        return await call()
    monkeypatch.setattr(scenes, '_retry_prompt', single_attempt)
    monkeypatch.setattr(scenes.asyncio, 'sleep', AsyncMock())
    allow = [False]
    calls = []
    async def chunk(settings, persist, offset, total, on_scene=None):
        calls.append(offset)
        if offset == 30 and not allow[0]:
            raise ValueError('Temporary Muse failure')
        return {'id': str(uuid.uuid4()), 'title': settings.topic, 'settings': settings.model_dump(),
                'status': 'draft', 'scenes': [{'id': str(uuid.uuid4()), 'number': n + 1} for n in range(settings.count)]}
    monkeypatch.setattr(scenes, '_plan', chunk)
    settings = scenes.Settings(topic='Sea', count=61, cameras=['static'])
    job = await scenes.begin_plan(settings)
    await scenes._planning[job['id']]
    failed = scenes.planning_status(job['id'])
    item = scenes.load(failed['project_id'])
    assert failed['status'] == 'error' and len(item['scenes']) == 31
    original_ids = [s['id'] for s in item['scenes']]
    allow[0] = True
    resumed = await scenes.begin_plan(settings, item['id'])
    await scenes._planning[resumed['id']]
    final = scenes.load(item['id'])
    assert len(final['scenes']) == 61 and calls == [0, 30, 60] + [30] * 6
    assert [s['id'] for s in final['scenes'][:30]] == original_ids[:30]
    assert final['scenes'][-1]['id'] == original_ids[-1]


async def test_prompt_batches_parallel_and_out_of_order_saved_in_order(state, monkeypatch):
    monkeypatch.setattr(gateway, 'status', AsyncMock(return_value={'available': 2}))
    started = asyncio.Event()
    gate = asyncio.Event()
    offsets = []
    async def chunk(settings, persist, offset, total, on_scene=None):
        offsets.append(offset)
        if len(offsets) == 2:
            started.set()
        if offset == 0:
            await gate.wait()
        return {'settings': settings.model_dump(), 'scenes': [
            {'id': str(uuid.uuid4()), 'number': n + 1, 'title': str(offset)} for n in range(settings.count)]}
    monkeypatch.setattr(scenes, '_plan', chunk)
    job = await scenes.begin_plan(scenes.Settings(topic='Sea', count=6, cameras=['static']))
    await asyncio.wait_for(started.wait(), 2)
    partial = scenes.load(scenes.planning_status(job['id'])['project_id'])
    assert [s['number'] for s in partial['scenes']] == [4, 5, 6]
    gate.set()
    await scenes._planning[job['id']]
    final = scenes.load(partial['id'])
    assert [s['number'] for s in final['scenes']] == [1, 2, 3, 4, 5, 6]


def test_count_limit_is_9999():
    assert scenes.Settings(topic='Sea', count=9999, cameras=['static']).count == 9999
    with pytest.raises(ValueError):
        scenes.Settings(topic='Sea', count=10000, cameras=['static'])


async def test_two_accounts_run_six_video_waiters_and_stop_preserves_ids(state, monkeypatch):
    item = await make()
    template = item['scenes'][0]
    item['scenes'] = [{**template, 'id': str(uuid.uuid4()), 'number': n + 1} for n in range(12)]
    item['settings']['count'] = 12
    scenes.save(item)
    monkeypatch.setattr(gateway, 'status', AsyncMock(return_value={'available': 2}))
    all_started = asyncio.Event()
    count = [0]
    async def generate(*args, **kwargs):
        count[0] += 1
        return {'id': 'task_' + str(count[0])}
    waiting = [0]
    async def wait(*args):
        waiting[0] += 1
        if waiting[0] == 6:
            all_started.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(gateway, 'generate', generate)
    monkeypatch.setattr(scenes, 'wait_result', wait)
    await scenes.start(item['id'], 'videos')
    await asyncio.wait_for(all_started.wait(), 2)
    stopped = await scenes.stop(item['id'])
    assert stopped['parallelism'] == 6 and count[0] == 6
    assert len({s['video_task'] for s in stopped['scenes'] if s['video_task']}) == 6
    assert stopped['status'] == 'paused' and not scenes._workers


async def test_stack_same_context_projects_without_generating_until_start(state, monkeypatch):
    from agent.services import muse_queue
    first = await make()
    second = await make()
    events = await install_media_fixtures(state, monkeypatch)
    await muse_queue.add(first['id'])
    await muse_queue.add(second['id'])
    await muse_queue.add(first['id'])
    queue = muse_queue.status()
    assert len(queue['items']) == 2 and queue['total_prompts'] == 6
    assert not events and not queue['running']
    await muse_queue.start()
    await muse_queue._task
    assert all(row['status'] == 'completed' for row in muse_queue.status()['items'])
    assert len([event for event in events if event[0] == 'submit']) == 6


async def test_queue_survives_restart_without_auto_start_and_remove_preserves_project(state):
    from agent.services import muse_queue
    project = await make()
    await muse_queue.add(project['id'])
    saved = muse_queue.read()
    saved['running'] = True
    saved['items'][0]['status'] = 'running'
    muse_queue.write(saved)
    recovered = muse_queue.status()
    assert not recovered['running'] and recovered['items'][0]['status'] == 'paused'
    await muse_queue.remove(recovered['items'][0]['id'])
    assert not muse_queue.status()['items']
    assert scenes.load(project['id'])['id'] == project['id']


async def test_plan_enqueue_only_adds_prompts_never_media(state):
    from agent.services import muse_queue
    job = await scenes.begin_plan(scenes.Settings(topic='Sea', count=3, cameras=['static']), enqueue=True)
    await scenes._planning[job['id']]
    queue = muse_queue.status()
    assert queue['total_prompts'] == 3 and not queue['running']
    project = scenes.load(queue['items'][0]['project_id'])
    assert not any(scene['video_task'] for scene in project['scenes'])


async def test_stopping_queue_stops_current_and_does_not_start_next_project(state, monkeypatch):
    from agent.services import muse_queue
    first, second = await make(), await make()
    await muse_queue.add(first['id'])
    await muse_queue.add(second['id'])
    started = asyncio.Event()
    async def wait(*args):
        started.set()
        await asyncio.Event().wait()
    await install_media_fixtures(state, monkeypatch)
    monkeypatch.setattr(scenes, 'wait_result', wait)
    await muse_queue.start()
    await started.wait()
    queue = await muse_queue.stop()
    assert not queue['running'] and queue['items'][0]['status'] == 'paused'
    assert not any(scene['video_task'] for scene in scenes.load(second['id'])['scenes'])
    assert not scenes._workers


async def test_delete_selected_cameras_persists_and_keeps_saved_projects_usable(state):
    custom = await scenes.add_camera('Sát mặt nước', 'Glide along the water surface')
    item = await scenes.plan(scenes.Settings(topic='Sea', count=3, cameras=[custom['id']]))
    before = scenes.video_prompt(item, item['scenes'][0])
    remaining = await scenes.delete_cameras(['static', custom['id']])
    assert 'static' not in {row['id'] for row in remaining}
    assert custom['id'] not in {row['id'] for row in scenes.camera_options()}
    assert scenes.video_prompt(scenes.load(item['id']), item['scenes'][0]) == before
    edits = [scenes.SceneEdit(**{key: scene[key] for key in ('title', 'camera', 'image_prompt', 'video_prompt')}) for scene in item['scenes']]
    assert (await scenes.edit(item['id'], edits))['id'] == item['id']
    with pytest.raises(ValueError):
        await scenes.plan(scenes.Settings(topic='Sea', count=3, cameras=['static']))


async def test_delete_cameras_unknown_ids_does_not_mutate_library(state):
    before = scenes.camera_options()
    with pytest.raises(ValueError):
        await scenes.delete_cameras(['static', 'unknown-camera'])
    assert scenes.camera_options() == before


async def test_multiple_projects_export_directly_without_subfolders_or_overwrite(state, monkeypatch):
    first, second = await make(), await make()
    media = gateway.DATA / 'media'
    media.mkdir(parents=True)
    (media / 'first.mp4').write_bytes(b'first-result')
    (media / 'second.mp4').write_bytes(b'second-result')
    first['scenes'][0]['video'] = 'first.mp4'
    second['scenes'][0]['video'] = 'second.mp4'
    scenes.export_scene(first, first['scenes'][0])
    scenes.export_scene(second, second['scenes'][0])
    assert scenes.output_directory(first) == scenes.output_directory(second) == scenes.OUTPUT_ROOT
    files = list(scenes.OUTPUT_ROOT.iterdir())
    assert len(files) == 2 and all(file.is_file() for file in files)
    assert {file.read_bytes() for file in files} == {b'first-result', b'second-result'}


async def test_scene_failure_does_not_block_others_then_retries_after_main_pass(state, monkeypatch):
    item = await make()
    events = await install_media_fixtures(state, monkeypatch)
    actual = scenes.wait_result
    attempts = {}
    async def wait(ident, kind):
        attempts[ident] = attempts.get(ident, 0) + 1
        if ident == 'task_0' and attempts[ident] == 1:
            events.append(('error', kind, ident))
            raise ValueError('Temporary failure')
        return await actual(ident, kind)
    monkeypatch.setattr(scenes, 'wait_result', wait)
    monkeypatch.setattr(gateway, 'task', AsyncMock(return_value={'status': 'running'}))
    await scenes.start(item['id'], 'videos')
    await scenes._workers[item['id']]
    final = scenes.load(item['id'])
    assert final['status'] == 'completed'
    assert final['scenes'][0]['retry_count'] == 1
    assert len([event for event in events if event[0] == 'submit']) == 3
    assert events[-1] == ('finish', 'video', 'task_0')


async def test_persistent_scene_error_retries_five_times_and_queue_continues(state, monkeypatch):
    from agent.services import muse_queue
    first, second = await make(), await make()
    await muse_queue.add(first['id'])
    await muse_queue.add(second['id'])
    events = await install_media_fixtures(state, monkeypatch)
    actual = scenes.wait_result
    calls = []
    async def wait(ident, kind):
        calls.append(ident)
        if ident == 'task_0':
            raise ValueError('Permanent failure')
        return await actual(ident, kind)
    monkeypatch.setattr(scenes, 'wait_result', wait)
    monkeypatch.setattr(gateway, 'task', AsyncMock(return_value={'status': 'running'}))
    await muse_queue.start()
    await muse_queue._task
    final = scenes.load(first['id'])
    assert final['status'] == 'error' and final['scenes'][0]['retry_count'] == 5
    assert calls.count('task_0') == 6
    assert calls[-5:] == ['task_0'] * 5
    assert all(scene['video'] for scene in scenes.load(second['id'])['scenes'])
    assert [row['status'] for row in muse_queue.status()['items']] == ['error', 'completed']


async def test_confirmed_failed_video_resubmits_and_preserves_completed_scenes(state, monkeypatch):
    item = await make()
    events = await install_media_fixtures(state, monkeypatch)
    actual = scenes.wait_result
    async def wait(ident, kind):
        if ident == 'task_0':
            raise ValueError('Confirmed failed')
        return await actual(ident, kind)
    monkeypatch.setattr(scenes, 'wait_result', wait)
    monkeypatch.setattr(gateway, 'task', AsyncMock(return_value={'status': 'failed'}))
    await scenes.start(item['id'], 'videos')
    await scenes._workers[item['id']]
    final = scenes.load(item['id'])
    assert final['status'] == 'completed'
    assert len([event for event in events if event[0] == 'submit']) == 4
    assert final['scenes'][0]['video_task'] != 'task_0'


async def test_quota_stops_queue_without_retries_and_shows_reason_on_queue_row(state, monkeypatch):
    from agent.services import muse_queue
    first, second = await make(), await make()
    await muse_queue.add(first['id'])
    await muse_queue.add(second['id'])
    await install_media_fixtures(state, monkeypatch)
    async def quota(*args):
        raise gateway.QuotaExhausted()
    monkeypatch.setattr(scenes, 'wait_result', quota)
    await muse_queue.start()
    await muse_queue._task
    queue = muse_queue.status()
    assert not queue['running']
    assert queue['items'][0]['quota_exhausted']
    assert 'hết hạn mức' in queue['items'][0]['error']
    assert not any(scene.get('retry_count') for scene in scenes.load(first['id'])['scenes'])
    assert not any(scene['video_task'] for scene in scenes.load(second['id'])['scenes'])


async def test_wait_result_uses_explicit_quota_code(state, monkeypatch):
    monkeypatch.setattr(gateway, 'task', AsyncMock(return_value={
        'status': 'failed', 'error_code': 'upstream_quota_exhausted'}))
    with pytest.raises(gateway.QuotaExhausted):
        await scenes.wait_result('task_quota', 'video')


async def test_prompt_retry_recovers_without_repeating_success(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(scenes.asyncio, 'sleep', sleep)
    call = AsyncMock(side_effect=[ValueError('temporary'), {'scenes': 'success'}])
    notices = []
    assert await scenes._retry_prompt(call, notices.append) == {'scenes': 'success'}
    assert call.await_count == 2 and notices == [1]


async def test_prompt_retry_stops_after_five_additional_attempts(monkeypatch):
    monkeypatch.setattr(scenes.asyncio, 'sleep', AsyncMock())
    call = AsyncMock(side_effect=ValueError('persistent'))
    notices = []
    with pytest.raises(ValueError):
        await scenes._retry_prompt(call, notices.append)
    assert call.await_count == 6 and notices == [1, 2, 3, 4, 5]


async def test_prompt_quota_or_cancel_never_automatically_retries(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(scenes.asyncio, 'sleep', sleep)
    for error in (gateway.QuotaExhausted(), asyncio.CancelledError()):
        call = AsyncMock(side_effect=error)
        with pytest.raises(type(error)):
            await scenes._retry_prompt(call, lambda attempt: None)
        assert call.await_count == 1
    sleep.assert_not_called()


async def test_stop_at_300_of_500_enqueues_partial_and_resume_preserves_existing_media(state, monkeypatch):
    from agent.services import muse_queue
    template = (await make())['scenes'][0]
    waiting = asyncio.Event()
    resume = [False]
    async def chunk(settings, persist, offset, total, on_scene=None):
        if offset >= 300 and not resume[0]:
            waiting.set()
            await asyncio.Event().wait()
        return {'settings': settings.model_dump(), 'scenes': [
            {**template, 'id': str(uuid.uuid4()), 'number': offset + n + 1} for n in range(settings.count)]}
    monkeypatch.setattr(scenes, '_plan', chunk)
    job = await scenes.begin_plan(scenes.Settings(topic='Sea', count=500, cameras=['static']), enqueue=True)
    await waiting.wait()
    stopped = await scenes.stop_plan(job['id'])
    queue = muse_queue.status()
    assert stopped['status'] == 'stopped' and '300/500' in stopped['message']
    assert queue['total_prompts'] == 300 and len(queue['items']) == 1 and not queue['running']
    project = scenes.load(stopped['project_id'])
    project['scenes'][0].update(video='already-created.mp4', video_task='task_existing')
    scenes.save(project)
    resume[0] = True
    resumed = await scenes.begin_plan(scenes.Settings(**project['settings']), project['id'])
    await scenes._planning[resumed['id']]
    final = scenes.load(project['id'])
    assert len(final['scenes']) == 500
    assert final['scenes'][0]['video'] == 'already-created.mp4'
    assert muse_queue.status()['total_prompts'] == 500


async def test_older_stopped_partial_is_recovered_once_and_can_be_removed(state):
    from agent.services import muse_queue
    project = await make()
    project['settings']['count'] = 500
    scenes.save(project)
    scenes.atomic_json(scenes.planning_path(str(uuid.uuid4())), {'status': 'stopped', 'project_id': project['id']})
    await muse_queue.recover_stopped_plans()
    row = muse_queue.status()['items'][0]
    assert row['count'] == 3
    await muse_queue.remove(row['id'])
    await muse_queue.recover_stopped_plans()
    assert not muse_queue.status()['items']


async def test_streaming_first_complete_prompt_enqueued_before_reply_finishes(state, monkeypatch):
    from agent.services import muse_queue
    ready = asyncio.Event()
    draft = {'title': 'Sea', 'image_prompt': 'Ocean cliffs', 'video_prompt': 'Waves moving'}
    async def streaming(prompt, on_text=None):
        await on_text('{"scenes":[' + json.dumps(draft) + ',{"title":"unfinished')
        ready.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(gateway, 'chat', streaming)
    job = await scenes.begin_plan(scenes.Settings(topic='Sea', count=3, cameras=['static']), enqueue=True)
    await ready.wait()
    assert muse_queue.status()['total_prompts'] == 1
    stopped = await scenes.stop_plan(job['id'])
    assert muse_queue.status()['total_prompts'] == 1
    project = scenes.load(stopped['project_id'])
    original_id = project['scenes'][0]['id']
    monkeypatch.setattr(gateway, 'chat', AsyncMock(return_value={'text': json.dumps({'scenes': [draft] * 3})}))
    resumed = await scenes.begin_plan(scenes.Settings(**project['settings']), project['id'], enqueue=True)
    await scenes._planning[resumed['id']]
    assert muse_queue.status()['total_prompts'] == 3
    assert scenes.load(project['id'])['scenes'][0]['id'] == original_id


async def test_new_prompt_batch_joins_active_video_queue(state, monkeypatch):
    from agent.services import muse_queue
    first = await make()
    await muse_queue.add(first['id'])
    await install_media_fixtures(state, monkeypatch)
    waiting = asyncio.Event()
    release = asyncio.Event()
    actual = scenes.wait_result
    async def wait(ident, kind):
        waiting.set()
        await release.wait()
        return await actual(ident, kind)
    monkeypatch.setattr(scenes, 'wait_result', wait)
    await muse_queue.start()
    await waiting.wait()
    job = await scenes.begin_plan(scenes.Settings(topic='Forest', count=3, cameras=['static']), enqueue=True)
    await scenes._planning[job['id']]
    new_id = scenes.planning_status(job['id'])['project_id']
    assert muse_queue.status()['total_prompts'] == 6
    release.set()
    await muse_queue._task
    assert all(scene['video'] for scene in scenes.load(new_id)['scenes'])
    assert muse_queue.status()['items'][1]['status'] == 'completed'


async def test_auto_video_starts_from_first_prompt_while_reply_still_streams(state, monkeypatch):
    from agent.services import muse_queue
    events = await install_media_fixtures(state, monkeypatch)
    first_video = asyncio.Event()
    actual = scenes.wait_result
    async def wait(ident, kind):
        result = await actual(ident, kind)
        first_video.set()
        return result
    monkeypatch.setattr(scenes, 'wait_result', wait)
    draft = {'title': 'Sea', 'image_prompt': 'Ocean cliffs', 'video_prompt': 'Waves moving'}
    async def streaming(prompt, on_text=None):
        await on_text('{"scenes":[' + json.dumps(draft) + ',')
        await asyncio.wait_for(first_video.wait(), 3)
        text = json.dumps({'scenes': [draft] * 3})
        await on_text(text)
        return {'text': text}
    monkeypatch.setattr(gateway, 'chat', streaming)
    job = await scenes.begin_plan(scenes.Settings(topic='Sea', count=3, cameras=['static']), enqueue=True, auto_run=True)
    await scenes._planning[job['id']]
    await asyncio.wait_for(muse_queue._task, 5)
    project = scenes.load(scenes.planning_status(job['id'])['project_id'])
    assert len(project['scenes']) == 3 and all(scene['video'] for scene in project['scenes']), (project, muse_queue.status(), events)
    assert len([event for event in events if event[0] == 'submit']) == 3
    assert muse_queue.status()['items'][0]['status'] == 'completed'


async def test_failed_prompt_batch_moves_to_later_batches_before_retry(state, monkeypatch):
    monkeypatch.setattr(scenes.asyncio, 'sleep', AsyncMock())
    calls = []
    async def chunk(settings, persist, offset, total, on_scene=None):
        calls.append(offset)
        if offset == 0 and calls.count(0) == 1:
            raise ValueError('First batch failed')
        return {'settings': settings.model_dump(), 'scenes': [
            {'id': str(uuid.uuid4()), 'number': offset + n + 1} for n in range(settings.count)]}
    monkeypatch.setattr(scenes, '_plan', chunk)
    job = await scenes.begin_plan(scenes.Settings(topic='Sea', count=61, cameras=['static']))
    await scenes._planning[job['id']]
    assert calls == [0, 30, 60, 0]
    assert scenes.planning_status(job['id'])['status'] == 'completed'


async def test_video_error_does_not_block_later_streamed_prompts(state, monkeypatch):
    from agent.services import muse_queue
    events = await install_media_fixtures(state, monkeypatch)
    first_failed = asyncio.Event()
    calls = []
    actual = scenes.wait_result
    async def wait(ident, kind):
        calls.append(ident)
        if ident == 'task_0' and calls.count(ident) == 1:
            first_failed.set()
            raise ValueError('First video temporarily failed')
        return await actual(ident, kind)
    monkeypatch.setattr(scenes, 'wait_result', wait)
    monkeypatch.setattr(gateway, 'task', AsyncMock(return_value={'status': 'running'}))
    draft = {'title': 'Sea', 'image_prompt': 'Ocean cliffs', 'video_prompt': 'Waves moving'}
    async def streaming(prompt, on_text=None):
        await on_text('{"scenes":[' + json.dumps(draft) + ',')
        await first_failed.wait()
        text = json.dumps({'scenes': [draft] * 3})
        await on_text(text)
        return {'text': text}
    monkeypatch.setattr(gateway, 'chat', streaming)
    job = await scenes.begin_plan(scenes.Settings(topic='Sea', count=3, cameras=['static']), enqueue=True, auto_run=True)
    await scenes._planning[job['id']]
    await asyncio.wait_for(muse_queue._task, 5)
    project = scenes.load(scenes.planning_status(job['id'])['project_id'])
    assert all(scene['video'] for scene in project['scenes'])
    assert calls[0] == 'task_0' and calls[-1] == 'task_0' and len(calls) == 4
    assert len([event for event in events if event[0] == 'submit']) == 3


async def test_prompt_queue_flat_list_paginates_across_contexts_and_skips_missing_projects(state):
    from agent.services import muse_queue
    first, second = await make(), await make()
    await muse_queue.add(first['id'])
    await muse_queue.add(second['id'])
    saved = muse_queue.read()
    saved['items'].insert(0, {'id': str(uuid.uuid4()), 'project_id': str(uuid.uuid4()), 'status': 'waiting'})
    muse_queue.write(saved)
    result = muse_queue.prompt_list(page=2, limit=2)
    assert result['total'] == 6 and result['pages'] == 3
    assert [row['id'] for row in result['items']] == [first['scenes'][2]['id'], second['scenes'][0]['id']]
    assert [row['ordinal'] for row in result['items']] == [3, 4]
    assert all(row['image_prompt'] and row['camera_label'] for row in result['items'])
    assert len(result['missing']) == 1


async def test_prompt_queue_api_is_local_only_and_returns_individual_prompts(state):
    from agent.services import muse_queue
    from agent.muse_app import app
    project = await make()
    await muse_queue.add(project['id'])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1') as client:
        assert (await client.get('/api/muse/scenes/queue/prompts')).status_code == 403
        response = await client.get('/api/muse/scenes/queue/prompts?limit=2', headers={'X-Flowkit-Local-Auth': '1'})
        assert response.status_code == 200
        assert response.json()['total'] == 3 and len(response.json()['items']) == 2




async def test_queue_missing_project_does_not_block_valid_prompts(state, monkeypatch):
    from agent.services import muse_queue
    item = await make()
    events = await install_media_fixtures(state, monkeypatch)
    muse_queue.write({'running': False, 'items': [{'id': str(uuid.uuid4()), 'project_id': str(uuid.uuid4()), 'status': 'paused'}]})
    await muse_queue.add(item['id'])
    await muse_queue.start()
    await muse_queue._task
    assert len([event for event in events if event[0] == 'submit']) == 3
    assert muse_queue.status()['items'][1]['status'] == 'completed'


async def test_clear_queue_preserves_project_and_media_and_blocks_active_jobs(state):
    from agent.services import muse_queue
    item = await make()
    await muse_queue.add(item['id'])
    scenes._planning['active'] = object()
    with pytest.raises(ValueError):
        await muse_queue.clear()
    assert muse_queue.status()['total_prompts'] == 3
    scenes._planning.clear()
    media = state / 'saved-video.mp4'
    media.write_bytes(b'existing-video')
    assert not (await muse_queue.clear())['items']
    assert len(scenes.load(item['id'])['scenes']) == 3
    assert media.read_bytes() == b'existing-video'
    assert scenes.load(item['id'])['partial_queue_recovered']


async def test_video_submission_response_lost_reuses_same_key_on_retry(state, monkeypatch):
    item = await make()
    await install_media_fixtures(state, monkeypatch)
    original = gateway.generate
    calls = {}
    async def lost(kind, prompt, size, references, request_id=None):
        seen = calls.setdefault(prompt, [])
        seen.append(request_id)
        if len(seen) == 1:
            raise ValueError('response lost after accepted')
        return await original(kind, prompt, size, references)
    monkeypatch.setattr(gateway, 'generate', lost)
    await scenes.start(item['id'], 'videos')
    await scenes._workers[item['id']]
    assert all(scene.get('video') for scene in scenes.load(item['id'])['scenes'])
    assert all(len(keys) == 2 and keys[0] and keys[0] == keys[1] for keys in calls.values())


async def test_old_unknown_with_five_retries_is_flagged_without_sending_again(state, monkeypatch):
    item = await make()
    item['scenes'][0].update(video_task='submission_unknown', status='error', retry_count=5)
    scenes.save(item)
    events = await install_media_fixtures(state, monkeypatch)
    await scenes.start(item['id'], 'videos')
    await scenes._workers[item['id']]
    result = scenes.load(item['id'])
    assert result['scenes'][0]['status'] == 'needs_review'
    assert result['scenes'][0]['retry_count'] == 5
    assert len([x for x in events if x[0] == 'submit']) == 2


async def test_explicit_requeue_preserves_finished_video_and_releases_only_failed_scenes(state):
    from agent.services import muse_queue
    item = await make()
    item['scenes'][0].update(video='existing.mp4', status='completed', video_task='task_done')
    item['scenes'][1].update(video_task='submission_unknown', status='needs_review', retry_count=5)
    item['scenes'][2].update(video_task='task_live', status='error', retry_count=5)
    scenes.save(item)
    gateway.DATA.mkdir(parents=True, exist_ok=True)
    (gateway.DATA / 'tasks.json').write_text(json.dumps([{'id':'task_live', 'status':'running'}]))
    await muse_queue.add(item['id'])
    with pytest.raises(ValueError):
        await muse_queue.requeue_failed()
    result = await muse_queue.requeue_failed(True)
    final = scenes.load(item['id'])
    assert result['requeued'] == 2
    assert final['scenes'][0]['video'] == 'existing.mp4'
    assert final['scenes'][0]['video_task'] == 'task_done'
    assert final['scenes'][1]['video_task'] is None
    assert final['scenes'][1]['previous_video_tasks'][0]['id'] == 'submission_unknown'
    assert final['scenes'][2]['video_task'] == 'task_live'
    assert final['scenes'][1]['retry_count'] == 0
    assert result['items'][0]['status'] == 'waiting'


async def test_start_explains_blocked_queue_instead_of_silently_finishing(state):
    from agent.services import muse_queue
    item = await make()
    for scene in item['scenes']:
        scene.update(status='needs_review', video_task='submission_unknown', retry_count=5)
    scenes.save(item)
    await muse_queue.add(item['id'])
    with pytest.raises(ValueError, match='Gửi lại cảnh lỗi'):
        await muse_queue.start()
    assert muse_queue._task is None


async def test_requeue_does_not_change_active_work(state):
    from agent.services import muse_queue
    item = await make()
    await muse_queue.add(item['id'])
    scenes._workers[item['id']] = object()
    with pytest.raises(ValueError):
        await muse_queue.requeue_failed(True)
    assert scenes.load(item['id'])['scenes'] == item['scenes']


async def test_slow_tail_does_not_block_next_project_and_stop_keeps_ids(state, monkeypatch):
    from agent.services import muse_queue
    first, second = await make(), await make()
    await muse_queue.add(first['id'])
    await muse_queue.add(second['id'])
    await install_media_fixtures(state, monkeypatch)
    original = scenes.wait_result
    gate = asyncio.Event()
    async def wait(ident, kind):
        if ident == 'task_0':
            await gate.wait()
        return await original(ident, kind)
    monkeypatch.setattr(scenes, 'wait_result', wait)
    await muse_queue.start()
    try:
        for _ in range(200):
            if all(scene.get('video') for scene in scenes.load(second['id'])['scenes']):
                break
            await asyncio.sleep(.01)
        assert all(scene.get('video') for scene in scenes.load(second['id'])['scenes'])
        assert not scenes.load(first['id'])['scenes'][0]['video']
        old_id = scenes.load(first['id'])['scenes'][0]['video_task']
    finally:
        await muse_queue.stop()
    assert scenes.load(first['id'])['scenes'][0]['video_task'] == old_id
    assert not scenes._workers and not muse_queue.status()['running']


async def test_multiple_projects_share_fifteen_slot_budget(state, monkeypatch):
    from agent.services import muse_queue
    for _ in range(6):
        item = await make()
        await muse_queue.add(item['id'])
    await install_media_fixtures(state, monkeypatch)
    calls = [0]
    async def wait(*args):
        calls[0] += 1
        await asyncio.Event().wait()
    monkeypatch.setattr(scenes, 'wait_result', wait)
    await muse_queue.start()
    try:
        for _ in range(500):
            if calls[0] >= 15:
                break
            await asyncio.sleep(.01)
        assert calls[0] == 15
        await asyncio.sleep(.25)
        assert calls[0] == 15
    finally:
        await muse_queue.stop()
    assert not scenes._workers


def test_prompt_filters_separate_errors_from_waiting(state):
    from agent.services import muse_queue
    from agent.services.speech_store import atomic_json
    item = {'id': str(uuid.uuid4()), 'title': 'Test', 'settings': {'count': 3}, 'status': 'draft',
            'scenes': [{'id': str(uuid.uuid4()), 'number': n, 'status': status, 'camera': 'static', 'video': None}
                       for n, status in enumerate(['pending', 'video', 'needs_review'], 1)]}
    scenes.save(item)
    scenes._workers[item['id']] = object()  # A real active project owns the processing phase.
    muse_queue.write({'running': False, 'items': [{'id': str(uuid.uuid4()), 'project_id': item['id'], 'status': 'waiting'}]})
    assert muse_queue.prompt_list(filter='waiting')['total'] == 1
    assert muse_queue.prompt_list(filter='processing')['total'] == 1
    assert muse_queue.prompt_list(filter='error')['items'][0]['ordinal'] == 3
    state = muse_queue.status()
    assert state['waiting'] == 1 and state['processing'] == 1 and state['blocked'] == 1


@pytest.mark.parametrize('project_status', ['running', 'paused', 'error'])
def test_restart_recovers_each_scene_phase_without_losing_submission_ids(state, project_status):
    from agent.services import muse_queue
    item = {'id': str(uuid.uuid4()), 'title': 'Restart', 'settings': {'count': 4}, 'status': project_status,
        'scenes': [{'id': str(uuid.uuid4()), 'number': n, 'status': phase, 'camera': 'static',
                    'video': None, 'video_task': f'task_{n}', 'video_request_key': f'key_{n}'}
                   for n, phase in enumerate(['video', 'image', 'running', 'error'], 1)]}
    scenes.save(item)
    muse_queue.write({'running': False, 'items': [{'id': str(uuid.uuid4()), 'project_id': item['id'], 'status': 'paused'}]})
    result = scenes.load(item['id'])
    assert [row['status'] for row in result['scenes']] == ['paused', 'paused', 'paused', 'error']
    assert [row['video_task'] for row in result['scenes']] == [f'task_{n}' for n in range(1, 5)]
    assert [row['video_request_key'] for row in result['scenes']] == [f'key_{n}' for n in range(1, 5)]
    assert muse_queue.status()['processing'] == 0
    assert muse_queue.status()['waiting'] == 3
    assert muse_queue.status()['blocked'] == 1
    assert muse_queue.prompt_list(filter='processing')['total'] == 0
    assert muse_queue.prompt_list(filter='waiting')['total'] == 3
