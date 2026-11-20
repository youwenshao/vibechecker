import asyncio
import os
import sys
from collections.abc import Callable

import psutil
from vibechecker_engine.backends.memory import macos_footprint

GIB = 1024**3


def memory_available() -> bool:
    used = (
        macos_footprint(os.getpid())[0]
        if sys.platform == "darwin"
        else psutil.Process().memory_info().rss
    )
    return used < 18 * GIB and psutil.virtual_memory().available >= 2 * GIB


class Busy(Exception):
    pass


class Scheduler:
    def __init__(self, memory_ok: Callable[[], bool] = memory_available, wait_seconds: float = 2.5):
        self.slots = {"quick": asyncio.Semaphore(4), "deep": asyncio.Semaphore(1)}
        self.memory_ok = memory_ok
        self.wait_seconds = wait_seconds

    async def reserve(self, mode: str) -> asyncio.Semaphore:
        if not self.memory_ok():
            raise Busy
        slot = self.slots[mode]
        try:
            await asyncio.wait_for(slot.acquire(), self.wait_seconds)
        except TimeoutError as exc:
            raise Busy from exc
        if not self.memory_ok():
            slot.release()
            raise Busy
        return slot
