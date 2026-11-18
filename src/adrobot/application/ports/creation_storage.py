from typing import Protocol
from uuid import UUID

from adrobot.application.dto.campaign import Creation


class CreationReader(Protocol):
    async def get(self, request_id: UUID) -> Creation: ...


class CreationSaver(Protocol):
    async def save(self, creation: Creation) -> None: ...
