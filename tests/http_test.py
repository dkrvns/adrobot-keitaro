from typing import Any
from uuid import uuid4

from httpx import AsyncClient

from conftest import Tracker


async def test_create_recovers_campaign_and_streams_after_partial_upstream_failure(
    client: AsyncClient,
    tracker: Tracker,
) -> None:
    payload = tracker.creation_body()
    tracker.fail_campaign_response = True
    tracker.fail_offer_flow = True

    assert (await client.post('/api/campaigns', json=payload)).status_code == 502
    assert tracker.campaign is not None
    assert tracker.campaign['state'] == 'disabled'
    assert tracker.streams == {}

    assert (await client.post('/api/campaigns', json=payload)).status_code == 502
    assert list(tracker.streams) == [tracker.geo_id]
    assert tracker.campaign['state'] == 'disabled'

    created = await client.post('/api/campaigns', json=payload)
    assert created.status_code == 201
    assert created.json()['id'] == tracker.campaign_id
    assert created.json()['name'] == 'test_kryvanos_test-case'
    assert created.json()['state'] == 'active'
    assert tracker.campaign_creates == 1
    assert tracker.campaign['domain_id'] == 10
    assert tracker.campaign['group_id'] == 11
    assert tracker.campaign['traffic_source_id'] == 12
    geo = tracker.streams[tracker.geo_id]
    assert geo['type'] == 'forced'
    assert geo['position'] == 1
    assert geo['action_payload'] == 'https://www.google.com/'
    assert geo['filters'] == [{'name': 'country', 'mode': 'accept', 'payload': ['AU']}]
    flow = tracker.streams[tracker.flow_id]
    assert flow['type'] == 'default'
    assert flow['position'] == 2
    assert flow['offers'] == [{'offer_id': 100, 'share': 100, 'state': 'active'}]

    assert (await client.post('/api/campaigns', json=payload)).json() == created.json()
    assert tracker.campaign_creates == 1
    assert len(tracker.streams) == 2
    assert (
        await client.post('/api/campaigns', json={**payload, 'country': 'BY'})
    ).status_code == 409


