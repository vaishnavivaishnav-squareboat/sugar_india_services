"""
app/agents/tools/generate_email.py
─────────────────────────────────────────────────────────────────────────────
Tool: generate_email — Stage 7 (Personalized Email Generation)

Mirrors: agents/src/tools/generateEmail.js
The Email Generator Agent calls this once it has composed the full outreach
email. The tool appends the email to a JSONL log file and returns the result.
─────────────────────────────────────────────────────────────────────────────
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from agents import function_tool

logger = logging.getLogger(__name__)

# Append generated emails to sugar_india_services/generated_emails.jsonl
_EMAILS_FILE = Path(__file__).resolve().parents[3] / "generated_emails.jsonl"


@function_tool
def generate_email(
    lead_name: Annotated[str, "Business name of the lead"],
    lead_city: Annotated[str, "City where the lead is located"],
    lead_segment: Annotated[str, "HORECA segment of the lead"],
    contact_name: Annotated[
        str,
        "First name of the decision-maker to address, or empty string",
    ],
    subject: Annotated[
        str,
        "Email subject line — specific, personalized, professional",
    ],
    body: Annotated[
        str,
        (
            "Full email body including: greeting addressing contact by name, "
            "personalized value proposition, Dhampur Green product benefits, "
            "clear soft CTA (sample request or 15-min call), "
            "and sign-off from Arjun Mehta | Regional Sales Manager, Dhampur Green"
        ),
    ],
) -> str:
    """
    Records and saves the finalized personalized outreach email for a HORECA lead.
    Call this with the complete subject line and email body once you have written
    the email. The email should be 150–200 words, professionally written, and
    include a clear CTA.
    """
    record = {
        "lead_name":    lead_name,
        "lead_city":    lead_city,
        "lead_segment": lead_segment,
        "contact_name": contact_name,
        "subject":      subject,
        "body":         body,
        "status":       "draft",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with _EMAILS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        logger.warning(f"  [TOOL: generate_email] Could not write to JSONL: {exc}")

    logger.info(
        f"  [TOOL: generate_email] ✅ Email saved for '{lead_name}' — Subject: '{subject}'"
    )
    return json.dumps({"subject": subject, "body": body})
