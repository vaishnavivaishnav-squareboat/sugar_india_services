"""
app/utils/smtp.py
─────────────────────────────────────────────────────────────────────────────
Async email-sending utility for Dhampur Green outreach.

Usage
-----
from app.utils.smtp import send_email

await send_email(to_email="buyer@hotel.com", subject="...", body="...")

Switch between DUMMY and REAL
─────────────────────────────
By default the function logs to console and does NOT send a real email.
When you're ready to go live:
  1. Fill in SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM in .env
  2. In send_email() below, comment out the DUMMY block and uncomment the REAL block.
─────────────────────────────────────────────────────────────────────────────
"""
import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.core.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
from app.db.session import AsyncSessionLocal
from app.db.orm import Lead
from app.core.constants import LeadStatus
from sqlalchemy import select

async def send_email(to_email: str, subject: str, body: str, lead_id: str = None) -> None:
    """Send a plain-text outreach email and optionally update lead status to CONTACTED."""

    # ── DUMMY ── (active by default) ──────────────────────────────────────
    # Simulates a send: logs to console, does NOT hit any mail server.
    print(f"[DUMMY EMAIL] To: {to_email} | Subject: {subject}")
    await asyncio.sleep(0.1)   # mimic network latency
    # ── END DUMMY ─────────────────────────────────────────────────────────

    # ── REAL ── (uncomment when ready to send live emails) ────────────────
    # msg = MIMEMultipart("alternative")
    # msg["Subject"] = subject
    # msg["From"]    = SMTP_FROM or SMTP_USER
    # msg["To"]      = to_email
    # msg.attach(MIMEText(body, "plain"))
    #
    # await aiosmtplib.send(
    #     msg,
    #     hostname  = SMTP_HOST,
    #     port      = SMTP_PORT,
    #     username  = SMTP_USER,
    #     password  = SMTP_PASSWORD,
    #     start_tls = True,
    # )
    # ── END REAL ──────────────────────────────────────────────────────────

    # Update lead status if lead_id is provided
    if lead_id:
        async with AsyncSessionLocal() as session:
            lead = (await session.execute(
                select(Lead).where(Lead.id == lead_id)
            )).scalar_one_or_none()
            if lead and lead.status != LeadStatus.CONTACTED:
                lead.status = LeadStatus.CONTACTED
                await session.commit()
