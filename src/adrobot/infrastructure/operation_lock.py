import asyncio
from contextlib import AbstractAsyncContextManager

from adrobot.application.ports.transaction import OperationLock


class LocalOperationLock(OperationLock):
    def __init__(self) -> None:
        self._locks = tuple(asyncio.Lock() for _ in range(128))

    def acquire(self, key: int) -> AbstractAsyncContextManager[None]:
        return self._locks[key % len(self._locks)]
