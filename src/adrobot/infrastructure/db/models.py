from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Index, MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            'ix': 'ix_%(column_0_label)s',
            'pk': 'pk_%(table_name)s',
            'ck': 'ck_%(table_name)s_%(constraint_name)s',
        }
    )


class StreamSnapshotModel(Base):
    __tablename__ = 'stream_snapshots'
    __table_args__ = (Index('ix_stream_snapshots_campaign_id', 'campaign_id'),)

    stream_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    editable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    committed: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    draft: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )


class CreationModel(Base):
    __tablename__ = 'campaign_creations'

    request_id: Mapped[UUID] = mapped_column(primary_key=True)
    input: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    campaign_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False)
