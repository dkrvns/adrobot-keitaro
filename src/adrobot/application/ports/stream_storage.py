from typing import Protocol

from adrobot.application.dto.stream import Snapshot


class SnapshotReader(Protocol):
    async def get(self, stream_id: int) -> Snapshot: ...
    async def for_campaign(self, campaign_id: int) -> dict[int, Snapshot]: ...


class SnapshotSaver(Protocol):
    async def save(self, snapshot: Snapshot) -> None: ...
