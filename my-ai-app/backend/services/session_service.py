"""Serialize chat and memory edits per user in this local, single-worker app."""
import asyncio
from weakref import WeakValueDictionary

_locks = WeakValueDictionary()


def user_lock(user_id: str) -> asyncio.Lock:
    lock = _locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[user_id] = lock
    return lock
