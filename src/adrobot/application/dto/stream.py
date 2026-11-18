from dataclasses import dataclass
from typing import Literal

type OfferState = Literal['active', 'disabled', 'removed']
type DraftAction = Literal['add', 'remove', 'restore', 'pin']


@dataclass(frozen=True, slots=True)
class Assignment:
    offer_id: int
    share: int
    state: OfferState = 'active'


@dataclass(frozen=True, slots=True)
class Stream:
    id: int | None = None
    campaign_id: int | None = None
    name: str = ''
    position: int = 0
    schema: str = ''
    state: str = ''
    offers: tuple[Assignment, ...] = ()


@dataclass(frozen=True, slots=True)
class OfferEntry:
    offer_id: int
    name: str
    share: int
    state: OfferState = 'active'
    pinned: bool = False


@dataclass(frozen=True, slots=True)
class Snapshot:
    stream_id: int | None = None
    campaign_id: int | None = None
    revision: int = 0
    editable: bool = False
    committed: tuple[OfferEntry, ...] = ()
    draft: tuple[OfferEntry, ...] | None = None


@dataclass(frozen=True, slots=True)
class StreamView:
    stream: Stream
    snapshot: Snapshot
    clicks_today: int | None = None
