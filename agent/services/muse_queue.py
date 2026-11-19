"""Persistent project queue. Adding prompts never starts media generation."""
import asyncio
import uuid

from agent.services import muse_scenes as scenes
from agent.services.speech_store import atomic_json, read_json

_task = None
_lock = asyncio.Lock()


def read():
    state = read_json(scenes.ROOT / 'production-queue.json') or {'items': [], 'running': False}
    if state['running'] and (_task is None or _task.done()):
        state['running'] = False
        for row in state['items']:
            if row['status'] == 'running':
                row['status'] = 'paused'
        write(state)
    return state


def write(state):
    atomic_json(scenes.ROOT / 'production-queue.json', state)


def status():
    state = read()
    rows = []
    for row in state['items']:
        row = dict(row)
        try:
            project = scenes.load(row['project_id'])
            row.update(title=project['title'], count=len(project['scenes']), target=project['settings']['count'],
                       videos=sum(bool(scene.get('video')) for scene in project['scenes']))
            row['processing'] = sum(not scene.get('video') and scene.get('status') in {'video', 'image', 'running'} for scene in project['scenes'])
            row['waiting'] = sum(not scene.get('video') and scene.get('status') not in {'error', 'needs_review', 'video', 'image', 'running'} for scene in project['scenes'])
            row['needs_review'] = sum(scene.get('status') == 'needs_review' for scene in project['scenes'])
            row['blocked'] = sum(not scene.get('video') and scene.get('status') in {'error', 'needs_review'} for scene in project['scenes'])
            row['quota_exhausted'] = bool(row.get('quota_exhausted') or project.get('quota_exhausted'))
            if row['quota_exhausted']:
                row['error'] = 'Tài khoản Muse hết hạn mức — đã dừng hàng đợi.'
        except ValueError:
            row.update(title='Không tìm thấy bộ cảnh', count=0, videos=0)
        rows.append(row)
    return {**state, 'items': rows, 'total_prompts': sum(row['count'] for row in rows),
            'processing': sum(row.get('processing', 0) for row in rows),
            'waiting': sum(row.get('waiting', 0) for row in rows),
            'blocked': sum(row.get('blocked', 0) for row in rows)}


