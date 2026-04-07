"""Add state column to cities table

Revision ID: add_state_to_cities
Revises: add_segments_table
Create Date: 2026-04-06

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_state_to_cities'
down_revision: Union[str, Sequence[str], None] = 'add_segments_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cities', sa.Column('state', sa.String(length=100), nullable=True, server_default=''))


def downgrade() -> None:
    op.drop_column('cities', 'state')
