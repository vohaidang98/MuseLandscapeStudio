"""Muse-only application: no Google Flow, extension bridge, or legacy Studio."""
from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI
from agent.api.muse import router
from agent.api.muse_scenes import router as scenes_router
from agent.services import muse_gateway, muse_scenes, muse_queue, muse_tokens


async def shutdown_services(app):
    async with app.state.shutdown_lock:
        if app.state.services_stopped:
            return
        connection = app.state.connection_task
        connection.cancel()
        for operation in (lambda: asyncio.gather(connection, return_exceptions=True),
                          muse_queue.stop, muse_scenes.shutdown, muse_tokens.shutdown):
            try:
                await asyncio.wait_for(operation(), timeout=3)
            except (Exception, asyncio.CancelledError):
                pass
        from agent.services.muse_browser_cleanup import close_owned_chrome
        await asyncio.to_thread(close_owned_chrome, muse_gateway.ROOT)
        try:
            await asyncio.wait_for(muse_gateway.shutdown(), timeout=5)
        except (Exception, asyncio.CancelledError):
            pass
        app.state.services_stopped = True


@asynccontextmanager
async def lifespan(app):
    app.state.event_loop = asyncio.get_running_loop()
    app.state.shutdown_lock = asyncio.Lock()
    app.state.services_stopped = False
    await muse_queue.recover_stopped_plans()
    connection = asyncio.create_task(muse_gateway.auto_start_saved())
    app.state.connection_task = connection
    yield
    await shutdown_services(app)


app = FastAPI(title='Muse Landscape Studio', lifespan=lifespan)
app.include_router(scenes_router)
app.include_router(router)


@app.get('/health')
async def health():
    return {'status': 'ok', 'application': 'Muse Landscape Studio', 'version': '1.2.3'}




