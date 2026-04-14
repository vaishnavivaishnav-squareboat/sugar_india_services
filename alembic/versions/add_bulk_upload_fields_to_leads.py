"""Add description, country, email_2, phone_2 to leads

Revision ID: add_bulk_upload_fields
Revises: add_highlights_fields
Create Date: 2026-04-10

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_bulk_upload_fields'
down_revision: Union[str, Sequence[str], None] = 'add_highlights_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('leads', sa.Column('description', sa.Text(),    nullable=True, server_default=''))
    op.add_column('leads', sa.Column('country',     sa.String(100), nullable=True, server_default='India'))
    op.add_column('leads', sa.Column('email_2',     sa.String(255), nullable=True, server_default=''))
    op.add_column('leads', sa.Column('phone_2',     sa.String(50),  nullable=True, server_default=''))


def downgrade() -> None:
    op.drop_column('leads', 'phone_2')
    op.drop_column('leads', 'email_2')
    op.drop_column('leads', 'country')
    op.drop_column('leads', 'description')
