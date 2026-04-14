"""
app/core/cron.py
─────────────────────────────────────────────────────────────────────────────
Weekly cron script that runs the full 8-stage HORECA lead pipeline for
EVERY active city configured in the database.

Unlike celery_app.py (which round-robins one city per Celery invocation),
this script processes ALL active cities in sequence in a single run.

──────────────────────────────────────────────────────────────────────────────
SETUP — add to crontab:
    crontab -e

    # Every Monday at 02:00 AM IST
    0 2 * * 1  cd "/path/to/sugar_india_services" && source venv/bin/activate && python -m app.core.cron >> logs/cron_pipeline.log 2>&1

──────────────────────────────────────────────────────────────────────────────
MANUAL RUN:
    cd sugar_india_services
    source venv/bin/activate
    python -m app.core.cron                          # all active cities
    python -m app.core.cron --city Mumbai            # single city override
    python -m app.core.cron --city Mumbai --dry-run  # dry-run, no API calls
──────────────────────────────────────────────────────────────────────────────
"""

import asyncio
import argparse
import fcntl
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure sugar_india_services/ is on sys.path so app.* imports resolve
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from sqlalchemy import select, update

from app.db.session import AsyncSessionLocal
from app.db.orm import City, PipelineRun
import app.pipelines.stages as ps

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("cron_pipeline")

# ── Lock file (prevents overlapping cron runs) ────────────────────────────────
LOCK_FILE = ROOT_DIR / "cron_pipeline.lock"


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _separator(char: str = "─", width: int = 64) -> str:
    return char * width


async def _get_active_cities(session, city_name_override: str = None) -> list:
    q    = select(City).where(City.is_active == True).order_by(City.priority.desc())
    rows = (await session.execute(q)).scalars().all()
    if city_name_override:
        rows = [c for c in rows if c.name.lower() == city_name_override.lower()]
    return rows


async def _create_pipeline_run(session, city: City) -> PipelineRun:
    run = PipelineRun(
        ulid=str(uuid.uuid4()),
        city_id=city.id,
        status="running",
        started_at=datetime.now(timezone.utc),
        logs={},
    )
    session.add(run)
    await session.commit()
    return run


async def _log_stage(run: PipelineRun, session, stage: str, msg: str):
    logs = run.logs or {}
    logs[stage] = {"message": msg, "at": datetime.now(timezone.utc).isoformat()}
    run.logs = logs
    await session.commit()


async def _mark_city_processed(session, city: City):
    await session.execute(
        update(City)
        .where(City.id == city.id)
        .values(last_processed_at=datetime.now(timezone.utc))
    )
    await session.commit()


# ══════════════════════════════════════════════════════════════════════════════
# SINGLE CITY PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

