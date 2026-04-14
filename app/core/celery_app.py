"""
app/core/celery_app.py
─────────────────────────────────────────────────────────────────────────────
Celery application + weekly city-based HORECA ETL pipeline task.

Unlike cron.py (which processes ALL cities per run), this processes ONE city
per invocation using a round-robin selection strategy.

Start worker:
    celery -A app.core.celery_app worker --loglevel=info

Start beat scheduler:
    celery -A app.core.celery_app beat --loglevel=info
─────────────────────────────────────────────────────────────────────────────
"""
from celery import Celery
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.db.orm import City, PipelineRun
from app.db.session import AsyncSessionLocal
from app.pipelines.stages import (
    extract_business_data,
    ai_process_business_data,
    apply_kpi_filtering,
    deduplicate_leads,
    enrich_contacts,
    enrich_emails,
    generate_personalized_emails,
    store_leads_and_emails,
)

import logging
import asyncio
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

# ─── CELERY APP ───────────────────────────────────────────────────────────────

celery_app = Celery(
    "horeca_pipeline",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)

# Weekly beat schedule: every Monday at 02:00 AM IST
celery_app.conf.beat_schedule = {
    "weekly-city-pipeline": {
        "task":     "app.core.celery_app.run_city_pipeline",
        "schedule": 604800,  # 7 days in seconds
    },
}
celery_app.conf.timezone = "Asia/Kolkata"


# ─── HELPERS ─────────────────────────────────────────────────────────────────

async def _select_next_city(session: AsyncSession):
    """Round-robin: pick the active city least recently processed."""
    result = await session.execute(
        select(City)
        .where(City.is_active == True)
        .order_by(City.last_processed_at.asc().nullsfirst(), City.priority.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _update_city_last_processed(session: AsyncSession, city_id: int):
    await session.execute(
        update(City)
        .where(City.id == city_id)
        .values(last_processed_at=datetime.utcnow())
    )
    await session.commit()


async def _append_log(pipeline_run: PipelineRun, session: AsyncSession, stage: str, msg: str):
    """Append a timestamped log entry to the pipeline run record."""
    logs = pipeline_run.logs or {}
    logs[stage] = {"message": msg, "at": datetime.utcnow().isoformat()}
    pipeline_run.logs = logs
    await session.commit()


# ─── MAIN CELERY TASK ────────────────────────────────────────────────────────

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_city_pipeline(self):
    """
    Main Celery entry point for the weekly city-based HORECA pipeline.
    Celery tasks are synchronous; async stages are run via asyncio.run().
    """
    asyncio.run(_async_pipeline())


async def _async_pipeline():
    """Full async ETL pipeline – called from the Celery task wrapper."""
    async with AsyncSessionLocal() as session:

        # ── Step 1: City selection (round-robin) ──────────────────────────
        city = await _select_next_city(session)
        if not city:
            logger.info("[Pipeline] No active cities to process.")
            return

        logger.info(f"[Pipeline] Processing city: {city.name}")

        # ── Step 2: Create pipeline run record ────────────────────────────
        pipeline_run = PipelineRun(
            ulid=str(uuid.uuid4()),
            city_id=city.id,
            status="running",
            started_at=datetime.utcnow(),
            logs={},
        )
        session.add(pipeline_run)
        await session.commit()

        try:
            await _append_log(pipeline_run, session, "stage_1", "Starting extraction")
            raw = await extract_business_data(city.name, session)
            await _append_log(pipeline_run, session, "stage_1", f"Extracted {len(raw)} raw businesses")

            await _append_log(pipeline_run, session, "stage_2", "Starting AI processing")
            ai_enriched = await ai_process_business_data(raw, session)
            await _append_log(pipeline_run, session, "stage_2", f"AI processed {len(ai_enriched)} businesses")

            await _append_log(pipeline_run, session, "stage_3", "Starting KPI filtering")
            filtered = await apply_kpi_filtering(ai_enriched, session)
            await _append_log(pipeline_run, session, "stage_3", f"{len(filtered)} passed KPI filter")

            await _append_log(pipeline_run, session, "stage_4", "Starting deduplication")
            deduped = await deduplicate_leads(filtered, session)
            await _append_log(pipeline_run, session, "stage_4", f"{len(deduped)} unique leads")

            await _append_log(pipeline_run, session, "stage_5", "Starting contact enrichment")
            with_contacts = await enrich_contacts(deduped, session)
            await _append_log(pipeline_run, session, "stage_5", "Contact enrichment done")

            await _append_log(pipeline_run, session, "stage_6", "Starting email enrichment")
            with_emails = await enrich_emails(with_contacts, session)
            await _append_log(pipeline_run, session, "stage_6", "Email enrichment done")

            await _append_log(pipeline_run, session, "stage_7", "Starting email generation")
            email_items = await generate_personalized_emails(with_emails, session)
            await _append_log(pipeline_run, session, "stage_7", f"{len(email_items)} emails generated")

            await _append_log(pipeline_run, session, "stage_8", "Storing results")
            success = await store_leads_and_emails(email_items, session)
            await _append_log(
                pipeline_run, session, "stage_8",
                "Stored successfully" if success else "Storage partially failed",
            )

            pipeline_run.status       = "completed"
            pipeline_run.completed_at = datetime.utcnow()
            logger.info(f"[Pipeline] City '{city.name}' completed. {len(email_items)} leads stored.")

        except Exception as exc:
            pipeline_run.status       = "failed"
            pipeline_run.completed_at = datetime.utcnow()
            logs = pipeline_run.logs or {}
            logs["error"] = str(exc)
            pipeline_run.logs = logs
            logger.error(f"[Pipeline] City '{city.name}' failed: {exc}", exc_info=True)

        await session.commit()

        # ── Step 3: Mark city as processed ────────────────────────────────
        await _update_city_last_processed(session, city.id)
