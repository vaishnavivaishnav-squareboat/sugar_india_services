"""Merge add_bulk_upload_fields and add_state_to_cities heads

Revision ID: merge_bulk_upload_and_state
Revises: add_bulk_upload_fields, add_state_to_cities
Create Date: 2026-04-10

"""
from typing import Sequence, Union

revision: str = 'merge_bulk_upload_and_state'
down_revision: Union[str, Sequence[str], None] = ('add_bulk_upload_fields', 'add_state_to_cities')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
