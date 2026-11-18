from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from adrobot.application.commands.campaigns.create import CreateCampaignCommand
from adrobot.application.commands.streams.edit import (
    CancelDraftCommand,
    EditDraftCommand,
)
from adrobot.application.commands.streams.publish import PublishDraftCommand
from adrobot.application.commands.streams.sync import SyncCampaignCommand
from adrobot.application.interactors.campaigns.list_campaigns import (
    ListCampaignsInteractor,
)
from adrobot.application.ports.tracker import CatalogReader
from adrobot.config import Config
from adrobot.infrastructure.gateways.creation import CreationGateway
from adrobot.infrastructure.gateways.snapshot import SnapshotGateway
from adrobot.infrastructure.keitaro.client import KeitaroClient
from adrobot.infrastructure.operation_lock import LocalOperationLock


@dataclass(frozen=True, slots=True)
class Operations:
    catalog: CatalogReader
    list_campaigns: ListCampaignsInteractor
    create: CreateCampaignCommand
    sync: SyncCampaignCommand
    edit: EditDraftCommand
    cancel: CancelDraftCommand
    publish: PublishDraftCommand


@dataclass(frozen=True, slots=True)
class Resources:
    config: Config
    tracker: KeitaroClient
    sessions: async_sessionmaker[AsyncSession]
    locks: LocalOperationLock

    def operations(self, session: AsyncSession) -> Operations:
        tracker = self.tracker
        snapshots = SnapshotGateway(session)
        creations = CreationGateway(session)
        return Operations(
            catalog=tracker,
            list_campaigns=ListCampaignsInteractor(tracker),
            create=CreateCampaignCommand(
                tracker,
                tracker,
                tracker,
                tracker,
                tracker,
                creations,
                creations,
                session,
                self.locks,
                self.config.campaign_prefix,
            ),
            sync=SyncCampaignCommand(
                tracker,
                tracker,
                tracker,
                tracker,
                snapshots,
                snapshots,
                session,
                self.locks,
            ),
            edit=EditDraftCommand(snapshots, snapshots, session, self.locks, tracker),
            cancel=CancelDraftCommand(snapshots, snapshots, session, self.locks),
            publish=PublishDraftCommand(
                snapshots,
                snapshots,
                session,
                self.locks,
                tracker,
                tracker,
            ),
        )


async def operations(request: Request) -> AsyncIterator[Operations]:
    resources: Resources = request.app.state.resources
    async with resources.sessions() as session:
        yield resources.operations(session)
