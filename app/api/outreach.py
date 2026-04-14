"""
app/api/routes/outreach.py
─────────────────────────────────────────────────────────────────────────────
All /outreach/* endpoints for the HORECA Lead Intelligence API.
─────────────────────────────────────────────────────────────────────────────
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import desc, select

from app.db.session import AsyncSessionLocal
from app.db.orm import OutreachEmail
from app.utils import model_to_dict

outreach_router = APIRouter(prefix="/outreach")


@outreach_router.get("/emails")
async def get_all_emails(limit: int = 50):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OutreachEmail).order_by(desc(OutreachEmail.generated_at)).limit(limit)
        )
        return [model_to_dict(e) for e in result.scalars()]


@outreach_router.get("/{lead_id}/emails")
async def get_lead_emails(lead_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OutreachEmail)
            .where(OutreachEmail.lead_id == lead_id)
            .order_by(desc(OutreachEmail.generated_at))
            .limit(20)
        )
        return [model_to_dict(e) for e in result.scalars()]


@outreach_router.put("/{email_id}/mark-sent")
async def mark_email_sent(email_id: str):
    async with AsyncSessionLocal() as session:
        email = (await session.execute(
            select(OutreachEmail).where(OutreachEmail.id == email_id)
        )).scalar_one_or_none()
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        email.status  = "sent"
        email.sent_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(email)
        return model_to_dict(email)
