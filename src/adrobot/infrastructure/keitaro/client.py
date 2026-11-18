import asyncio
import logging
from collections.abc import Mapping
from dataclasses import asdict

import httpx
from pydantic import TypeAdapter, ValidationError

from adrobot.application.dto.campaign import Campaign, Catalog, Choice, NewCampaign
from adrobot.application.dto.stream import Assignment, Stream
from adrobot.application.errors import TrackerRejected, TrackerUnavailable
from adrobot.application.ports.tracker import (
    CampaignReader,
    CampaignWriter,
    CatalogReader,
    ClickReader,
    StreamReader,
    StreamWriter,
)
from adrobot.infrastructure.keitaro.wire import (
    CampaignWire,
    ChoiceWire,
    ClickReportWire,
    StreamWire,
)

logger = logging.getLogger(__name__)

campaign_object = TypeAdapter(CampaignWire)
campaign_list = TypeAdapter(list[CampaignWire])
stream_object = TypeAdapter(StreamWire)
stream_list = TypeAdapter(list[StreamWire])
choice_object = TypeAdapter(ChoiceWire)
choice_list = TypeAdapter(list[ChoiceWire])
click_report = TypeAdapter(ClickReportWire)


class KeitaroClient(
    CampaignReader,
    CampaignWriter,
    StreamReader,
    StreamWriter,
    CatalogReader,
    ClickReader,
):
    def __init__(self, client: httpx.AsyncClient, timezone: str) -> None:
        self._http = client
        self._timezone = timezone

    async def _request[T](
        self,
        method: str,
        route: str,
        adapter: TypeAdapter[T],
        *,
        params: Mapping[str, str | int] | None = None,
        body: dict[str, object] | None = None,
        allow_missing: bool = False,
    ) -> T | None:
        try:
            response = await self._http.request(
                method,
                route,
                params=params,
                json=body,
            )
        except httpx.RequestError:
            logger.warning('Keitaro request failed method=%s route=%s', method, route)
            raise TrackerUnavailable('Could not reach Keitaro. Try again.') from None
        if response.status_code == 404 and allow_missing:
            return None
        if response.is_client_error:
            logger.warning(
                'Keitaro rejected method=%s route=%s status=%d',
                method,
                route,
                response.status_code,
            )
            if response.status_code in (401, 402, 403):
                raise TrackerUnavailable('Check the Keitaro key and its permissions.')
            raise TrackerRejected('Keitaro rejected the operation.')
        if not response.is_success:
            raise TrackerUnavailable('Keitaro is temporarily unavailable.')
        try:
            return adapter.validate_json(response.content)
        except ValidationError:
            logger.warning('Invalid Keitaro response method=%s route=%s', method, route)
            raise TrackerUnavailable(
                'Keitaro returned an unexpected response.'
            ) from None

    async def campaigns(
        self,
        offset: int,
        limit: int,
        query: str,
    ) -> tuple[Campaign, ...]:
        if not query:
            page = await self._campaign_page(offset, limit)
            return tuple(item.to_campaign() for item in page)
        if query.isascii() and query.isdigit() and len(query) <= 18:
            campaign = await self.campaign(int(query))
            return (campaign,) if offset == 0 and campaign.id is not None else ()

        matches: list[Campaign] = []
        search = query.casefold()
        page_size = 100
        tracker_offset = 0
        while len(matches) < offset + limit:
            page = await self._campaign_page(tracker_offset, page_size)
            matches.extend(
                row.to_campaign()
                for row in page
                if search in row.name.casefold() or search in row.alias.casefold()
            )
            if len(page) < page_size:
                break
            tracker_offset += page_size
        return tuple(matches[offset : offset + limit])

    async def _campaign_page(self, offset: int, limit: int) -> list[CampaignWire]:
        return (
            await self._request(
                'GET',
                'campaigns',
                campaign_list,
                params={'offset': offset, 'limit': limit},
            )
            or []
        )

    async def campaign(self, campaign_id: int) -> Campaign:
        result = await self._request(
            'GET',
            f'campaigns/{campaign_id}',
            campaign_object,
            allow_missing=True,
        )
        return Campaign() if result is None else result.to_campaign()

    async def create_campaign(self, data: NewCampaign, alias: str) -> Campaign:
        response = await self._request(
            'POST',
            'campaigns',
            campaign_object,
            body={
                'name': data.name,
                'alias': alias,
                'type': 'position',
                'state': 'disabled',
                'domain_id': data.domain_id,
                'group_id': data.group_id,
                'traffic_source_id': data.traffic_source_id,
            },
        )
        if response is None:
            raise TrackerUnavailable('Keitaro did not confirm campaign creation.')
        return response.to_campaign()

    async def enable_campaign(self, campaign_id: int) -> Campaign:
        response = await self._request(
            'PUT',
            f'campaigns/{campaign_id}',
            campaign_object,
            body={'state': 'active'},
        )
        if response is None:
            raise TrackerUnavailable('Keitaro did not confirm campaign activation.')
        return response.to_campaign()

    async def streams(self, campaign_id: int) -> tuple[Stream, ...]:
        rows = (
            await self._request(
                'GET',
                f'campaigns/{campaign_id}/streams',
                stream_list,
            )
            or []
        )
        return tuple(
            row.to_stream()
            for row in sorted(rows, key=lambda item: item.position)
            if row.state != 'deleted'
        )

    async def stream(self, stream_id: int) -> Stream:
        row = await self._request(
            'GET',
            f'streams/{stream_id}',
            stream_object,
            allow_missing=True,
        )
        return Stream() if row is None else row.to_stream()

    async def create_geo_stream(self, campaign_id: int, country: str) -> Stream:
        return await self._write_stream(
            'POST',
            'streams',
            {
                'campaign_id': campaign_id,
                'name': f'{country} → Google',
                'position': 1,
                'type': 'forced',
                'schema': 'redirect',
                'action_type': 'http',
                'action_payload': 'https://www.google.com/',
                'collect_clicks': True,
                'state': 'active',
                'filters': [
                    {'name': 'country', 'mode': 'accept', 'payload': [country]}
                ],
            },
        )

    async def create_offer_stream(self, campaign_id: int, offer_id: int) -> Stream:
        return await self._write_stream(
            'POST',
            'streams',
            {
                'campaign_id': campaign_id,
                'name': 'Офферы',
                'position': 2,
                'type': 'default',
                'schema': 'landings',
                'action_type': 'http',
                'collect_clicks': True,
                'state': 'active',
                'landings': [],
                'offers': [asdict(Assignment(offer_id, 100))],
            },
        )

    async def put_offers(
        self,
        stream_id: int,
        offers: tuple[Assignment, ...],
    ) -> Stream:
        return await self._write_stream(
            'PUT',
            f'streams/{stream_id}',
            {'offers': [asdict(offer) for offer in offers]},
        )

    async def _write_stream(
        self,
        method: str,
        route: str,
        body: dict[str, object],
    ) -> Stream:
        response = await self._request(method, route, stream_object, body=body)
        if response is None:
            raise TrackerUnavailable('Keitaro did not confirm the stream update.')
        return response.to_stream()

    async def catalog(self) -> Catalog:
        domain_rows = self._request('GET', 'domains', choice_list)
        group_rows = self._request(
            'GET',
            'groups',
            choice_list,
            params={'type': 'campaigns'},
        )
        source_rows = self._request('GET', 'traffic_sources', choice_list)
        domains, groups, sources = await asyncio.gather(
            domain_rows,
            group_rows,
            source_rows,
        )
        return Catalog(
            domains=tuple(
                row.to_choice() for row in domains or [] if row.state == 'active'
            ),
            groups=tuple(
                row.to_choice() for row in groups or [] if row.type == 'campaigns'
            ),
            sources=tuple(
                row.to_choice() for row in sources or [] if row.state == 'active'
            ),
        )

    async def offers(self, query: str = '') -> tuple[Choice, ...]:
        rows = await self._request('GET', 'offers', choice_list) or []
        search = query.casefold()
        return tuple(
            row.to_choice()
            for row in rows
            if row.state == 'active'
            and (search in row.name.casefold() or search in str(row.id))
        )

    async def offer(self, offer_id: int) -> Choice | None:
        row = await self._request(
            'GET',
            f'offers/{offer_id}',
            choice_object,
            allow_missing=True,
        )
        return row.to_choice() if row and row.state == 'active' else None

    async def stream_clicks_today(self, campaign_id: int) -> dict[int, int]:
        report = await self._request(
            'POST',
            'report/build',
            click_report,
            body={
                'range': {'interval': 'today', 'timezone': self._timezone},
                'grouping': ['stream_id'],
                'metrics': ['clicks'],
                'filters': [
                    {
                        'name': 'campaign_id',
                        'operator': 'EQUALS',
                        'expression': campaign_id,
                    }
                ],
                'limit': 1000,
            },
        )
        return {row.stream_id: row.clicks for row in report.rows} if report else {}
