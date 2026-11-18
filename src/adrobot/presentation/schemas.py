from typing import Annotated
from uuid import UUID

import pycountry
from pydantic import BaseModel, ConfigDict, Field, field_validator

from adrobot.application.dto.campaign import Campaign
from adrobot.application.dto.stream import DraftAction, OfferState, Snapshot, StreamView

type TrackerID = Annotated[int, Field(gt=0, le=2**63 - 1)]


class CreateCampaignBody(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    request_id: UUID
    name: str = Field(min_length=1, max_length=100)
    country: str = Field(pattern=r'^[A-Za-z]{2}$')
    offer_id: TrackerID
    domain_id: TrackerID
    group_id: TrackerID
    traffic_source_id: TrackerID

    @field_validator('country')
    @classmethod
    def validate_country(cls, value: str) -> str:
        country = value.upper()
        if pycountry.countries.get(alpha_2=country) is None:
            raise ValueError('Use an ISO 3166-1 alpha-2 country code.')
        return country


class DraftBody(BaseModel):
    model_config = ConfigDict(extra='forbid')

    revision: TrackerID
    action: DraftAction
    offer_id: TrackerID


class ChoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class CatalogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    domains: list[ChoiceResponse]
    groups: list[ChoiceResponse]
    sources: list[ChoiceResponse]
    campaign_prefix: str
    timezone: str


class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    alias: str
    state: str
    domain: str
    group_id: int | None
    traffic_source_id: int | None
    domain_id: int | None

    @classmethod
    def from_campaign(cls, campaign: Campaign) -> CampaignResponse:
        return cls.model_validate(campaign)


class CampaignPageResponse(BaseModel):
    items: list[CampaignResponse]
    has_more: bool


class OfferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    offer_id: int
    name: str
    share: int
    state: OfferState
    pinned: bool


class DraftResponse(BaseModel):
    revision: int
    dirty: bool
    editable: bool
    offers: list[OfferResponse]

    @classmethod
    def from_snapshot(cls, snapshot: Snapshot) -> DraftResponse:
        rows = snapshot.committed if snapshot.draft is None else snapshot.draft
        return cls(
            revision=snapshot.revision,
            dirty=snapshot.draft is not None,
            editable=snapshot.editable,
            offers=[OfferResponse.model_validate(row) for row in rows],
        )


class StreamResponse(DraftResponse):
    id: int
    name: str
    position: int
    state: str
    clicks_today: int | None

    @classmethod
    def from_view(cls, view: StreamView) -> StreamResponse:
        if view.stream.id is None:
            raise ValueError('Stream ID is required.')
        return cls(
            id=view.stream.id,
            name=view.stream.name,
            position=view.stream.position,
            state=view.stream.state,
            clicks_today=view.clicks_today,
            **DraftResponse.from_snapshot(view.snapshot).model_dump(),
        )


class WorkspaceResponse(BaseModel):
    admin_url: str
    campaign: CampaignResponse
    streams: list[StreamResponse]
