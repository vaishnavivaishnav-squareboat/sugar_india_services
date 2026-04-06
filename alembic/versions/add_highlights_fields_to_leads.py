"""Add highlights, service_options, sugar signal fields to leads

Revision ID: add_highlights_fields
Revises: add_contacts_table
Create Date: 2026-04-03

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'add_highlights_fields'
down_revision: Union[str, Sequence[str], None] = 'add_contacts_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('leads', sa.Column('highlights', JSONB, nullable=True, server_default='[]'))
    op.add_column('leads', sa.Column('offerings', JSONB, nullable=True, server_default='[]'))
    op.add_column('leads', sa.Column('dining_options', JSONB, nullable=True, server_default='[]'))
    op.add_column('leads', sa.Column('sugar_signal_from_highlights', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('leads', sa.Column('highlight_sugar_signals', JSONB, nullable=True, server_default='[]'))


def downgrade() -> None:
    op.drop_column('leads', 'highlight_sugar_signals')
    op.drop_column('leads', 'sugar_signal_from_highlights')
    op.drop_column('leads', 'dining_options')
    op.drop_column('leads', 'offerings')
    op.drop_column('leads', 'highlights')
