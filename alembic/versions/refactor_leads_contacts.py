"""Refactor leads/contacts: move decision-maker & secondary contact fields to contacts table

Revision ID: refactor_leads_contacts
Revises: merge_bulk_upload_and_state
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'refactor_leads_contacts'
down_revision = 'merge_bulk_upload_and_state'
branch_labels = None
depends_on = None


def upgrade():
    # ─── 1. Remove decision-maker + secondary-contact columns from leads ──────
    with op.batch_alter_table("leads") as batch_op:
        for col in (
            "decision_maker_name",
            "decision_maker_role",
            "decision_maker_linkedin",
            "email_2",
            "phone_2",
        ):
            try:
                batch_op.drop_column(col)
            except Exception:
                pass  # column may not exist if migration was partially applied

    # ─── 2. Add enriched person-details columns to contacts ───────────────────
    with op.batch_alter_table("contacts") as batch_op:
        batch_op.add_column(sa.Column("department",       sa.String(100), server_default="", nullable=True))
        batch_op.add_column(sa.Column("seniority",        sa.String(50),  server_default="", nullable=True))
        batch_op.add_column(sa.Column("is_primary",       sa.Boolean(),   server_default=sa.text("false"), nullable=True))
        batch_op.add_column(sa.Column("email_2",          sa.String(255), server_default="", nullable=True))
        batch_op.add_column(sa.Column("phone",            sa.String(50),  server_default="", nullable=True))
        batch_op.add_column(sa.Column("phone_2",          sa.String(50),  server_default="", nullable=True))
        batch_op.add_column(sa.Column("confidence_score", sa.Float(),     server_default="0.0", nullable=True))
        batch_op.add_column(sa.Column("verified",         sa.String(50),  server_default="", nullable=True))
        batch_op.add_column(sa.Column("source",           sa.String(50),  server_default="", nullable=True))

        # make role nullable (was NOT NULL in the original add_contacts_table migration)
        batch_op.alter_column("role", existing_type=sa.String(100), nullable=True, server_default="")


def downgrade():
    # ─── 1. Re-add removed columns to leads ──────────────────────────────────
    with op.batch_alter_table("leads") as batch_op:
        batch_op.add_column(sa.Column("decision_maker_name",     sa.String(255), server_default="", nullable=True))
        batch_op.add_column(sa.Column("decision_maker_role",     sa.String(255), server_default="", nullable=True))
        batch_op.add_column(sa.Column("decision_maker_linkedin", sa.String(500), server_default="", nullable=True))
        batch_op.add_column(sa.Column("email_2",                 sa.String(255), server_default="", nullable=True))
        batch_op.add_column(sa.Column("phone_2",                 sa.String(50),  server_default="", nullable=True))

    # ─── 2. Drop enriched columns from contacts ───────────────────────────────
    with op.batch_alter_table("contacts") as batch_op:
        for col in ("department", "seniority", "is_primary", "email_2",
                    "phone", "phone_2", "confidence_score", "verified", "source"):
            batch_op.drop_column(col)
