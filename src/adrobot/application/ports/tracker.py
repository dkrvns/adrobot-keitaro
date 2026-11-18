from typing import Protocol

from adrobot.application.dto.campaign import Campaign, Catalog, Choice, NewCampaign
from adrobot.application.dto.stream import Assignment, Stream


class CampaignReader(Protocol):
    async def campaigns(
        self,
        offset: int,
        limit: int,
        query: str,
    ) -> tuple[Campaign, ...]: ...

    async def campaign(self, campaign_id: int) -> Campaign: ...


class CampaignWriter(Protocol):
    async def create_campaign(self, data: NewCampaign, alias: str) -> Campaign: ...
    async def enable_campaign(self, campaign_id: int) -> Campaign: ...


class StreamReader(Protocol):
    async def streams(self, campaign_id: int) -> tuple[Stream, ...]: ...
    async def stream(self, stream_id: int) -> Stream: ...


class StreamWriter(Protocol):
    async def create_geo_stream(self, campaign_id: int, country: str) -> Stream: ...
    async def create_offer_stream(self, campaign_id: int, offer_id: int) -> Stream: ...

    async def put_offers(
        self,
        stream_id: int,
        offers: tuple[Assignment, ...],
    ) -> Stream: ...


class CatalogReader(Protocol):
    async def catalog(self) -> Catalog: ...
    async def offers(self, query: str = '') -> tuple[Choice, ...]: ...
    async def offer(self, offer_id: int) -> Choice | None: ...


class ClickReader(Protocol):
    async def stream_clicks_today(self, campaign_id: int) -> dict[int, int]: ...
