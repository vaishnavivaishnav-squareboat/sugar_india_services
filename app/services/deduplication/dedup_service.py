"""
app/services/deduplication/dedup_service.py
─────────────────────────────────────────────────────────────────────────────
Stage 4 — Lead Deduplication.

Two-pass deduplication:
  1. In-run dedup  — Jaccard name similarity > 0.8, or > 0.6 combined with
                     matching geo hash (lat/lng rounded to 3 d.p.)
  2. DB cross-check — Normalised "{business_name}_{city}" already present in
                      the leads table → skip to avoid re-inserting known leads.

This is the clean, modular replacement for the inline deduplicate_leads()
function and its private helpers in stages.py. stages.py delegates to this
service.
─────────────────────────────────────────────────────────────────────────────
"""
import re
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.orm import Lead

logger = logging.getLogger(__name__)


# ── Text / geo helpers ────────────────────────────────────────────────────────

def _normalize_name(name: str) -> str:
    """Lowercase, strip punctuation and common stopwords for fuzzy comparison."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name)
    stopwords = {"the", "a", "an", "and", "or", "of", "in", "at", "on"}
    return " ".join(w for w in name.split() if w not in stopwords).strip()


def _geo_hash(lat: float, lng: float, precision: int = 3) -> str:
    """Round lat/lng to *precision* decimal places and return a string key."""
    return f"{round(lat, precision)}:{round(lng, precision)}"


def _jaccard(a: str, b: str) -> float:
    """Token-level Jaccard similarity between two pre-normalised strings."""
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)



# ── START ────────────────────────────────────────────────────────
async def deduplicate_businesses(
    filtered_data: list[dict],
    session: AsyncSession,
) -> list[dict]:
    """
    Remove duplicate and already-stored businesses from the pipeline batch.

    Strategy:
      • Load all (business_name, city) pairs already in the DB.
      • Walk the incoming list; for each entry check:
          a) DB cross-check via normalised name+city key.
          b) In-run Jaccard similarity + optional geo proximity vs already-
             accepted entries.
      • Return only the subset of novel, unique businesses.

    Args:
        filtered_data: KPI-passing business dicts from Stage 3.
        session:       Active async SQLAlchemy session for DB look-ups.

    Returns:
        Deduplicated list ready for Stage 5 contact enrichment.
    """
    # ── Load existing DB keys ────────────────────────────────────────────────
    existing: set = set()
    try:
        rows = (
            await session.execute(select(Lead.business_name, Lead.city))
        ).all()
        for row in rows:
            existing.add(_normalize_name(f"{row.business_name}_{row.city}"))
    except Exception as exc:
        logger.info(f"[Dedup] Could not load existing leads: {exc}")

    seen:   list = []
    deduped: list = []

    for biz in filtered_data:
        city   = biz.get("city", "")
        db_key = _normalize_name(f"{biz.get('business_name', '')}_{city}")

        # ── DB cross-check ───────────────────────────────────────────────────
        if db_key in existing:
            logger.info(f"[Dedup] Already in DB: '{biz.get('business_name')}'")
            continue

        # ── In-run similarity check ──────────────────────────────────────────
        norm = _normalize_name(biz.get("business_name", ""))
        lat  = float(biz.get("lat", 0) or 0)
        lng  = float(biz.get("lng", 0) or 0)
        geo  = _geo_hash(lat, lng) if (lat and lng) else None

        is_dup = False
        for s in seen:
            s_norm = _normalize_name(s.get("business_name", ""))
            sim    = _jaccard(norm, s_norm)
            s_lat  = float(s.get("lat", 0) or 0)
            s_lng  = float(s.get("lng", 0) or 0)
            s_geo  = _geo_hash(s_lat, s_lng) if (s_lat and s_lng) else None

            if sim > 0.8 or (sim > 0.6 and geo and s_geo and geo == s_geo):
                is_dup = True
                break

        if not is_dup:
            seen.append(biz)
            deduped.append(biz)

    logger.info(
        f"[Dedup] {len(deduped)}/{len(filtered_data)} unique leads after dedup."
    )
    return deduped
