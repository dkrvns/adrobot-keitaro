from dataclasses import asdict
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from adrobot.application.dto.campaign import Creation, NewCampaign
from adrobot.application.ports.creation_storage import CreationReader, CreationSaver
from adrobot.infrastructure.db.models import CreationModel

campaign_input = TypeAdapter(NewCampaign)


class CreationGateway(CreationReader, CreationSaver):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, request_id: UUID) -> Creation:
        row = await self._session.get(CreationModel, request_id)
        if row is None:
            return Creation()
        return Creation(
            row.request_id,
            campaign_input.validate_python(row.input),
            row.campaign_id,
            row.completed,
        )

    async def save(self, creation: Creation) -> None:
        if creation.input is None:
            raise ValueError('Creation input is required.')
        statement = insert(CreationModel).values(
            request_id=creation.request_id,
            input=asdict(creation.input),
            campaign_id=creation.campaign_id,
            completed=creation.completed,
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[CreationModel.request_id],
                set_={
                    'campaign_id': creation.campaign_id,
                    'completed': creation.completed,
                },
            )
        )
