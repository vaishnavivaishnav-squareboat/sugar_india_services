"""
app/services/storage/storage_service.py
─────────────────────────────────────────────────────────────────────────────
Stage 8 — Lead, Contact, and Email Storage.

Persists all three entity types in a single database transaction per run:
  - Lead           — one row per unique business (uuid4 PK)
  - Contact        — zero or more rows per lead (integer PK + FK to lead)
  - OutreachEmail  — one row per lead (uuid4 PK + FK to lead)

Uses session.flush() after each Lead insert to resolve lead.id before
the FK references in Contact and OutreachEmail are written.
Rolls back the entire transaction on commit failure.

This is the clean, modular replacement for the inline store_leads_and_emails()
function in stages.py. stages.py delegates to this service.
─────────────────────────────────────────────────────────────────────────────
"""
import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.orm import Lead, Contact, OutreachEmail
from app.core.constants import LeadStatus, EmailStatus

logger = logging.getLogger(__name__)



# ── START ────────────────────────────────────────────────────────
async def store_pipeline_results(
    final_leads: list[dict],
    session: AsyncSession,
) -> bool:
    """
    Persist Lead, Contact, and OutreachEmail records for the current pipeline
    run in a single atomic transaction.

    Args:
        final_leads: List of email dicts produced by Stage 7, each containing
                     a nested "business" key with the enriched business dict.
        session:     Active async SQLAlchemy session.

    Returns:
        True if the commit succeeded, False if it was rolled back.
    """
    stored = 0

    # Group email items by business so each business gets exactly ONE Lead row
    # and ONE set of Contact rows, but potentially many OutreachEmail rows.
    grouped: dict[str, dict] = {}  # business_name → { "biz": ..., "items": [...] }
    for item in final_leads:
        biz  = item.get("business", {})
        key  = biz.get("business_name", "") or id(biz)
        if key not in grouped:
            grouped[key] = {"biz": biz, "items": []}
        grouped[key]["items"].append(item)

    for key, group in grouped.items():
        biz   = group["biz"]
        items = group["items"]
        try:
            now  = datetime.now(timezone.utc)
            lead = Lead(
                id                           = str(uuid.uuid4()),
                business_name                = biz.get("business_name", ""),
                segment                      = biz.get("segment", "Restaurant"),
                city                         = biz.get("city", ""),
                state                        = biz.get("state", ""),
                country                      = biz.get("country", "India"),
                tier                         = int(biz.get("tier", 2) or 2),
                address                      = biz.get("address", ""),
                phone                        = biz.get("phone", ""),
                email                        = biz.get("email", ""),
                website                      = biz.get("website", ""),
                description                  = biz.get("description", ""),
                rating                       = float(biz.get("rating", 0) or 0),
                num_outlets                  = int(biz.get("num_outlets", 1) or 1),
                has_dessert_menu             = bool(biz.get("has_dessert_menu", False)),
                hotel_category               = biz.get("hotel_category", ""),
                is_chain                     = bool(biz.get("is_chain", False)),
                ai_score                     = int(biz.get("kpi_score", 0) or 0),
                ai_reasoning                 = biz.get("ai_reasoning", ""),
                priority                     = biz.get("priority", "Low"),
                status                       = LeadStatus.NEW,
                source                       = biz.get("source", "pipeline"),
                monthly_volume_estimate      = f"{biz.get('monthly_sugar_estimate_kg', '')} kg",
                highlights                   = biz.get("highlights", []),
                offerings                    = biz.get("offerings", []),
                dining_options               = biz.get("dining_options", []),
                sugar_signal_from_highlights = bool(biz.get("sugar_signal_from_highlights", False)),
                highlight_sugar_signals      = biz.get("highlight_sugar_signals", []),
                created_at                   = now,
                updated_at                   = now,
            )
            session.add(lead)
            await session.flush()  # resolve lead.id before FK references

            # ── Contacts (one row per unique contact, written once per lead) ──
            for cd in biz.get("contacts", []):
                if not cd.get("name"):
                    continue
                session.add(Contact(
                    lead_id          = lead.id,
                    name             = cd.get("name", ""),
                    role             = cd.get("role", ""),
                    email            = cd.get("email", ""),
                    email_2          = cd.get("email_2", ""),
                    phone            = cd.get("phone", ""),
                    phone_2          = cd.get("phone_2", ""),
                    linkedin_url     = cd.get("linkedin_url", ""),
                    confidence_score = float(cd.get("confidence_score", 0.0) or 0.0),
                    verified         = cd.get("verified", ""),
                    source           = cd.get("source", "pipeline"),
                    seniority        = cd.get("seniority", ""),
                    department       = cd.get("department", ""),
                    is_primary       = bool(cd.get("is_primary", False)),
                    created_at       = now,
                    updated_at       = now,
                ))

            # ── OutreachEmails (one row per recipient — all contacts with email) ──
            for item in items:
                session.add(OutreachEmail(
                    id            = str(uuid.uuid4()),
                    lead_id       = lead.id,
                    lead_name     = item.get("lead_name", ""),
                    lead_city     = item.get("lead_city", ""),
                    lead_segment  = item.get("lead_segment", ""),
                    subject       = item.get("subject", ""),
                    body          = item.get("body", ""),
                    status        = EmailStatus.DRAFT,
                    sent_to_email = item.get("sent_to_email", ""),
                    generated_at  = now,
                ))

            stored += 1

        except Exception as exc:
            logger.info(f"[Store] Failed for '{biz.get('business_name')}': {exc}")
            continue

    try:
        await session.commit()
        logger.info(f"[Store] {stored} leads (+ contacts + emails) committed to DB.")
        return True
    except Exception as exc:
        await session.rollback()
        logger.info(f"[Store] DB commit failed: {exc}")
        return False