async def test_editor_persists_drafts_pins_and_archives_with_exact_shares(
    client: AsyncClient,
    tracker: Tracker,
) -> None:
    campaign, _, flow, draft = await open_workspace(client, tracker)
    update = find_flow(
        (await client.post(campaign + '/sync')).json()['streams'], tracker.flow_id
    )
    assert update['clicks_today'] == 17
    assert update['offers'] == flow['offers']

    async def action(revision: int, name: str, offer_id: int) -> dict[str, Any]:
        response = await client.patch(
            draft,
            json={
                'revision': revision,
                'action': name,
                'offer_id': offer_id,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    draft_result = flow
    for offer_id in (101, 102, 103):
        draft_result = await action(draft_result['revision'], 'add', offer_id)
    assert offer_shares(draft_result) == {100: 25, 101: 25, 102: 25, 103: 25}
    assert draft_result['dirty'] is True
    assert tracker.offer_writes == 0
    assert len(tracker.streams[tracker.flow_id]['offers']) == 1
    reloaded = find_flow(
        (await client.post(campaign + '/sync')).json()['streams'], tracker.flow_id
    )
    assert offer_shares(reloaded) == offer_shares(draft_result)

    response = await client.delete(draft, params={'revision': reloaded['revision']})
    assert response.status_code == 200
    assert offer_shares(response.json()) == {100: 100}
    assert tracker.offer_writes == 0

    draft_result = response.json()
    for offer_id in (101, 102, 103):
        draft_result = await action(draft_result['revision'], 'add', offer_id)
    publish = draft.removesuffix('/draft') + '/publish'
    confirmed = await client.post(
        publish, params={'revision': draft_result['revision']}
    )
    assert confirmed.status_code == 200
    assert tracker.offer_writes == 1
    draft_result = await action(confirmed.json()['revision'], 'pin', 100)
    draft_result = await action(draft_result['revision'], 'remove', 102)
    assert offer_shares(draft_result) == {100: 25, 101: 38, 102: 0, 103: 37}
    assert tracker.offer_writes == 1

    response = await client.post(
        publish,
        params={
            'revision': draft_result['revision'],
        },
    )
    assert response.status_code == 200
    assert response.json()['dirty'] is False
    assert tracker.offer_writes == 2
    assert tracker.streams[tracker.flow_id]['offers'] == [
        {'offer_id': 100, 'share': 25, 'state': 'active'},
        {'offer_id': 101, 'share': 38, 'state': 'active'},
        {'offer_id': 103, 'share': 37, 'state': 'active'},
    ]

    tracker.streams[tracker.flow_id]['offers'] = [
        {'offer_id': 100, 'share': 25, 'state': 'active'},
        {'offer_id': 103, 'share': 37, 'state': 'active'},
    ]
    external = find_flow(
        (await client.post(campaign + '/sync')).json()['streams'], tracker.flow_id
    )
    assert offer_shares(external) == {100: 25, 101: 0, 102: 0, 103: 37}
    assert {row['offer_id'] for row in external['offers'] if row['pinned']} == {100}
    restored = await action(external['revision'], 'restore', 101)
    assert offer_shares(restored) == {100: 25, 101: 37, 102: 0, 103: 38}


async def test_publish_preserves_external_edits_and_recovers_unknown_success(
    client: AsyncClient,
    tracker: Tracker,
) -> None:
    campaign, _, flow, draft = await open_workspace(client, tracker)
    publish = draft.removesuffix('/draft') + '/publish'
    body = {'revision': flow['revision'], 'action': 'add', 'offer_id': 101}
    result = await client.patch(draft, json=body)
    assert result.status_code == 200
    assert (
        await client.patch(draft, json={**body, 'offer_id': 102})
    ).status_code == 409
    revision = result.json()['revision']

    tracker.streams[tracker.flow_id]['offers'] = [
        {'offer_id': 100, 'share': 70, 'state': 'active'},
        {'offer_id': 104, 'share': 30, 'state': 'active'},
    ]
    assert (
        await client.post(publish, params={'revision': revision})
    ).status_code == 409
    assert tracker.offer_writes == 0
    assert (
        await client.delete(draft, params={'revision': revision})
    ).status_code == 200

    latest = find_flow(
        (await client.post(campaign + '/sync')).json()['streams'], tracker.flow_id
    )
    assert offer_shares(latest) == {100: 70, 104: 30}
    result = await client.patch(draft, json={**body, 'revision': latest['revision']})
    assert result.status_code == 200
    revision = result.json()['revision']

    tracker.fail_publish_response = True
    assert (
        await client.post(publish, params={'revision': revision})
    ).status_code == 502
    assert tracker.offer_writes == 1
    retry = await client.post(publish, params={'revision': revision})
    assert retry.status_code == 200
    assert retry.json()['dirty'] is False
    assert offer_shares(retry.json()) == {100: 34, 104: 33, 101: 33}
    assert tracker.offer_writes == 1


async def test_validation_and_stream_identity_prevent_writes(
    client: AsyncClient,
    tracker: Tracker,
) -> None:
    payload = tracker.creation_body()
    assert (
        await client.post('/api/campaigns', json={**payload, 'country': 'XX'})
    ).status_code == 422
    assert tracker.campaign_creates == 0
    campaign, geo, flow, draft = await open_workspace(client, tracker)
    body = {'revision': flow['revision'], 'action': 'remove', 'offer_id': 100}
    wrong_campaign = draft.replace(
        str(tracker.campaign_id), str(tracker.campaign_id + 1), 1
    )
    assert (await client.patch(wrong_campaign, json=body)).status_code == 404
    assert (
        await client.patch(
            f'{campaign}/streams/{geo["id"]}/draft',
            json={**body, 'revision': geo['revision']},
        )
    ).status_code == 422
    assert (
        await client.patch(
            draft,
            json=body,
            headers={'Origin': 'https://different.example'},
        )
    ).status_code == 403
    assert (
        await client.post('/api/campaigns', content=b'x' * 17_000)
    ).status_code == 413
    assert (
        await client.post(
            '/api/campaigns',
            json={
                **payload,
                'request_id': str(uuid4()),
                'offer_id': 999,
            },
        )
    ).status_code == 422
    assert tracker.campaign_creates == 1
    assert tracker.offer_writes == 0


async def open_workspace(
    client: AsyncClient, tracker: Tracker
) -> tuple[str, dict[str, Any], dict[str, Any], str]:
    created = await client.post('/api/campaigns', json=tracker.creation_body())
    assert created.status_code == 201, created.text
    campaign = f'/api/campaigns/{tracker.campaign_id}'
    workspace = await client.post(campaign + '/sync')
    assert workspace.status_code == 200, workspace.text
    geo, flow = workspace.json()['streams']
    assert geo['editable'] is False
    assert geo['clicks_today'] == 0
    assert flow['id'] == tracker.flow_id
    assert flow['editable'] is True
    return campaign, geo, flow, f'{campaign}/streams/{tracker.flow_id}/draft'


def find_flow(streams: list[dict[str, Any]], flow_id: int) -> dict[str, Any]:
    return next(stream for stream in streams if stream['id'] == flow_id)


def offer_shares(result: dict[str, Any]) -> dict[int, int]:
    return {row['offer_id']: row['share'] for row in result['offers']}
