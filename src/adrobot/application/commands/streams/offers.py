from dataclasses import replace

from adrobot.application.dto.stream import Assignment, OfferEntry
from adrobot.application.errors import Invalid


def assignments(rows: tuple[OfferEntry, ...]) -> tuple[Assignment, ...]:
    return tuple(
        sorted(
            (
                Assignment(row.offer_id, row.share, row.state)
                for row in rows
                if row.state != 'removed'
            ),
            key=lambda row: row.offer_id,
        )
    )


def signature(rows: tuple[Assignment, ...]) -> tuple[Assignment, ...]:
    return tuple(sorted(rows, key=lambda row: row.offer_id))


def redistribute(rows: tuple[OfferEntry, ...]) -> tuple[OfferEntry, ...]:
    active = [row for row in rows if row.state == 'active']
    candidates = [row for row in active if not row.pinned]
    remaining = 100 - sum(row.share for row in active if row.pinned)
    if not active:
        return rows
    if remaining < 0 or (remaining and not candidates):
        raise Invalid('Unpin an offer to distribute the remaining traffic.')
    if not candidates:
        return rows
    if remaining < len(candidates):
        raise Invalid('Unpin an offer to leave at least 1% for each active offer.')

    base, remainder = divmod(remaining, len(candidates))
    shares = {
        row.offer_id: base + (index < remainder) for index, row in enumerate(candidates)
    }
    return tuple(
        replace(row, share=shares[row.offer_id]) if row.offer_id in shares else row
        for row in rows
    )


def merge(
    previous: tuple[OfferEntry, ...],
    current: tuple[Assignment, ...],
    names: dict[int, str],
) -> tuple[OfferEntry, ...]:
    old = {row.offer_id: row for row in previous}
    published = []
    for row in current:
        prior = old.pop(row.offer_id, None)
        published.append(
            OfferEntry(
                offer_id=row.offer_id,
                name=names.get(
                    row.offer_id, prior.name if prior else f'#{row.offer_id}'
                ),
                share=row.share,
                state=row.state,
                pinned=bool(prior and prior.pinned and row.state == 'active'),
            )
        )
    archived = (
        replace(
            row,
            share=0,
            state='removed',
            pinned=False,
            name=names.get(
                row.offer_id,
                row.name,
            ),
        )
        for row in old.values()
    )
    return (*published, *archived)