async def run_pipeline_for_city(city: City, dry_run: bool = False) -> dict:
    """
    Runs all 8 ETL stages for one city.
    Returns a summary dict with counts and status.
    """
    city_name = city.name
    logger.info(_separator("═"))
    logger.info(f"  City: {city_name}  |  {'DRY-RUN' if dry_run else 'LIVE'}")
    logger.info(_separator("═"))

    summary = {
        "city": city_name, "status": "failed",
        "extracted": 0, "ai_enriched": 0, "kpi_passed": 0,
        "deduped": 0, "emails_generated": 0, "stored": 0, "error": None,
    }

    async with AsyncSessionLocal() as session:
        run = await _create_pipeline_run(session, city)

        try:
            # ── Stage 1: Extract ──────────────────────────────────────────
            await _log_stage(run, session, "stage_1", "Starting extraction")
            if dry_run:
                from tests.test_pipeline import MOCK_BUSINESSES
                raw = [b for b in MOCK_BUSINESSES]
                logger.info(f"[DRY-RUN] Using {len(raw)} mock businesses")
            else:
                raw = await ps.extract_business_data(city_name, session)
            summary["extracted"] = len(raw)
            await _log_stage(run, session, "stage_1", f"Extracted {len(raw)} raw businesses")
            logger.info(f"  Stage 1 ✓  →  {len(raw)} businesses extracted")

            if not raw:
                logger.warning(f"  Stage 1 returned 0 results for {city_name!r} — aborting.")
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc)
                await session.commit()
                await _mark_city_processed(session, city)
                summary["status"] = "completed"
                return summary

            # ── Stage 2: AI Processing ─────────────────────────────────────
            await _log_stage(run, session, "stage_2", "Starting AI processing")
            if dry_run:
                for b in raw:
                    b.update({
                        "has_dessert_menu":             b["segment"] in ["Bakery", "Cafe"],
                        "monthly_sugar_estimate_kg":    400 if b["segment"] == "Bakery" else 120,
                        "sweetness_dependency_pct":     70  if b["segment"] == "Bakery" else 35,
                        "sugar_signal_from_highlights": False,
                        "highlight_sugar_signals":      [],
                        "ai_reasoning":                 "Mock: high sugar dependency",
                        "is_chain":                     bool(b.get("is_chain", False)),
                        "hotel_category":               "",
                    })
                ai_enriched = raw
            else:
                ai_enriched = await ps.ai_process_business_data(raw, session)
            summary["ai_enriched"] = len(ai_enriched)
            await _log_stage(run, session, "stage_2", f"AI processed {len(ai_enriched)} businesses")
            logger.info(f"  Stage 2 ✓  →  {len(ai_enriched)} AI-enriched")

            # ── Stage 3: KPI Filtering ─────────────────────────────────────
            await _log_stage(run, session, "stage_3", "Starting KPI filtering")
            filtered = await ps.apply_kpi_filtering(ai_enriched, session)
            summary["kpi_passed"] = len(filtered)
            await _log_stage(run, session, "stage_3", f"{len(filtered)}/{len(ai_enriched)} passed KPI")
            logger.info(f"  Stage 3 ✓  →  {len(filtered)} passed KPI filter")

            # ── Stage 4: Deduplication ─────────────────────────────────────
            await _log_stage(run, session, "stage_4", "Starting deduplication")
            deduped = await ps.deduplicate_leads(filtered, session)
            summary["deduped"] = len(deduped)
            await _log_stage(run, session, "stage_4", f"{len(deduped)} unique leads")
            logger.info(f"  Stage 4 ✓  →  {len(deduped)} unique leads after dedup")

            # ── Stage 5: Contact Enrichment ────────────────────────────────
            await _log_stage(run, session, "stage_5", "Starting contact enrichment")
            if dry_run:
                for b in deduped:
                    b["decision_maker_name"]     = "Priya Sharma (mock)"
                    b["decision_maker_role"]     = "F&B Manager"
                    b["decision_maker_linkedin"] = ""
                    b["contacts"]                = []
                with_contacts = deduped
            else:
                with_contacts = await ps.enrich_contacts(deduped, session)
            await _log_stage(run, session, "stage_5", "Contact enrichment done")
            logger.info("  Stage 5 ✓  →  contact enrichment done")

            # ── Stage 6: Email Enrichment ──────────────────────────────────
            await _log_stage(run, session, "stage_6", "Starting email enrichment")
            with_emails = with_contacts if dry_run else await ps.enrich_emails(with_contacts, session)
            await _log_stage(run, session, "stage_6", "Email enrichment done")
            logger.info("  Stage 6 ✓  →  email enrichment done")

            # ── Stage 7: Email Generation ──────────────────────────────────
            await _log_stage(run, session, "stage_7", "Starting email generation")
            if dry_run:
                email_items = [{
                    "lead_name":    b.get("business_name"),
                    "lead_city":    b.get("city"),
                    "lead_segment": b.get("segment"),
                    "subject":      f"Sugar Supply Partnership — {b.get('business_name')} (Dhampur Green)",
                    "body":         f"[Dry-run email for {b.get('business_name')}]",
                    "status":       "draft",
                    "business":     b,
                } for b in with_emails]
            else:
                email_items = await ps.generate_personalized_emails(with_emails, session)
            summary["emails_generated"] = len(email_items)
            await _log_stage(run, session, "stage_7", f"{len(email_items)} emails generated")
            logger.info(f"  Stage 7 ✓  →  {len(email_items)} emails generated")

            # ── Stage 8: Store to DB ───────────────────────────────────────
            await _log_stage(run, session, "stage_8", "Storing to DB")
            success = await ps.store_leads_and_emails(email_items, session)
            stored  = len(email_items) if success else 0
            summary["stored"] = stored
            await _log_stage(
                run, session, "stage_8",
                f"Stored {stored} leads" if success else "Storage partially failed",
            )
            logger.info(f"  Stage 8 ✓  →  {stored} leads + emails stored to DB")

            run.status       = "completed"
            run.completed_at = datetime.now(timezone.utc)
            await session.commit()
            summary["status"] = "completed"

        except Exception as exc:
            run.status       = "failed"
            run.completed_at = datetime.now(timezone.utc)
            logs = run.logs or {}
            logs["error"] = str(exc)
            run.logs = logs
            await session.commit()
            summary["error"] = str(exc)
            logger.error(f"  ✗ Pipeline failed for {city_name!r}: {exc}", exc_info=True)

        finally:
            await _mark_city_processed(session, city)

    return summary


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

