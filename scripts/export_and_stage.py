#!/usr/bin/env python3
"""
export_and_stage.py
-------------------
Small CLI to export selected tables to JSON and import them into a staging DB.

Usage:
  Export: python scripts/export_and_stage.py --export
  Import: python scripts/export_and_stage.py --import --folder exports/2026-04-28_12-00-00 --staging-url postgresql+asyncpg://...

This script uses the existing ORM models and async session in the project.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
import os
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Ensure project root is on PYTHONPATH when running the script directly
# (so `import app` works when executed from the project folder)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import AsyncSessionLocal
from app.db.orm import Lead, Contact, Segment, City, OutreachEmail


TABLES = [
    (Lead, "leads"),
    (Contact, "contacts"),
    (Segment, "segments"),
    (City, "cities"),
    (OutreachEmail, "outreach_emails"),
]


async def export_all(output_dir: Path, filtered: bool = False):
    output_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as session:
        if filtered:
            # Export only leads that have at least one contact with email (email or email_2)
            lead_stmt = select(Lead).where(
                select(Contact.lead_id)
                .where(
                    (Contact.lead_id == Lead.id)
                    & (
                        (Contact.email.isnot(None) & (Contact.email != ""))
                        | (Contact.email_2.isnot(None) & (Contact.email_2 != ""))
                    )
                )
                .exists()
            )
            lead_res = await session.execute(lead_stmt)
            lead_rows = lead_res.scalars().all()
            leads_data = [r.to_dict() for r in lead_rows]

            leads_path = output_dir / "leads.json"
            with leads_path.open("w", encoding="utf-8") as fh:
                json.dump(leads_data, fh, ensure_ascii=False, indent=2)
            print(f"Exported {len(leads_data)} leads -> {leads_path}")

            # Export contacts for those leads but only contacts that have email/email_2
            lead_ids = [r.id for r in lead_rows]
            if lead_ids:
                contact_stmt = select(Contact).where(
                    Contact.lead_id.in_(lead_ids),
                    (
                        (Contact.email.isnot(None) & (Contact.email != ""))
                        | (Contact.email_2.isnot(None) & (Contact.email_2 != ""))
                    ),
                )
                contact_res = await session.execute(contact_stmt)
                contact_rows = contact_res.scalars().all()
                contacts_data = [c.to_dict() for c in contact_rows]
            else:
                contacts_data = []

            contacts_path = output_dir / "contacts.json"
            with contacts_path.open("w", encoding="utf-8") as fh:
                json.dump(contacts_data, fh, ensure_ascii=False, indent=2)
            print(f"Exported {len(contacts_data)} contacts -> {contacts_path}")

        else:
            for model, name in TABLES:
                stmt = select(model)
                result = await session.execute(stmt)
                rows = result.scalars().all()
                data = [getattr(r, "to_dict")() if hasattr(r, "to_dict") else _row_to_dict(r) for r in rows]

                path = output_dir / f"{name}.json"
                with path.open("w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)

                print(f"Exported {len(data)} rows -> {path}")


def _row_to_dict(row):
    # Fallback generic serializer for SQLAlchemy models
    d = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        try:
            if hasattr(val, "isoformat"):
                d[col.name] = val.isoformat()
            else:
                d[col.name] = val
        except Exception:
            d[col.name] = None
    return d


async def import_all(folder: Path, staging_url: str):
    if not folder.exists():
        raise SystemExit(f"Folder not found: {folder}")

    engine = create_async_engine(staging_url, echo=False)
    Factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Factory() as session:
        for model, name in TABLES:
            path = folder / f"{name}.json"
            if not path.exists():
                print(f"Skipping missing file: {path}")
                continue

            with path.open("r", encoding="utf-8") as fh:
                items = json.load(fh)

            instances = []
            # Known datetime-like column names used across models
            datetime_fields = {
                "created_at",
                "updated_at",
                "generated_at",
                "sent_at",
                "last_processed_at",
                "started_at",
                "completed_at",
            }

            for it in items:
                # Prepare a mutable copy and coerce datetimes from ISO strings
                data = dict(it)
                for k in list(data.keys()):
                    v = data[k]
                    if k in datetime_fields and isinstance(v, str) and v:
                        try:
                            data[k] = datetime.fromisoformat(v)
                        except Exception:
                            # leave as-is if parsing fails
                            pass

                # Create instance while preserving provided keys
                try:
                    inst = model(**data)
                except Exception:
                    # Try removing primary key if constructor fails
                    pdata = dict(data)
                    pk = None
                    if hasattr(model, "__table__"):
                        for col in model.__table__.primary_key.columns:
                            pk = col.name
                    if pk and pk in pdata:
                        pdata.pop(pk)
                    inst = model(**pdata)

                instances.append(inst)

            if not instances:
                print(f"No rows to import for {name}")
                continue

            for inst in instances:
                session.add(inst)
            try:
                await session.commit()
                print(f"Inserted {len(instances)} rows into {name}")
            except IntegrityError as e:
                await session.rollback()
                print(f"IntegrityError while inserting into {name}: {e}. Attempting row-by-row insert.")
                count = 0
                for inst in instances:
                    try:
                        session.add(inst)
                        await session.commit()
                        count += 1
                    except IntegrityError:
                        await session.rollback()
                print(f"Inserted {count}/{len(instances)} new rows into {name}")

    await engine.dispose()


def _default_exports_dir() -> Path:
    t = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    return Path("exports") / t


def main():
    parser = argparse.ArgumentParser(description="Export and import tables for staging")
    parser.add_argument("--export", action="store_true", help="Export tables to JSON files")
    parser.add_argument("--export-filtered", dest="export_filtered", action="store_true", help="Export only leads that have at least one contact with an email and those contacts")
    parser.add_argument("--import", dest="do_import", action="store_true", help="Import JSON files into staging DB")
    parser.add_argument("--folder", type=str, help="Folder containing exported JSON files (for import)")
    parser.add_argument("--staging-url", type=str, help="Staging DATABASE_URL (async driver) e.g. postgresql+asyncpg://user:pass@host/db")

    args = parser.parse_args()

    if not args.export and not args.do_import:
        parser.print_help()
        raise SystemExit(1)

    if args.export:
        out = _default_exports_dir()
        print(f"Exporting to {out}")
        asyncio.run(export_all(out, filtered=args.export_filtered))

    if args.do_import:
        folder = Path(args.folder) if args.folder else Path("exports")
        staging_url = args.staging_url or os.getenv("STAGING_DATABASE_URL") or os.getenv("DATABASE_URL")
        if not staging_url:
            raise SystemExit("Please provide --staging-url or set STAGING_DATABASE_URL in env")

        print(f"Importing from {folder} into {staging_url}")
        asyncio.run(import_all(folder, staging_url))


if __name__ == "__main__":
    main()
