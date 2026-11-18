from dataclasses import asdict

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from adrobot.application.dto.stream import OfferEntry, Snapshot
from adrobot.application.ports.stream_storage import SnapshotReader, SnapshotSaver
from adrobot.infrastructure.db.models import StreamSnapshotModel

entries = TypeAdapter(tuple[OfferEntry, ...])


class SnapshotGateway(SnapshotReader, SnapshotSaver):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, stream_id: int) -> Snapshot:
        row = await self._session.get(StreamSnapshotModel, stream_id)
        if row is None:
            return Snapshot()
        return self._to_dto(row)

    async def for_campaign(self, campaign_id: int) -> dict[int, Snapshot]:
        rows = await self._session.scalars(
            select(StreamSnapshotModel).where(
                StreamSnapshotModel.campaign_id == campaign_id,
            )
        )
        return {row.stream_id: self._to_dto(row) for row in rows}

    async def save(self, snapshot: Snapshot) -> None:
        values = {
            'campaign_id': snapshot.campaign_id,
            'revision': snapshot.revision,
            'editable': snapshot.editable,
            'committed': [asdict(row) for row in snapshot.committed],
            'draft': (
                None
                if snapshot.draft is None
                else [asdict(row) for row in snapshot.draft]
            ),
        }
        statement = insert(StreamSnapshotModel).values(
            stream_id=snapshot.stream_id,
            **values,
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[StreamSnapshotModel.stream_id],
                set_=values,
            )
        )

    @staticmethod
    def _to_dto(row: StreamSnapshotModel) -> Snapshot:
        return Snapshot(
            stream_id=row.stream_id,
            campaign_id=row.campaign_id,
            revision=row.revision,
            editable=row.editable,
            committed=entries.validate_python(row.committed),
            draft=None if row.draft is None else entries.validate_python(row.draft),
        )
