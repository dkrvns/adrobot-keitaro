import asyncio
from dataclasses import replace

from adrobot.application.commands.streams.offers import assignments, merge, signature
from adrobot.application.dto.campaign import Campaign
from adrobot.application.dto.stream import Snapshot, StreamView
from adrobot.application.errors import Missing, TrackerRejected, TrackerUnavailable
from adrobot.application.ports.stream_storage import SnapshotReader, SnapshotSaver
from adrobot.application.ports.tracker import (
    CampaignReader,
    CatalogReader,
    ClickReader,
    StreamReader,
)
from adrobot.application.ports.transaction import Committer, OperationLock


class SyncCampaignCommand:
    def __init__(
        self,
        campaigns: CampaignReader,
        streams: StreamReader,
        catalog: CatalogReader,
        clicks: ClickReader,
        reader: SnapshotReader,
        saver: SnapshotSaver,
        committer: Committer,
        locks: OperationLock,
    ) -> None:
        self._campaigns = campaigns
        self._streams = streams
        self._catalog = catalog
        self._clicks = clicks
        self._reader = reader
        self._saver = saver
        self._committer = committer
        self._locks = locks

    async def __call__(
        self,
        campaign_id: int,
    ) -> tuple[Campaign, tuple[StreamView, ...]]:
        async with self._locks.acquire(campaign_id):
            campaign = await self._campaigns.campaign(campaign_id)
            if campaign.id is None:
                raise Missing('Campaign was not found.')
            streams, offers, clicks = await asyncio.gather(
                self._streams.streams(campaign_id),
                self._catalog.offers(),
                self._today(campaign_id),
            )
            names = {offer.id: offer.name for offer in offers}
            saved = await self._reader.for_campaign(campaign_id)
            views = []
            for stream in streams:
                if stream.id is None:
                    continue
                previous = saved.get(stream.id)
                if previous is None:
                    previous = Snapshot(stream.id, campaign_id)
                committed = merge(previous.committed, stream.offers, names)
                draft = previous.draft
                # Keep the draft baseline for publish conflict detection.
                if draft is not None:
                    committed = previous.committed
                    if assignments(draft) == signature(stream.offers):
                        committed = merge(draft, stream.offers, names)
                        draft = None
                updated = replace(
                    previous,
                    committed=committed,
                    draft=draft,
                    editable=stream.schema == 'landings',
                )
                if updated != previous or stream.id not in saved:
                    updated = replace(updated, revision=previous.revision + 1)
                    await self._saver.save(updated)
                views.append(
                    StreamView(
                        stream,
                        updated,
                        clicks.get(stream.id, 0) if clicks is not None else None,
                    )
                )
            await self._committer.commit()
        return campaign, tuple(views)

    async def _today(self, campaign_id: int) -> dict[int, int] | None:
        try:
            return await self._clicks.stream_clicks_today(campaign_id)
        except TrackerUnavailable, TrackerRejected:
            return None
