from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Choice:
    id: int
    name: str


@dataclass(frozen=True, slots=True)
class Catalog:
    domains: tuple[Choice, ...]
    groups: tuple[Choice, ...]
    sources: tuple[Choice, ...]


@dataclass(frozen=True, slots=True)
class Campaign:
    id: int | None = None
    name: str = ''
    alias: str = ''
    state: str = ''
    domain: str = ''
    group_id: int | None = None
    traffic_source_id: int | None = None
    domain_id: int | None = None


@dataclass(frozen=True, slots=True)
class CampaignPage:
    items: tuple[Campaign, ...]
    has_more: bool


@dataclass(frozen=True, slots=True)
class NewCampaign:
    name: str
    country: str
    offer_id: int
    domain_id: int
    group_id: int
    traffic_source_id: int


@dataclass(frozen=True, slots=True)
class Creation:
    request_id: UUID | None = None
    input: NewCampaign | None = None
    campaign_id: int | None = None
    completed: bool = False