def prompt_list(page=1, limit=20, filter="all"):
    rows, missing = [], []
    cameras = {row['id']: row['label'] for row in scenes.camera_options()}
    for batch in read()['items']:
        try:
            project = scenes.load(batch['project_id'])
        except ValueError:
            missing.append(batch['id'])
            continue
        for scene in project['scenes']:
            key = scene.get('camera', '')
            camera = 'Theo prompt TXT' if project.get('source') == 'txt' else cameras.get(key, scenes.CAMERAS.get(key, ('Góc đã lưu',))[0])
            quota = bool(batch.get('quota_exhausted') or project.get('quota_exhausted'))
            rows.append({**{key: scene.get(key) for key in ('id', 'number', 'title', 'image_prompt', 'video_prompt',
                'status', 'error', 'video', 'retry_count')}, 'project_id': project['id'], 'queue_id': batch['id'],
                'camera_label': camera, 'quota_exhausted': quota, 'ordinal': len(rows) + 1})
    if filter != 'all':
        groups = {'waiting': {'pending', 'draft', 'paused'}, 'processing': {'video', 'image', 'running'},
                  'error': {'error', 'needs_review'}, 'completed': {'completed'}}
        rows = [row for row in rows if row.get('status') in groups.get(filter, set())]
    pages = max(1, (len(rows) + limit - 1) // limit)
    page = min(max(1, page), pages)
    return {'items': rows[(page - 1) * limit:page * limit], 'page': page, 'pages': pages,
            'total': len(rows), 'missing': missing}


async def add(project_id):
    async with _lock:
        project = scenes.load(project_id)
        if not project['scenes']:
            raise ValueError('Chưa có prompt hoàn thành để thêm vào hàng đợi.')
        scenes.gateway.prompts_ready()
        state = read()
        if not any(row['project_id'] == project_id for row in state['items']):
            state['items'].append({'id': str(uuid.uuid4()), 'project_id': project_id, 'status': 'waiting'})
            write(state)
        else:
            row = next(row for row in state['items'] if row['project_id'] == project_id)
            if row['status'] == 'completed' and any(not scene.get('video') for scene in project['scenes']):
                row['status'] = 'waiting'
                write(state)
        return status()


async def import_prompts(text, filename='prompts.txt', size='16:9'):
    """Append a validated text file without AI rewriting or starting production."""
    if size not in {'16:9', '9:16', '1:1'}:
        raise ValueError('Tỉ lệ khung hình không hợp lệ.')
    if len(text) > 10_000_000 or '\x00' in text:
        raise ValueError('File TXT quá lớn hoặc không phải văn bản hợp lệ.')
    lines = [(number, line.strip()) for number, line in enumerate(text.lstrip('\ufeff').splitlines(), 1) if line.strip()]
    if not lines:
        raise ValueError('File TXT không có prompt. Mỗi dòng không trống là một prompt.')
    if len(lines) > 9999:
        raise ValueError('Mỗi file được nhập tối đa 9.999 prompt.')
    for number, line in lines:
        if len(line) > 6000:
            raise ValueError(f'Dòng {number} quá dài (tối đa 6.000 ký tự). Chưa nhập prompt nào.')
    settings = scenes.Settings(topic='Prompt từ TXT', count=len(lines), cameras=['txt'], size=size,
        custom_cameras={'txt': 'Theo nội dung prompt TXT'})
    item = {'id': str(uuid.uuid4()), 'title': filename[:100] or 'Prompt từ TXT', 'source': 'txt',
        'settings': settings.model_dump(), 'status': 'draft', 'message': f'Đã nhập {len(lines)} prompt từ TXT.',
        'export_root': str(scenes.output_directory()), 'deduplication': {'enabled': False},
        'scenes': [{'id': str(uuid.uuid4()), 'number': index, 'title': f'Prompt {index}',
            'image_prompt': line, 'video_prompt': 'Theo nội dung prompt TXT', 'camera': 'txt',
            'image_task': None, 'video_task': None, 'image': None, 'video': None,
            'status': 'pending', 'error': None} for index, (_, line) in enumerate(lines, 1)]}
    scenes.save(item)
    await add(item['id'])
    return {'queue': status(), 'imported': len(lines), 'project_id': item['id']}


async def remove(ident):
    async with _lock:
        state = read()
        row = next((row for row in state['items'] if row['id'] == ident), None)
        if state.get('running'):
            raise ValueError('Dừng hàng đợi trước khi bỏ bộ đang chạy.')
        state['items'] = [row for row in state['items'] if row['id'] != ident]
        write(state)
        return status()


async def clear():
    global _auto_blocked
    async with _lock:
        if (_task and not _task.done()) or scenes._workers or scenes._planning:
            raise ValueError('Dừng tạo prompt và hàng đợi trước khi dọn prompt.')
        state = read()
        for row in state['items']:
            try:
                project = scenes.load(row['project_id'])
            except ValueError:
                continue
            project['partial_queue_recovered'] = True
            scenes.save(project)
        _auto_blocked = True
        write({'items': [], 'running': False})
        return status()


async def requeue_failed(confirm_resubmit=False):
    if not confirm_resubmit:
        raise ValueError('Cần xác nhận gửi lại vì yêu cầu cũ có thể đã được Muse nhận.')
    async with _lock:
        if (_task and not _task.done()) or scenes._workers or scenes._planning:
            raise ValueError('Dừng hàng đợi và tạo prompt trước khi gửi lại cảnh lỗi.')
        state = read()
        stored = {row['id']: row for row in (read_json(scenes.gateway.DATA / 'tasks.json') or [])}
        changed = 0
        for row in state['items']:
            try:
                project = scenes.load(row['project_id'])
            except ValueError:
                continue
            count = 0
            for scene in project['scenes']:
                if scene.get('video') or scene.get('status') not in {'error', 'needs_review'}:
                    continue
                old = scene.get('video_task')
                task = stored.get(old)
                # Keep known live/successful task IDs; only a confirmed failed,
                # missing or explicitly accepted uncertain submission gets a new key.
                if task and task.get('status') in {'queued', 'running', 'succeeded'}:
                    scene.update(status='pending', retry_count=0, error=None)
                else:
                    scene.setdefault('previous_video_tasks', []).append({'id': old, 'request_key': scene.get('video_request_key')})
                    scene.update(video_task=None, status='pending', retry_count=0, error=None)
                    scene.pop('video_request_key', None)
                count += 1
            if count:
                project.update(status='draft', message=f'Đã chuẩn bị gửi lại {count} cảnh lỗi; giữ nguyên video hoàn thành.', quota_exhausted=False)
                scenes.save(project)
                row.update(status='waiting', error=None, quota_exhausted=False)
                changed += count
        write(state)
        return {**status(), 'requeued': changed}


async def recover_stopped_plans():
    # Older builds saved partial projects but never put them into this queue.
    for file in (scenes.ROOT / 'planning-jobs').glob('*.json'):
        job = read_json(file) or {}
        if job.get('status') not in {'stopped', 'error', 'running'} or not job.get('project_id'):
            continue
        try:
            project = scenes.load(job['project_id'])
        except ValueError:
            continue
        if project.get('partial_queue_recovered') or not 0 < len(project['scenes']) < project['settings']['count']:
            continue
        await add(project['id'])
        project['partial_queue_recovered'] = True
        scenes.save(project)


_auto_blocked = False


def allow_auto_run():
    global _auto_blocked
    _auto_blocked = False


async def auto_start():
    if not _auto_blocked and (_task is None or _task.done()) and not scenes._workers:
        await start()


async def start():
    global _task, _auto_blocked
    async with _lock:
        if _task and not _task.done():
            raise ValueError('Hàng đợi đang chạy.')
        if scenes._workers:
            raise ValueError('Dừng tác vụ hiện tại trước khi chạy hàng đợi.')
        state = read()
        if not any(row['status'] != 'completed' for row in state['items']):
            raise ValueError('Chưa có bộ cảnh chờ tạo video.')
        runnable = False
        for row in state['items']:
            try:
                project = scenes.load(row['project_id'])
            except ValueError:
                continue
            if any(not scene.get('video') and scene.get('status') != 'needs_review'
                   and not (scene.get('status') == 'error' and scene.get('retry_count', 0) >= 5)
                   for scene in project['scenes']):
                runnable = True
        if not runnable and not scenes._planning:
            raise ValueError('Các cảnh còn lại đang bị chặn hoặc hết số lần thử. Bấm Gửi lại cảnh lỗi để xác nhận chạy tiếp; video hoàn thành được giữ nguyên.')
        from agent.services import muse_tokens
        await muse_tokens.shutdown()
        await scenes.gateway.require_ready()
        _auto_blocked = False
        state['running'] = True
        write(state)

        async def run():
            global _auto_blocked
            active = {}
            from agent.services.muse_performance import current as performance
            slots = asyncio.Semaphore(performance()['max_videos'])
            async def execute(row, retry):
                global _auto_blocked
                ident = row['id']
                current = row['project_id']
                state = read()
                row = next(row for row in state['items'] if row['id'] == ident)
                row.update(status='running', error=None, quota_exhausted=False)
                write(state)
                quota = False
                try:
                    await scenes.start(current, 'videos', retry_errors=retry, retry_only=retry, queue_slots=slots)
                    worker = scenes._workers.get(current)
                    if worker:
                        await worker
                    project = scenes.load(current)
                    quota = bool(project.get('quota_exhausted'))
                    if quota:
                        result, error = 'error', project['message']
                    elif all(scene.get('video') for scene in project['scenes']):
                        result, error = 'completed', None
                    elif project['status'] in {'error', 'paused'}:
                        result, error = project['status'], project.get('message')
                    else:
                        result, error = 'waiting', None
                except scenes.gateway.QuotaExhausted as exc:
                    result, error, quota = 'error', str(exc), True
                except Exception as exc:
                    result, error = 'error', str(exc) if isinstance(exc, ValueError) else 'Không chạy được bộ cảnh. Kiểm tra nhật ký.'
                state = read()
                row = next(row for row in state['items'] if row['id'] == ident)
                row.update(status=result, error=error, quota_exhausted=quota)
                write(state)
                if quota:
                    _auto_blocked = True
                return quota or result == 'paused'
            try:
                while True:
                    for ident, task in list(active.items()):
                        if task.done():
                            del active[ident]
                            if task.result():
                                return
                    ready = None
                    for row in read()['items']:
                        if row['id'] in active or row.get('quota_exhausted'):
                            continue
                        try:
                            project = scenes.load(row['project_id'])
                        except ValueError:
                            continue
                        if any(not scene.get('video') and scene.get('status') not in {'error', 'needs_review'} for scene in project['scenes']):
                            ready = row
                            break
                    # At most fifteen project controllers share one 15-slot budget.
                    # A slow tail in one project leaves free slots to later projects.
                    if ready and len(active) < 15:
                        active[ready['id']] = asyncio.create_task(execute(ready, False))
                    elif not active and not scenes._planning:
                        break
                    if active:
                        await asyncio.wait(list(active.values()), timeout=.5, return_when=asyncio.FIRST_COMPLETED)
                    else:
                        await asyncio.sleep(.5)
                for row in list(read()['items']):
                    try:
                        scenes.load(row['project_id'])
                    except ValueError:
                        continue
                    if row['status'] == 'error' and await execute(row, True):
                        return
            finally:
                for task in active.values():
                    task.cancel()
                await asyncio.gather(*active.values(), return_exceptions=True)
                # Cancelling an execute task propagates to its project worker.
                for row in read()['items']:
                    if row['project_id'] in scenes._workers:
                        await scenes.stop(row['project_id'])
                state = read()
                state['running'] = False
                for row in state['items']:
                    if row['status'] == 'running':
                        row['status'] = 'paused'
                write(state)
        _task = asyncio.create_task(run())
        return status()


async def stop():
    global _task, _auto_blocked
    _auto_blocked = True
    if _task and not _task.done():
        _task.cancel()
        await asyncio.gather(_task, return_exceptions=True)
    _task = None
    return status()
