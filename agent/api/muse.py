"""Local-only Muse controls: credentials never leave this machine's gateway."""
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, SecretStr, field_validator

from agent.api.codex_auth import require_local
from agent.services import muse_gateway as muse

router = APIRouter(prefix='/api/muse', dependencies=[Depends(require_local)], tags=['muse'])


async def checked(call):
    try:
        return await call
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get('/status')
async def status():
    return await muse.status()


class Performance(BaseModel):
    preset: Literal['eco', 'balanced', 'fast']
    automatic: bool | None = None


@router.get('/performance')
async def performance():
    from agent.services.muse_performance import current
    return current()


@router.post('/performance')
async def set_performance(body: Performance):
    from agent.services.muse_performance import save
    return await checked(save(body.preset, body.automatic))


@router.post('/start')
async def start():
    return await checked(muse.start())


@router.post('/stop')
async def stop():
    await muse.shutdown()
    return await muse.status()


class Session(BaseModel):
    cookies: dict[str, SecretStr]
    consent: Literal[True]
    label: str = Field(default='FrameWeaver', min_length=1, max_length=80)


@router.post('/session')
async def session(body: Session):
    return await checked(muse.save_session({key: value.get_secret_value() for key, value in body.cookies.items()}, label=body.label.strip()))


class LoginStart(BaseModel):
    label: str = Field(default='FrameWeaver', min_length=1, max_length=80)


@router.post('/login/start')
async def start_login(body: LoginStart = LoginStart()):
    return await checked(muse.start_login(body.label))


@router.get('/accounts')
async def accounts():
    return await checked(muse.accounts())


@router.get('/accounts/tokens/status')
async def token_status():
    from agent.services import muse_tokens
    return muse_tokens.status()


@router.post('/accounts/tokens/refresh')
async def refresh_tokens():
    from agent.services import muse_tokens
    return await checked(muse_tokens.refresh())


@router.post('/accounts/{ident}/tokens/refresh')
async def refresh_account_tokens(ident: str):
    from agent.services import muse_tokens
    return await checked(muse_tokens.refresh(ident))


@router.post('/accounts/{ident}/delete')
async def account_delete(ident: str):
    return await checked(muse.delete_account(ident))


class AccountEnabled(BaseModel):
    enabled: bool


@router.post('/accounts/{ident}/enabled')
async def account_enabled(ident: str, body: AccountEnabled):
    return await checked(muse.enable_account(ident, body.enabled))


class LoginConsent(BaseModel):
    consent: Literal[True]


@router.post('/login/finish')
async def finish_login(body: LoginConsent):
    return await checked(muse.finish_login())


class Chat(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)


@router.post('/chat')
async def chat(body: Chat):
    return await checked(muse.chat(body.prompt))


class Generate(Chat):
    kind: Literal['image', 'video']
    size: Literal['16:9', '9:16', '1:1'] = '16:9'
    references: list[str] = Field(default_factory=list, max_length=4)

    @field_validator('references')
    @classmethod
    def local_images(cls, values):
        for value in values:
            if len(value) > 12 * 1024 * 1024 or not value.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')):
                raise ValueError('Chỉ chọn ảnh PNG, JPEG hoặc WebP dưới 9 MB.')
        return values


@router.post('/generate')
async def generate(body: Generate):
    return await checked(muse.generate(body.kind, body.prompt, body.size, body.references))


@router.get('/tasks')
async def tasks():
    return muse.history()


@router.get('/tasks/{ident}')
async def task(ident: str):
    return await checked(muse.task(ident))


@router.get('/media/{name}')
async def media(name: str):
    if Path(name).name != name or '/' in name or '\\' in name:
        raise HTTPException(404)
    root = (muse.DATA / 'media').resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.mp4', '.webm', '.mov', '.gif'}:
        raise HTTPException(404)
    return FileResponse(path)
