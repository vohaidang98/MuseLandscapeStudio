"""Bounded account scheduling with disjoint prompt and media roles."""
import asyncio
import time
from collections import Counter
from contextlib import asynccontextmanager
from contextvars import ContextVar

from muse2api.errors import NoAccountAvailable, UpstreamQuotaError
from muse2api.services.gateway import Gateway
from muse2api.services.request_log import note_account

_role = ContextVar('muse_account_role', default='prompt')


class AccountRoles:
    def __init__(self, pool, planning, max_accounts=5, videos_per_account=3, governor=None):
        self.governor = governor
        self.max_accounts = max_accounts
        self.videos_per_account = videos_per_account
        self.pool = pool
        self.planning = planning
        self.has_prompts = False
        self.prompt_id = None
        self.held = {}
        self.selected = []
        self.condition = asyncio.Condition()

    def phase(self):
        return 'warmup' if self.planning() and not self.has_prompts else 'mixed' if self.planning() else 'video'

    def prepare_plan(self, has_prompts):
        self.has_prompts = bool(has_prompts or any(x['role'] == 'video' for x in self.held.values()))
        if not self.has_prompts:
            self.prompt_id = None

    def prompts_ready(self):
        self.has_prompts = True

    def _preferred_prompt(self, available):
        must_drain_video = (len(self.held) >= self.max_accounts and all(x['role'] == 'video' for x in self.held.values()))
        if self.prompt_id not in {a.id for a in available} or (must_drain_video and self.prompt_id not in self.held):
            prompts = [a for a in available if self.held.get(a.id, {}).get('role') == 'prompt']
            idle = [a for a in available if a.id not in self.held]
            draining = [a for a in available if a.id in self.held] if must_drain_video else []
            # Reserving a currently busy video account drains its old work before
            # switching roles, rather than admitting a sixth account.
            choices = prompts or draining or idle or available
            self.prompt_id = min(choices, key=lambda a: a.last_used_at).id if choices else None
        return self.prompt_id

    def _choose(self, role, excluded):
        available = [a for a in self.pool.all() if a.is_available()]
        if not available:
            enabled = [a for a in self.pool.all() if a.enabled and a.status != 'invalid']
            if enabled and all(a.meta.get('quota_exhausted_until', 0) > time.time() for a in enabled):
                raise UpstreamQuotaError('all enabled accounts have exhausted quota')
            raise NoAccountAvailable('no usable account in pool')
        usable = {a.id for a in available}
        self.selected = [ident for ident in self.selected if ident in usable or ident in self.held]
        for account in available:
            if len(self.selected) >= self.max_accounts:
                break
            if account.id not in self.selected:
                self.selected.append(account.id)
        available = [account for account in available if account.id in self.selected]
        if not available:
            return None
        phase = self.phase()
        prompt = self._preferred_prompt(available) if phase == 'mixed' else None
        if self.governor:
            active_jobs = sum(value['count'] for value in self.held.values())
            limit = self.governor.limit()
            if active_jobs >= limit:
                return None
            if role == 'video' and phase == 'mixed':
                prompt_busy = any(value['role'] == 'prompt' for value in self.held.values())
                if not prompt_busy and active_jobs >= limit - 1:
                    return None  # Reserve room for the dedicated prompt account.
        candidates = []
        video_ids = {key for key, value in self.held.items() if value['role'] == 'video'}
        video_limit = min(self.max_accounts - 1, max(0, len(available) - 1)) if phase == 'mixed' else self.max_accounts
        for account in available:
            ident = account.id
            if ident in excluded:
                continue
            held = self.held.get(ident)
            if held and held['role'] != role:
                continue
            if not held and len(self.held) >= self.max_accounts:
                continue
            if role == 'prompt':
                if held and held['count'] >= 1:
                    continue
                if phase == 'mixed' and ident != prompt:
                    continue
            else:
                if phase == 'mixed' and ident == prompt:
                    continue
                if held and held['count'] >= self.videos_per_account:
                    continue
                if ident not in video_ids and len(video_ids) >= video_limit:
                    continue
            candidates.append(account)
        if not candidates:
            return None
        return min(candidates, key=lambda a: (self.held.get(a.id, {}).get('count', 0), a.last_used_at))

    @asynccontextmanager
    async def lease(self, role, exclude=(), hint=None):
        if role == 'video':
            self.prompts_ready()
        async with self.condition:
            while True:
                account = self._choose(role, set(exclude))
                if account:
                    record = self.held.setdefault(account.id, {'role': role, 'count': 0})
                    record['count'] += 1
                    break
                # Re-evaluate phase when the prompt planner finishes, even if no
                # media task released an account during that transition.
                try:
                    await asyncio.wait_for(self.condition.wait(), timeout=.5)
                except asyncio.TimeoutError:
                    pass
        try:
            others = [a.id for a in self.pool.all() if a.id != account.id]
            async with self.pool.lease(exclude=others, hint=hint) as lease:
                note_account(lease.account.id)
                yield lease
        finally:
            async with self.condition:
                record = self.held[account.id]
                record['count'] -= 1
                if not record['count']:
                    del self.held[account.id]
                self.condition.notify_all()

    def snapshot(self):
        counts = Counter(row['role'] for row in self.held.values())
        return {'mode': self.phase(), 'max_accounts': self.max_accounts, 'videos_per_account': self.videos_per_account, 'active_accounts': len(self.held),
                'prompt_accounts': counts['prompt'], 'video_accounts': counts['video'],
                'roles': {key: row['role'] for key, row in self.held.items()},
                'adaptive': self.governor.snapshot(sum(row['count'] for row in self.held.values())) if self.governor else None}


class RoleGateway(Gateway):
    def __init__(self, pool, driver, roles, **kwargs):
        super().__init__(pool, driver, **kwargs)
        self.roles = roles

    @asynccontextmanager
    async def _lease(self, exclude, hint):
        async with self.roles.lease(_role.get(), exclude, hint) as lease:
            yield lease

    async def _run(self, fn, hint=None):
        token = _role.set('video')
        try:
            return await super()._run(fn, hint)
        finally:
            _role.reset(token)
