"""Close unused Muse tabs while preserving busy requests and shared Chrome."""
import asyncio
import contextlib
import time


class IdleBrowserMixin:
    idle_seconds = 30

    async def _checkin(self, tab):
        tab.muse_idle_since = time.monotonic()
        await super()._checkin(tab)

    async def close_idle_tabs(self, now=None):
        now = time.monotonic() if now is None else now
        pool = getattr(self, 'muse_pool', None)
        selected = set(getattr(getattr(self, 'muse_roles', None), 'selected', []))
        governor = getattr(self, 'governor', None)
        idle_seconds = 5 if governor and governor.limit() < governor.ceiling else self.idle_seconds
        closing = []
        async with self._tab_cond:
            for ident, tabs in list(self._tabs.items()):
                if ident in getattr(self, 'muse_token_pending', set()):
                    continue
                if self._opening.get(ident, 0):
                    continue
                account = pool.get(ident) if pool else None
                retired = pool is not None and (account is None or not account.is_available() or ident not in selected)
                for tab in list(tabs):
                    if tab.closed or tab.busy:
                        continue
                    since = getattr(tab, 'muse_idle_since', None)
                    if since is None:
                        tab.muse_idle_since = now
                        since = now
                    if retired or now - since >= idle_seconds:
                        # Reserve before releasing the condition so checkout
                        # cannot pick a tab halfway through disposal.
                        tab.busy = True
                        closing.append(tab)
        for tab in closing:
            try:
                await asyncio.wait_for(self._close_tab(tab), timeout=5)
            except Exception:
                # Mark unusable; a later checkout must create a fresh tab.
                tab.stale = True
                tab.busy = False
        return len(closing)

    async def startup(self):
        await super().startup()
        task = getattr(self, '_idle_cleanup_task', None)
        if task is None or task.done():
            async def maintain():
                while True:
                    await asyncio.sleep(5)
                    with contextlib.suppress(Exception):
                        from agent.services import muse_tokens
                        await muse_tokens.refresh_quota_idle(self)
                    with contextlib.suppress(Exception):
                        await self.close_idle_tabs()
            self._idle_cleanup_task = asyncio.create_task(maintain())

    async def shutdown(self):
        task = getattr(self, '_idle_cleanup_task', None)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await super().shutdown()
