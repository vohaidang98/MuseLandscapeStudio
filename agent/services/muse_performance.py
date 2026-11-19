"""Persisted resource presets; changes apply only while production is stopped."""
from agent.services.speech_store import atomic_json, read_json

PRESETS = {
    'eco': {'label': 'Tiết kiệm', 'max_accounts': 2, 'videos_per_account': 1},
    'balanced': {'label': 'Cân bằng', 'max_accounts': 3, 'videos_per_account': 2},
    'fast': {'label': 'Nhanh', 'max_accounts': 5, 'videos_per_account': 3},
}


def current():
    from agent.services import muse_gateway
    saved = read_json(muse_gateway.ROOT / 'performance.json') or {}
    key = saved.get('preset', 'balanced')
    if key not in PRESETS:
        key = 'balanced'
    values = PRESETS[key]
    return {'preset': key, **values, 'max_videos': values['max_accounts'] * values['videos_per_account'],
            'poll_seconds': 5, 'automatic': bool(saved.get('automatic', True))}


async def save(preset, automatic=None):
    from agent.services import muse_gateway, muse_scenes, muse_queue, muse_tokens
    if preset not in PRESETS:
        raise ValueError('Chế độ hiệu năng không hợp lệ.')
    if muse_scenes._workers or muse_scenes._planning or muse_queue.read().get('running') or muse_tokens.status()['running']:
        raise ValueError('Dừng hàng đợi, viết prompt và kiểm tra token trước khi đổi hiệu năng.')
    if muse_gateway._services and muse_gateway._services.pool.stats().get('inflight', 0):
        raise ValueError('Muse vẫn còn tác vụ đang chạy. Chờ hoàn tất trước khi đổi hiệu năng.')
    auto = current()['automatic'] if automatic is None else bool(automatic)
    atomic_json(muse_gateway.ROOT / 'performance.json', {'preset': preset, 'automatic': auto})
    values = current()
    roles = muse_gateway._role_scheduler
    if roles:
        roles.max_accounts = values['max_accounts']
        roles.videos_per_account = values['videos_per_account']
        roles.selected = []
        roles.prompt_id = None
    if muse_gateway._services:
        muse_gateway._services.pool.max_concurrency = values['videos_per_account']
    if muse_gateway._driver:
        muse_gateway._driver.settings.account_max_concurrency = values['videos_per_account']
        governor = getattr(muse_gateway._driver, 'governor', None)
        if governor:
            governor.configure(values['max_videos'], values['automatic'])
    return values
