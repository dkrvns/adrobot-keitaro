from dataclasses import replace

from adrobot.application.commands.streams.offers import assignments, redistribute
from adrobot.application.dto.stream import DraftAction, OfferEntry, Snapshot
from adrobot.application.errors import Conflict, Invalid, Missing
from adrobot.application.ports.stream_storage import SnapshotReader, SnapshotSaver
from adrobot.application.ports.tracker import CatalogReader
from adrobot.application.ports.transaction import Committer, OperationLock


def require_snapshot(
    snapshot: Snapshot,
    campaign_id: int,
    revision: int,
) -> None:
    if snapshot.campaign_id != campaign_id or snapshot.stream_id is None:
        raise Missing('Stream was not found. Refresh the campaign.')
    if snapshot.revision != revision:
        raise Conflict('The stream has changed. Refresh the campaign.')


class EditDraftCommand:
    def __init__(
        self,
        reader: SnapshotReader,
        saver: SnapshotSaver,
        committer: Committer,
        locks: OperationLock,
        catalog: CatalogReader,
    ) -> None:
        self._reader = reader
        self._saver = saver
        self._committer = committer
        self._locks = locks
        self._catalog = catalog

    async def __call__(
        self,
        campaign_id: int,
        stream_id: int,
        revision: int,
        action: DraftAction,
        offer_id: int,
    ) -> Snapshot:
        async with self._locks.acquire(campaign_id):
            snapshot = await self._reader.get(stream_id)
            require_snapshot(snapshot, campaign_id, revision)
            if not snapshot.editable:
                raise Invalid('This stream does not support offers.')

            rows = list(
                snapshot.committed if snapshot.draft is None else snapshot.draft,
            )
            index = next(
                (i for i, row in enumerate(rows) if row.offer_id == offer_id),
                None,
            )
            if action == 'add':
                if index is not None:
                    raise Conflict('The offer is already listed in this stream.')
                await self._committer.commit()
                offer = await self._catalog.offer(offer_id)
                if offer is None:
                    raise Missing('Offer was not found or is unavailable.')
                rows.append(OfferEntry(offer.id, offer.name, 0))
            else:
                if index is None:
                    raise Missing('Offer was not found in this stream.')
                if action == 'restore':
                    await self._committer.commit()
                    offer = await self._catalog.offer(offer_id)
                    if offer is None:
                        raise Missing('Offer was not found or is unavailable.')
                self._edit_existing(rows, index, snapshot.committed, action)

            edited = tuple(rows) if action == 'pin' else redistribute(tuple(rows))
            if assignments(edited) == assignments(snapshot.committed):
                updated = replace(
                    snapshot,
                    committed=edited,
                    draft=None,
                    revision=revision + 1,
                )
            else:
                updated = replace(snapshot, draft=edited, revision=revision + 1)
            await self._saver.save(updated)
            await self._committer.commit()
            return updated

    @staticmethod
    def _edit_existing(
        rows: list[OfferEntry],
        index: int,
        committed: tuple[OfferEntry, ...],
        action: DraftAction,
    ) -> None:
        row = rows[index]
        if action == 'remove' and row.state != 'removed':
            if any(previous.offer_id == row.offer_id for previous in committed):
                rows[index] = replace(row, share=0, state='removed', pinned=False)
            else:
                rows.pop(index)
        elif action == 'restore' and row.state == 'removed':
            rows[index] = replace(row, state='active')
        elif action == 'pin' and row.state == 'active':
            rows[index] = replace(row, pinned=not row.pinned)
        else:
            raise Invalid('The action is unavailable for this offer.')


class CancelDraftCommand:
    def __init__(
        self,
        reader: SnapshotReader,
        saver: SnapshotSaver,
        committer: Committer,
        locks: OperationLock,
    ) -> None:
        self._reader = reader
        self._saver = saver
        self._committer = committer
        self._locks = locks

    async def __call__(
        self,
        campaign_id: int,
        stream_id: int,
        revision: int,
    ) -> Snapshot:
        async with self._locks.acquire(campaign_id):
            snapshot = await self._reader.get(stream_id)
            require_snapshot(snapshot, campaign_id, revision)
            if snapshot.draft is not None:
                snapshot = replace(snapshot, draft=None, revision=revision + 1)
                await self._saver.save(snapshot)
            await self._committer.commit()
            return snapshot
