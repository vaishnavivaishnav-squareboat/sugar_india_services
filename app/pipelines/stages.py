"""
app/pipelines/stages.py
─────────────────────────────────────────────────────────────────────────────
ETL pipeline stage functions for the HORECA lead generation system.

This file is intentionally thin — each stage function is a one- or two-line
delegate that calls the corresponding service module where all real logic
lives. This mirrors the existing pattern used by Stage 5 and Stage 6.

Stage → Service module mapping:
  1. extract_business_data        → app/services/extraction/extraction_service.py
  2. ai_process_business_data     → app/services/classification/classification_service.py
  3. apply_kpi_filtering          → app/services/filtering/kpi_service.py
  4. deduplicate_leads            → app/services/deduplication/dedup_service.py
  5. enrich_contacts              → app/services/enrichment/contact_service.py
  6. enrich_emails                → app/services/enrichment/email_service.py
  7. generate_personalized_emails → app/services/email_generation/email_gen_service.py
  8. store_leads_and_emails       → app/services/storage/storage_service.py
─────────────────────────────────────────────────────────────────────────────
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

# ── Stage services ────────────────────────────────────────────────────────────
from app.services.extraction.extraction_service         import extract_businesses        as _service_extract
from app.services.classification.classification_service import classify_businesses       as _service_classify
from app.services.filtering.kpi_service                 import filter_by_kpi            as _service_filter_kpi
from app.services.deduplication.dedup_service           import deduplicate_businesses   as _service_deduplicate
from app.services.enrichment.contact_service            import enrich_leads_contacts    as _service_enrich_contacts
from app.services.enrichment.email_service              import enrich_leads_emails      as _service_enrich_emails
from app.services.email_generation.email_gen_service    import generate_emails_for_leads as _service_generate_emails
from app.services.storage.storage_service               import store_pipeline_results   as _service_store

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 – DATA EXTRACTION - Extraction of businesses from SERPAPI/SEARCHAPI based on city and segment keywords
# ══════════════════════════════════════════════════════════════════════════════

async def extract_business_data(
    city: str,
    session: AsyncSession,
    segment_filter: str | None = None,
    max_pages: int = 1,
    hunter_limit: int = 10,
) -> list:
    """
    Stage 1: Discover HORECA businesses via SerpAPI Google Maps + Hunter Discover.
    Delegates to app.services.extraction.extraction_service.

    Credit-saving knobs:
      max_pages    — SerpAPI pages per query (1 = 20 results, 1 credit; 3 = 60 results, 3 credits)
      hunter_limit — Hunter Discover results per query (costs 1 Hunter credit regardless of limit)
    """
    return await _service_extract(city, segment_filter, max_pages=max_pages, hunter_limit=hunter_limit)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2 – AI CLASSIFICATION - AI enrichment (Business Intelligence Agent - sugar estimates, etc)
# ══════════════════════════════════════════════════════════════════════════════

async def ai_process_business_data(raw_data: list, session: AsyncSession) -> list:
    """
    Stage 2: Enrich each business with OpenAI — menu classification, sugar
    estimate, sweetness dependency. Delegates to
    app.services.classification.classification_service.
    """
    return await _service_classify(raw_data)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 3 – KPI FILTERING
# ══════════════════════════════════════════════════════════════════════════════

async def apply_kpi_filtering(ai_data: list, session: AsyncSession) -> list:
    """
    Stage 3: Score every business and discard those below the KPI threshold.
    Delegates to app.services.filtering.kpi_service.
    """
    return await _service_filter_kpi(ai_data)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 4 – DEDUPLICATION
# ══════════════════════════════════════════════════════════════════════════════

async def deduplicate_leads(filtered_data: list, session: AsyncSession) -> list:
    """
    Stage 4: Remove duplicates using Jaccard name similarity + geo proximity
    and cross-check against existing DB leads. Delegates to
    app.services.deduplication.dedup_service.
    """
    return await _service_deduplicate(filtered_data, session)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 5 – CONTACT ENRICHMENT - including LinkedIn snippets retrieval
# ══════════════════════════════════════════════════════════════════════════════

async def enrich_contacts(leads: list, session: AsyncSession) -> list:
    """
    Stage 5: Delegates to app.services.enrichment.contact_service.
    SerpAPI search for decision-maker signals + OpenAI extraction.
    """
    return await _service_enrich_contacts(leads)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 6 – EMAIL FINDING/ENRICHMENT - finding email addresses for the discovered contacts + using business domain
# ══════════════════════════════════════════════════════════════════════════════

async def enrich_emails(businesses: list, session: AsyncSession) -> list:
    """
    Stage 6: Delegates to app.services.enrichment.email_service.
    Hunter.io → Apollo.io → Snov.io → Pattern generation fallback chain.
    """
    return await _service_enrich_emails(businesses)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 7 – PERSONALIZED EMAIL GENERATION
# ══════════════════════════════════════════════════════════════════════════════

async def generate_personalized_emails(enriched_leads: list, session: AsyncSession) -> list:
    """
    Stage 7: Generate a personalized outreach email per qualified lead.
    Delegates to app.services.email_generation.email_gen_service.
    """
    return await _service_generate_emails(enriched_leads)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 8 – STORAGE - Store leads and emails to DB
# ══════════════════════════════════════════════════════════════════════════════

async def store_leads_and_emails(final_leads: list, session: AsyncSession) -> bool:
    """
    Stage 8: Persist Lead, Contact, and OutreachEmail records to the DB.
    Delegates to app.services.storage.storage_service.
    """
    return await _service_store(final_leads, session)
