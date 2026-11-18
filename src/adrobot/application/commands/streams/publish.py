from dataclasses import replace

from adrobot.application.commands.streams.edit import require_snapshot
from adrobot.application.commands.streams.offers import assignments, signature
from adrobot.application.dto.stream import Snapshot
from adrobot.application.errors import Conflict, TrackerUnavailable
from adrobot.application.ports.stream_storage import SnapshotReader, SnapshotSaver
from adrobot.application.ports.tracker import StreamReader, StreamWriter
from adrobot.application.ports.transaction import Committer, OperationLock


class PublishDraftCommand:
    def __init__(
        self,
        reader: SnapshotReader,
        saver: SnapshotSaver,
        committer: Committer,
        locks: OperationLock,
        streams: StreamReader,
        writer: StreamWriter,
    ) -> None:
        self._reader = reader
        self._saver = saver
        self._committer = committer
        self._locks = locks
        self._streams = streams
        self._writer = writer

    async def __call__(
        self,
        campaign_id: int,
        stream_id: int,
        revision: int,
    ) -> Snapshot:
        async with self._locks.acquire(campaign_id):
            snapshot = await self._reader.get(stream_id)
            require_snapshot(snapshot, campaign_id, revision)
            await self._committer.commit()
            if snapshot.draft is None:
                return snapshot
            remote = await self._streams.stream(stream_id)
            if remote.campaign_id != campaign_id or remote.schema != 'landings':
                raise Conflict('The stream no longer supports offers in Keitaro.')

            current = signature(remote.offers)
            desired = assignments(snapshot.draft)
            if current != desired:
                if current != assignments(snapshot.committed):
                    raise Conflict(
                        'Keitaro changed this stream. Cancel the draft and refresh.',
                    )
                updated = await self._writer.put_offers(stream_id, desired)
                if signature(updated.offers) != desired:
                    raise TrackerUnavailable('Keitaro did not confirm the offer list.')

            snapshot = replace(
                snapshot,
                draft=None,
                committed=snapshot.draft,
                revision=revision + 1,
            )
            await self._saver.save(snapshot)
            await self._committer.commit()
            return snapshot
