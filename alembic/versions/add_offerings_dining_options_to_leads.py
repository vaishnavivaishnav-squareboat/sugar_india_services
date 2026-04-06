"""Add offerings and dining_options columns to leads

Revision ID: add_offerings_dining_options
Revises: add_highlights_fields
Create Date: 2026-04-03

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'add_offerings_dining_options'
down_revision: Union[str, Sequence[str], None] = 'add_highlights_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('leads', sa.Column('offerings', JSONB, nullable=True, server_default='[]'))
    op.add_column('leads', sa.Column('dining_options', JSONB, nullable=True, server_default='[]'))


def downgrade() -> None:
    op.drop_column('leads', 'dining_options')
    op.drop_column('leads', 'offerings')
