import re
from dataclasses import replace
from uuid import UUID

from adrobot.application.dto.campaign import Campaign, Creation, NewCampaign
from adrobot.application.errors import Conflict, Invalid, TrackerUnavailable
from adrobot.application.ports.creation_storage import CreationReader, CreationSaver
from adrobot.application.ports.tracker import (
    CampaignReader,
    CampaignWriter,
    CatalogReader,
    StreamReader,
    StreamWriter,
)
from adrobot.application.ports.transaction import Committer, OperationLock


class CreateCampaignCommand:
    def __init__(
        self,
        reader: CampaignReader,
        writer: CampaignWriter,
        streams: StreamReader,
        stream_writer: StreamWriter,
        catalog: CatalogReader,
        requests: CreationReader,
        saver: CreationSaver,
        committer: Committer,
        locks: OperationLock,
        prefix: str,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._streams = streams
        self._stream_writer = stream_writer
        self._catalog = catalog
        self._requests = requests
        self._saver = saver
        self._committer = committer
        self._locks = locks
        self._prefix = prefix

    async def __call__(self, request_id: UUID, data: NewCampaign) -> Campaign:
        name = data.name
        if not name.startswith(self._prefix):
            name = f'{self._prefix}{name}'
        data = replace(data, name=name)
        slug = re.sub(r'[^a-z0-9_]+', '-', name.lower()).strip('-')[:17]
        alias = f'{slug}-{request_id.hex}'

        async with self._locks.acquire(request_id.int):
            creation = await self._requests.get(request_id)
            is_new = creation.request_id is None
            if is_new:
                creation = Creation(request_id, data)
                await self._store(creation)
            else:
                await self._committer.commit()
                if creation.input != data:
                    raise Conflict(
                        'Creation key was already used for different inputs.'
                    )

            if creation.campaign_id is None:
                campaign = (
                    Campaign() if is_new else await self._find_by_alias(name, alias)
                )
                if campaign.id is None:
                    await self._validate_catalog(data)
                    campaign = await self._writer.create_campaign(data, alias)
                creation = replace(creation, campaign_id=campaign.id)
                await self._store(creation)
            else:
                campaign = await self._reader.campaign(creation.campaign_id)

            campaign_id = campaign.id
            if campaign_id is None:
                raise Conflict('The campaign was removed in Keitaro.')
            if creation.completed:
                return campaign

            streams = await self._streams.streams(campaign_id)
            if not any(
                item.position == 1 and item.schema == 'redirect' for item in streams
            ):
                await self._stream_writer.create_geo_stream(campaign_id, data.country)
            if not any(
                item.position == 2 and item.schema == 'landings' for item in streams
            ):
                await self._stream_writer.create_offer_stream(
                    campaign_id,
                    data.offer_id,
                )
            if campaign.state != 'active':
                campaign = await self._writer.enable_campaign(campaign_id)
                if campaign.state != 'active':
                    raise TrackerUnavailable('Keitaro did not activate the campaign.')
            await self._store(replace(creation, completed=True))
            return campaign

    async def _find_by_alias(self, name: str, alias: str) -> Campaign:
        limit = 100
        offset = 0
        while True:
            matches = await self._reader.campaigns(offset, limit, name)
            for campaign in matches:
                if campaign.alias == alias:
                    return campaign
            if len(matches) < limit:
                return Campaign()
            offset += limit

    async def _store(self, creation: Creation) -> None:
        await self._saver.save(creation)
        await self._committer.commit()

    async def _validate_catalog(self, data: NewCampaign) -> None:
        catalog = await self._catalog.catalog()
        for value, options, label in (
            (data.domain_id, catalog.domains, 'Domain'),
            (data.group_id, catalog.groups, 'Campaign group'),
            (data.traffic_source_id, catalog.sources, 'Traffic source'),
        ):
            if all(value != option.id for option in options):
                raise Invalid(f'{label} is unavailable.')
        if await self._catalog.offer(data.offer_id) is None:
            raise Invalid('Offer is unavailable.')
