from adrobot.application.dto.campaign import CampaignPage
from adrobot.application.ports.tracker import CampaignReader


class ListCampaignsInteractor:
    def __init__(self, reader: CampaignReader) -> None:
        self._reader = reader

    async def __call__(self, offset: int, limit: int, query: str) -> CampaignPage:
        results = await self._reader.campaigns(offset, limit + 1, query)
        return CampaignPage(results[:limit], len(results) > limit)
