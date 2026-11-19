"""Independent send clocks for each Muse account."""
import asyncio
import random
import time


class AccountPacer:
    def __init__(self):
        self.locks = {}
        self.next_send = {}

    async def send(self, account_id, callback):
        async with self.locks.setdefault(account_id, asyncio.Lock()):
            await asyncio.sleep(max(0, self.next_send.get(account_id, 0) - time.monotonic()))
            try:
                return await callback()
            finally:
                self.next_send[account_id] = time.monotonic() + random.uniform(1, 2)
