"""Create campaign operation and stream workspace tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '20261118_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'campaign_creations',
        sa.Column('request_id', sa.Uuid(), nullable=False),
        sa.Column('input', postgresql.JSONB(), nullable=False),
        sa.Column('campaign_id', sa.BigInteger(), nullable=True),
        sa.Column('completed', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('request_id', name='pk_campaign_creations'),
    )
    op.create_table(
        'stream_snapshots',
        sa.Column('stream_id', sa.BigInteger(), nullable=False),
        sa.Column('campaign_id', sa.BigInteger(), nullable=False),
        sa.Column('revision', sa.BigInteger(), nullable=False),
        sa.Column('editable', sa.Boolean(), nullable=False),
        sa.Column('committed', postgresql.JSONB(), nullable=False),
        sa.Column('draft', postgresql.JSONB(none_as_null=True), nullable=True),
        sa.PrimaryKeyConstraint('stream_id', name='pk_stream_snapshots'),
    )
    op.create_index(
        'ix_stream_snapshots_campaign_id', 'stream_snapshots', ['campaign_id']
    )


def downgrade() -> None:
    op.drop_index('ix_stream_snapshots_campaign_id', table_name='stream_snapshots')
    op.drop_table('stream_snapshots')
    op.drop_table('campaign_creations')
