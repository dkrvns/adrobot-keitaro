import json
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from adrobot.config import Config
from adrobot.main import create_app

type JSONObject = dict[str, object]


class Tracker:
    """In-memory HTTP stand-in for the tracker, with actual API shapes."""

    def __init__(self) -> None:
        self.campaign_id = int.from_bytes(uuid4().bytes[:6])
        self.geo_id = self.campaign_id * 10 + 1
        self.flow_id = self.geo_id + 1
        self.campaign: JSONObject | None = None
        self.streams: dict[int, JSONObject] = {}
        self.offer_catalog = [
            {'id': offer_id, 'name': f'Оффер {offer_id}', 'state': 'active'}
            for offer_id in range(100, 105)
        ]
        self.campaign_creates = 0
        self.offer_writes = 0
        self.fail_campaign_response = False
        self.fail_offer_flow = False
        self.fail_publish_response = False

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.headers['Api-Key'] == 'fixture-key'
        route = request.url.path.removeprefix('/admin_api/v1/')
        method = request.method
        payload: JSONObject = json.loads(request.content or b'{}')

        if method == 'GET':
            return self._get(route, request.url.params)
        if method == 'POST' and route == 'campaigns':
            assert len(str(payload['alias'])) <= 50
            self.campaign_creates += 1
            self.campaign = {
                'id': self.campaign_id,
                'domain': 'test.example',
                **payload,
            }
            if self.fail_campaign_response:
                self.fail_campaign_response = False
                return httpx.Response(503)
            return httpx.Response(200, json=self.campaign)
        if method == 'POST' and route == 'streams':
            if payload['schema'] == 'landings' and self.fail_offer_flow:
                self.fail_offer_flow = False
                return httpx.Response(503)
            flow_id = self.geo_id if payload['schema'] == 'redirect' else self.flow_id
            flow = {'id': flow_id, 'offers': [], **payload}
            self.streams[flow_id] = flow
            return httpx.Response(200, json=flow)
        if method == 'PUT' and route == f'campaigns/{self.campaign_id}':
            assert self.campaign is not None
            self.campaign.update(payload)
            return httpx.Response(200, json=self.campaign)
        if method == 'PUT' and route == f'streams/{self.flow_id}':
            assert set(payload) == {'offers'}
            self.offer_writes += 1
            self.streams[self.flow_id].update(payload)
            if self.fail_publish_response:
                self.fail_publish_response = False
                return httpx.Response(503)
            return httpx.Response(200, json=self.streams[self.flow_id])
        if method == 'POST' and route == 'report/build':
            assert payload['range'] == {'interval': 'today', 'timezone': 'Europe/Minsk'}
            assert payload['grouping'] == ['stream_id']
            assert payload['filters'] == [
                {
                    'name': 'campaign_id',
                    'operator': 'EQUALS',
                    'expression': self.campaign_id,
                }
            ]
            return httpx.Response(
                200,
                json={
                    'rows': [
                        {'stream_id': self.flow_id, 'clicks': 17},
                    ],
                    'total': 1,
                },
            )
        return httpx.Response(404)

    def _get(self, route: str, params: httpx.QueryParams) -> httpx.Response:
        catalog = {
            'domains': [{'id': 10, 'name': 'test.example'}],
            'groups': [{'id': 11, 'name': 'FORTESTS', 'type': 'campaigns'}],
            'traffic_sources': [{'id': 12, 'name': 'FORTESTS'}],
            'offers': self.offer_catalog,
        }
        if route in catalog:
            return httpx.Response(200, json=catalog[route])
        if route.startswith('offers/'):
            for offer in self.offer_catalog:
                if route == f'offers/{offer["id"]}':
                    return httpx.Response(200, json=offer)
        if route == 'campaigns':
            rows = [] if self.campaign is None else [self.campaign]
            start = int(params.get('offset', '0'))
            limit = int(params.get('limit', '100'))
            return httpx.Response(200, json=rows[start : start + limit])
        if route == f'campaigns/{self.campaign_id}' and self.campaign:
            return httpx.Response(200, json=self.campaign)
        if route == f'campaigns/{self.campaign_id}/streams':
            return httpx.Response(200, json=list(self.streams.values()))
        for flow_id, flow in self.streams.items():
            if route == f'streams/{flow_id}':
                return httpx.Response(200, json=flow)
        return httpx.Response(404)

    def creation_body(self) -> JSONObject:
        return {
            'request_id': str(uuid4()),
            'name': 'test-case',
            'country': 'au',
            'offer_id': 100,
            'domain_id': 10,
            'group_id': 11,
            'traffic_source_id': 12,
        }


@pytest.fixture
def tracker() -> Tracker:
    return Tracker()


@pytest.fixture
def app(tracker: Tracker) -> FastAPI:
    url = os.environ['DATABASE_URL']
    assert httpx.URL(url).path == '/adrobot_test'
    config = Config.model_validate(
        {
            'database_url': url,
            'keitaro_url': 'https://fixture.example',
            'keitaro_api_key': 'fixture-key',
        }
    )
    return create_app(config, tracker_transport=httpx.MockTransport(tracker.handle))


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url='http://testserver',
        ) as test_client,
    ):
        yield test_client