async def main(city_override: str = None, dry_run: bool = False):
    started_at = datetime.now(timezone.utc)

    print(_separator("━"))
    print(f"  HORECA Cron Pipeline  |  {started_at.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Mode: {'🏜  Dry-run (mock data)' if dry_run else '🌐  Live (real API calls)'}")
    print(_separator("━"))

    async with AsyncSessionLocal() as session:
        cities = await _get_active_cities(session, city_override)

    if not cities:
        msg = (
            f"No active city found matching '{city_override}'"
            if city_override
            else "No active cities configured. Add cities via the admin panel."
        )
        logger.warning(f"  ⚠️  {msg}")
        return

    logger.info(f"  Cities to process: {[c.name for c in cities]}")

    all_summaries = []
    for i, city in enumerate(cities, 1):
        print(f"\n[{i}/{len(cities)}] Processing: {city.name}")
        summary = await run_pipeline_for_city(city, dry_run=dry_run)
        all_summaries.append(summary)

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    print(f"\n{_separator('═')}")
    print(f"  CRON RUN COMPLETE  |  elapsed: {elapsed:.0f}s")
    print(_separator("═"))
    print(f"  {'City':<20} {'Status':<12} {'Extracted':>10} {'Stored':>8}")
    print(f"  {_separator('-', 54)}")
    for s in all_summaries:
        status_icon = "✅" if s["status"] == "completed" else "❌"
        print(
            f"  {s['city']:<20} {status_icon} {s['status']:<10} "
            f"{s['extracted']:>10} {s['stored']:>8}"
        )
    print(_separator("━"))


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Weekly cron script — runs HORECA pipeline for all active cities"
    )
    parser.add_argument("--city",     default=None, help="Process only this city")
    parser.add_argument("--dry-run",  action="store_true", help="Use mock data — skips real API calls")
    parser.add_argument("--no-lock",  action="store_true", help="Skip the lock file check")
    args = parser.parse_args()

    if not args.no_lock:
        lock_fh = open(LOCK_FILE, "w")
        try:
            fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("⚠️  Another cron_pipeline is already running. Exiting.")
            sys.exit(0)

    try:
        asyncio.run(main(city_override=args.city, dry_run=args.dry_run))
    finally:
        if not args.no_lock:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)
            lock_fh.close()
            try:
                LOCK_FILE.unlink()
            except FileNotFoundError:
                pass
