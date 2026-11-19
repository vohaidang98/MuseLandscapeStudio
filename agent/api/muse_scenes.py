import tempfile
import json
from uuid import UUID
from zipfile import ZipFile, ZIP_STORED

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from pydantic import Field
from typing import Literal
from starlette.background import BackgroundTask
from pathlib import Path
import os

from agent.api.codex_auth import require_local
from agent.api.muse import checked
from agent.services import muse_scenes as scenes
from agent.services import muse_queue

router = APIRouter(prefix='/api/muse/scenes', dependencies=[Depends(require_local)])


@router.get('/queue')
async def queue_status():
    return muse_queue.status()


@router.get('/queue/prompts')
async def queue_prompts(page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1, le=100), filter: Literal["all", "waiting", "processing", "error", "completed"] = "all"):
    return muse_queue.prompt_list(page, limit, filter)


class QueueProject(BaseModel):
    project: UUID


class TextPrompts(BaseModel):
    text: str = Field(max_length=10_000_000)
    filename: str = Field(default='prompts.txt', max_length=255)
    size: Literal['16:9', '9:16', '1:1'] = '16:9'


@router.post('/queue/import-txt')
async def import_text_prompts(body: TextPrompts):
    return await checked(muse_queue.import_prompts(body.text, body.filename, body.size))


@router.post('/queue/add')
async def queue_add(body: QueueProject):
    return await checked(muse_queue.add(str(body.project)))


@router.post('/queue/start')
async def queue_start():
    return await checked(muse_queue.start())


@router.post('/queue/stop')
async def queue_stop():
    return await checked(muse_queue.stop())


class RequeueFailed(BaseModel):
    confirm_resubmit: bool = False


@router.post('/queue/requeue-failed')
async def queue_requeue_failed(body: RequeueFailed):
    return await checked(muse_queue.requeue_failed(body.confirm_resubmit))


@router.post('/queue/clear')
async def queue_clear():
    return await checked(muse_queue.clear())


@router.post('/queue/{ident}/remove')
async def queue_remove(ident: UUID):
    return await checked(muse_queue.remove(str(ident)))


@router.get('/options')
async def options():
    return {'cameras': scenes.camera_options(), 'landscapes': scenes.landscape_options()}


class Camera(BaseModel):
    label: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=5, max_length=1000)


class Landscape(BaseModel):
    label: str = Field(min_length=2, max_length=100)
    description: str = Field(default='', max_length=3000)


@router.post('/landscapes')
async def add_landscape(body: Landscape):
    return await checked(scenes.add_landscape(body.label, body.description))


@router.post('/cameras')
async def add_camera(body: Camera):
    return await checked(scenes.add_camera(body.label, body.description))


class DeleteCameras(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=30)


@router.post('/cameras/delete')
async def delete_cameras(body: DeleteCameras):
    return {'cameras': await checked(scenes.delete_cameras(body.ids))}


@router.get('')
async def listing():
    return scenes.listing()


@router.get('/storage')
async def storage():
    return {'directory': str(scenes.output_directory())}


class Storage(BaseModel):
    directory: str = Field(min_length=1, max_length=2000)
    project: UUID | None = None


@router.post('/storage')
async def save_storage(body: Storage):
    return await checked(scenes.set_output_directory(body.directory, str(body.project) if body.project else None))


@router.post('/storage/choose')
async def choose_storage():
    from agent.services.muse_folder_picker import choose
    directory = await checked(choose(scenes.output_directory()))
    return {'directory': directory or None}


@router.post('/storage/open')
async def open_storage(project: UUID | None = None):
    try:
        item = scenes.load(str(project)) if project else None
        directory = scenes.output_directory(item)
        directory.mkdir(parents=True, exist_ok=True)
        os.startfile(str(directory))
        return {'opened': True, 'directory': str(directory)}
    except (ValueError, OSError):
        raise HTTPException(409, 'Không mở được thư mục. Sao chép đường dẫn hiển thị và mở bằng File Explorer.') from None


@router.post('/plan')
async def plan(body: scenes.Settings):
    return await checked(scenes.plan(body))


@router.post('/plan/start')
async def begin_plan(body: scenes.Settings, enqueue: bool = False, auto_run: bool = False):
    return await checked(scenes.begin_plan(body, enqueue=enqueue, auto_run=auto_run))


@router.get('/planning/{ident}')
async def planning_status(ident: UUID):
    try:
        return scenes.planning_status(str(ident))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None


@router.post('/planning/{ident}/stop')
async def stop_plan(ident: UUID):
    return await checked(scenes.stop_plan(str(ident)))


@router.get('/{ident}')
async def get(ident: UUID):
    try:
        return scenes.load(str(ident))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None


@router.post('/{ident}/plan/resume')
async def resume_plan(ident: UUID):
    try:
        item = scenes.load(str(ident))
        return await checked(scenes.begin_plan(scenes.Settings(**item['settings']), str(ident)))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


class Edits(BaseModel):
    scenes: list[scenes.SceneEdit]


@router.post('/{ident}/deduplicate')
async def deduplicate(ident: UUID, body: Edits):
    return await checked(scenes.repair_project(str(ident), body.scenes))


@router.put('/{ident}')
async def edit(ident: UUID, body: Edits):
    return await checked(scenes.edit(str(ident), body.scenes))


class Run(BaseModel):
    output: Literal['images', 'videos']


@router.post('/{ident}/run')
async def run(ident: UUID, body: Run):
    return await checked(scenes.start(str(ident), body.output))


@router.post('/{ident}/pause')
async def pause(ident: UUID):
    return await scenes.pause(str(ident))


@router.post('/{ident}/stop')
async def stop(ident: UUID):
    return await checked(scenes.stop(str(ident)))


@router.post('/{ident}/retry')
async def retry(ident: UUID):
    return await checked(scenes.retry_failed(str(ident)))


@router.get('/{ident}/download')
async def download(ident: UUID):
    file_path = None
    try:
        item = scenes.load(str(ident))
        scenes.ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=scenes.ROOT, prefix='download-', suffix='.zip', delete=False) as temporary:
            file_path = Path(temporary.name)
        with ZipFile(file_path, 'w', ZIP_STORED) as archive:
            archive.writestr('scenes.json', json.dumps(item, ensure_ascii=False, indent=2))
            for scene in item['scenes']:
                for kind in ('image', 'video'):
                    if scene.get(kind):
                        file = scenes.media_file(scene[kind])
                        archive.write(file, f"scene-{scene['number']:02d}-{kind}{file.suffix}")
        return FileResponse(file_path, media_type='application/zip', filename='muse-scenes.zip',
            background=BackgroundTask(file_path.unlink, missing_ok=True))
    except ValueError as exc:
        if file_path:
            file_path.unlink(missing_ok=True)
        raise HTTPException(404, str(exc)) from None
