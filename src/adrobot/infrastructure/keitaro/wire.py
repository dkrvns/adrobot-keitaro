from typing import Literal

from pydantic import BaseModel, Field

from adrobot.application.dto.campaign import Campaign, Choice
from adrobot.application.dto.stream import Assignment, Stream


class ChoiceWire(BaseModel):
    id: int = Field(gt=0)
    name: str
    state: str = 'active'
    type: str = ''

    def to_choice(self) -> Choice:
        return Choice(self.id, self.name)


class CampaignWire(BaseModel):
    id: int = Field(gt=0)
    name: str
    alias: str
    state: str
    domain: str | None = None
    group_id: int | None = None
    traffic_source_id: int | None = None
    domain_id: int | None = None

    def to_campaign(self) -> Campaign:
        return Campaign(
            id=self.id,
            name=self.name,
            alias=self.alias,
            state=self.state,
            domain=self.domain or '',
            group_id=self.group_id,
            traffic_source_id=self.traffic_source_id,
            domain_id=self.domain_id,
        )


class AssignmentWire(BaseModel):
    offer_id: int = Field(gt=0)
    share: int = Field(ge=0, le=100)
    state: Literal['active', 'disabled']


class StreamWire(BaseModel):
    id: int = Field(gt=0)
    campaign_id: int = Field(gt=0)
    name: str
    position: int
    schema_: str = Field(alias='schema')
    state: str
    offers: list[AssignmentWire] = Field(default_factory=list)

    def to_stream(self) -> Stream:
        return Stream(
            id=self.id,
            campaign_id=self.campaign_id,
            name=self.name,
            position=self.position,
            schema=self.schema_,
            state=self.state,
            offers=tuple(
                Assignment(row.offer_id, row.share, row.state) for row in self.offers
            ),
        )


class ClickRowWire(BaseModel):
    stream_id: int = Field(ge=0)
    clicks: int = Field(ge=0)


class ClickReportWire(BaseModel):
    rows: list[ClickRowWire]
