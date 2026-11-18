from contextlib import AbstractAsyncContextManager
from typing import Protocol


class Committer(Protocol):
    async def commit(self) -> None: ...


class OperationLock(Protocol):
    def acquire(self, key: int) -> AbstractAsyncContextManager[None]: ...
