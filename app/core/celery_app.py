"""
app/core/celery_app.py
─────────────────────────────────────────────────────────────────────────────
Celery application for the Dhampur Green HORECA Lead Intelligence platform.

Architecture: class-based tasks (celery.Task subclasses) registered via
celery_app.register_task() — one class per task, __init__ for dependency
injection, run() as the entry point.

Start worker:
    celery -A app.core.celery_app worker --loglevel=info

Start beat scheduler:
    celery -A app.core.celery_app beat --loglevel=info
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import absolute_import

import asyncio
import logging
import uuid
from datetime import datetime

import celery
from celery import Celery
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

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

logger = logging.getLogger(__name__)

# ─── CELERY APP ───────────────────────────────────────────────────────────────

celery_app = Celery(
    "horeca_pipeline",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
    # Explicitly include this module so beat + worker always discover tasks
    include=["app.core.celery_app"],
)

celery_app.conf.beat_schedule = {
    # Runs the full ETL pipeline for the next city (round-robin) every 7 days
    "weekly-city-pipeline": {
        "task":     "run_city_pipeline",
        "schedule": 604800,  # 7 days
    },
    # Sends follow-up emails to CONTACTED leads with no reply for 3+ days, daily
    "daily-follow-up-emails": {
        "task":     "send_follow_up_emails_task",
        "schedule": 86400,   # 24 hours
        "kwargs":   {"follow_up_after_days": 3},
    },
}
celery_app.conf.timezone = "Asia/Kolkata"

print(celery_app)


# ─── DEBUG TASK ───────────────────────────────────────────────────────────────

@celery_app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")


# ─── ASYNC PIPELINE HELPERS ───────────────────────────────────────────────────

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


async def _async_pipeline():
    """Full async ETL pipeline — called from CityPipelineTask.run()."""
    async with AsyncSessionLocal() as session:

        city = await _select_next_city(session)
        if not city:
            logger.info("[Pipeline] No active cities to process.")
            return

        logger.info(f"[Pipeline] Processing city: {city.name}")

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
            logger.info(f"[Pipeline] City '{city.name}' failed: {exc}", exc_info=True)

        await session.commit()
        await _update_city_last_processed(session, city.id)


# ─── CLASS-BASED TASKS ────────────────────────────────────────────────────────

class CityPipelineTask(celery.Task):
    """
    Weekly HORECA ETL pipeline — round-robin city selection.
    Runs the full 8-stage pipeline for the least recently processed active city.
    Retries up to 3 times on failure with a 60-second delay.
    """
    name              = "run_city_pipeline"
    max_retries       = 3
    default_retry_delay = 60

    def run(self):
        logger.info("[CityPipelineTask] Starting pipeline run")
        try:
            asyncio.run(_async_pipeline())
        except Exception as exc:
            logger.info(f"[CityPipelineTask] Failed: {exc}", exc_info=True)
            raise self.retry(exc=exc)


class BulkEmailTask(celery.Task):
    """
    Bulk outreach — generate + send personalised emails to all 'new' leads
    that have no email or only a draft, then mark each lead as 'contacted'.

    Dispatched by: POST /api/outreach/bulk-send
    Polled via:    GET  /api/outreach/bulk-send/{task_id}
    """
    name = "send_bulk_emails_task"

    def run(self):
        from app.api.outreach import _run_bulk_send
        logger.info("[BulkEmailTask] Starting bulk send")
        return asyncio.run(_run_bulk_send())


class FollowUpEmailTask(celery.Task):
    """
    Follow-up emails — send a follow-up to all 'contacted' leads whose
    initial email is >= follow_up_after_days old with no reply yet.

    Dispatched by: POST /api/outreach/follow-up
    Polled via:    GET  /api/outreach/follow-up/{task_id}
    Auto-runs:     Daily via Celery beat (follow_up_after_days=3)
    """
    name = "send_follow_up_emails_task"

    def run(self, follow_up_after_days: int = 3):
        from app.api.outreach import _run_follow_up
        logger.info(f"[FollowUpEmailTask] Checking leads with no reply for {follow_up_after_days}+ days")
        return asyncio.run(_run_follow_up(follow_up_after_days))


# ─── REGISTER TASKS ───────────────────────────────────────────────────────────

celery_app.register_task(CityPipelineTask())
celery_app.register_task(BulkEmailTask())
celery_app.register_task(FollowUpEmailTask())
