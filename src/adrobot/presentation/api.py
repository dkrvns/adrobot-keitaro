from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, status

from adrobot.application.dto.campaign import NewCampaign
from adrobot.ioc import Operations, Resources, operations
from adrobot.presentation.schemas import (
    CampaignPageResponse,
    CampaignResponse,
    CatalogResponse,
    ChoiceResponse,
    CreateCampaignBody,
    DraftBody,
    DraftResponse,
    StreamResponse,
    WorkspaceResponse,
)

router = APIRouter(prefix='/api')

type OperationsDep = Annotated[Operations, Depends(operations)]
type ResourceID = Annotated[int, Path(gt=0, le=2**63 - 1)]
type Revision = Annotated[int, Query(gt=0, le=2**63 - 1)]


@router.get('/catalog')
async def get_catalog(ops: OperationsDep, request: Request) -> CatalogResponse:
    resources: Resources = request.app.state.resources
    catalog = await ops.catalog.catalog()
    return CatalogResponse(
        domains=[ChoiceResponse.model_validate(row) for row in catalog.domains],
        groups=[ChoiceResponse.model_validate(row) for row in catalog.groups],
        sources=[ChoiceResponse.model_validate(row) for row in catalog.sources],
        campaign_prefix=resources.config.campaign_prefix,
        timezone=resources.config.keitaro_timezone,
    )


@router.get('/offers')
async def find_offers(
    ops: OperationsDep,
    query: Annotated[str, Query(max_length=100)] = '',
) -> list[ChoiceResponse]:
    query = query.strip()
    if query.isascii() and query.isdigit() and len(query) <= 18:
        single = await ops.catalog.offer(int(query))
        if single is not None:
            return [ChoiceResponse.model_validate(single)]
    offers = await ops.catalog.offers(query)
    return [ChoiceResponse.model_validate(row) for row in offers[:30]]


@router.get('/campaigns')
async def list_campaigns(
    ops: OperationsDep,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
    query: Annotated[str, Query(max_length=100)] = '',
) -> CampaignPageResponse:
    page = await ops.list_campaigns(offset, limit, query.strip())
    return CampaignPageResponse(
        items=[CampaignResponse.from_campaign(row) for row in page.items],
        has_more=page.has_more,
    )


@router.post('/campaigns', status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CreateCampaignBody,
    ops: OperationsDep,
) -> CampaignResponse:
    campaign = await ops.create(
        body.request_id,
        NewCampaign(
            body.name,
            body.country,
            body.offer_id,
            body.domain_id,
            body.group_id,
            body.traffic_source_id,
        ),
    )
    return CampaignResponse.from_campaign(campaign)


@router.post('/campaigns/{campaign_id}/sync')
async def sync_campaign(
    campaign_id: ResourceID,
    ops: OperationsDep,
    request: Request,
) -> WorkspaceResponse:
    campaign, views = await ops.sync(campaign_id)
    resources: Resources = request.app.state.resources
    origin = resources.config.keitaro_origin
    return WorkspaceResponse(
        campaign=CampaignResponse.from_campaign(campaign),
        streams=[StreamResponse.from_view(view) for view in views],
        admin_url=f'{origin}/admin/#!/campaigns/{campaign_id}',
    )


@router.patch('/campaigns/{campaign_id}/streams/{stream_id}/draft')
async def edit_draft(
    campaign_id: ResourceID,
    stream_id: ResourceID,
    body: DraftBody,
    ops: OperationsDep,
) -> DraftResponse:
    snapshot = await ops.edit(
        campaign_id,
        stream_id,
        body.revision,
        body.action,
        body.offer_id,
    )
    return DraftResponse.from_snapshot(snapshot)


@router.delete('/campaigns/{campaign_id}/streams/{stream_id}/draft')
async def cancel_draft(
    campaign_id: ResourceID,
    stream_id: ResourceID,
    revision: Revision,
    ops: OperationsDep,
) -> DraftResponse:
    return DraftResponse.from_snapshot(
        await ops.cancel(campaign_id, stream_id, revision)
    )


@router.post('/campaigns/{campaign_id}/streams/{stream_id}/publish')
async def publish_draft(
    campaign_id: ResourceID,
    stream_id: ResourceID,
    revision: Revision,
    ops: OperationsDep,
) -> DraftResponse:
    return DraftResponse.from_snapshot(
        await ops.publish(campaign_id, stream_id, revision)
    )
