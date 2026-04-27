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
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import aiosmtplib

from app.core.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
from app.db.session import AsyncSessionLocal
from app.db.orm import Lead
from app.core.constants import LeadStatus
from sqlalchemy import select

# Rate list attached to every outreach email
_RATE_LIST_PATH = (
    Path(__file__).resolve().parents[2]
    / "documents"
    / "DhampurGreen_HOReCa_RateList_2026.html"
)


async def send_email(
    to_email: str,
    subject: str,
    body: str,
    lead_id: str = None,
    attachment_path: Path | None = _RATE_LIST_PATH,
) -> None:
    """Send a plain-text outreach email with an optional file attachment.

    By default attaches the HOReCa Rate List 2026 HTML file.
    Pass attachment_path=None to send without any attachment.
    Optionally updates the lead status to CONTACTED when lead_id is provided.
    """

    # # ── DUMMY ── (active by default) ──────────────────────────────────────
    # # Simulates a send: logs to console, does NOT hit any mail server.
    # attachment_note = (
    #     f" + attachment: {attachment_path.name}"
    #     if attachment_path and attachment_path.exists()
    #     else " (no attachment)"
    # )
    # print(f"[DUMMY EMAIL] To: {to_email} | Subject: {subject}{attachment_note}")
    # await asyncio.sleep(0.1)   # mimic network latency
    # # ── END DUMMY ─────────────────────────────────────────────────────────

    # ── REAL ── (uncomment when ready to send live emails) ────────────────
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = SMTP_FROM or SMTP_USER
    msg["To"]      = to_email
    
    # Plain-text body
    msg.attach(MIMEText(body, "plain"))
    
    # Attach rate list if the file exists
    if attachment_path and attachment_path.exists():
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment_path.read_bytes())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=attachment_path.name,
        )
        msg.attach(part)
    
    await aiosmtplib.send(
        msg,
        hostname  = SMTP_HOST,
        port      = SMTP_PORT,
        username  = SMTP_USER,
        password  = SMTP_PASSWORD,
        start_tls = True,
    )
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
