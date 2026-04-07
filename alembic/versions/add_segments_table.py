"""Add segments table

Revision ID: add_segments_table
Revises: add_contacts_table
Create Date: 2026-04-06

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_segments_table'
down_revision: Union[str, Sequence[str], None] = 'add_offerings_dining_options'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'segments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ulid', sa.String(length=26), nullable=False),
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False),
        sa.Column('cluster', sa.String(length=100), nullable=True),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ulid'),
        sa.UniqueConstraint('key'),
    )
    op.create_index(op.f('ix_segments_key'), 'segments', ['key'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_segments_key'), table_name='segments')
    op.drop_table('segments')
