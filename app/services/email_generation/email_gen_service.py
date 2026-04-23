"""
app/services/email_generation/email_gen_service.py
─────────────────────────────────────────────────────────────────────────────
Stage 7 — Personalized Outreach Email Generation.

For each enriched lead, calls OpenAI with the lead_email_api prompt to
produce a 150-200 word outreach email (SUBJECT line + body).

Raw model output format expected:
    SUBJECT: <subject line>

    Dear <name>,
    <body text>

This is the clean, modular replacement for the inline
generate_personalized_emails() function in stages.py. stages.py delegates
to this service.
─────────────────────────────────────────────────────────────────────────────
"""
import logging

from app.agents.prompts.lead_email_api import lead_email_api_prompt
from app.core.openai_client import call_openai
from app.core.constants import EmailStatus

logger = logging.getLogger(__name__)


def _parse_email_output(raw: str) -> tuple[str, str]:
    """
    Split raw model output into (subject, body).

    Expects the first line starting with "SUBJECT:" to carry the subject;
    everything else is concatenated as the body.
    """
    subject, body_lines, past_subject = "", [], False
    for line in raw.strip().split("\n"):
        if line.startswith("SUBJECT:") and not past_subject:
            subject     = line.replace("SUBJECT:", "").strip()
            past_subject = True
        else:
            body_lines.append(line)
    return subject, "\n".join(body_lines).strip()


async def generate_email_for_contact(biz: dict, contact: dict) -> dict | None:
    """
    Generate a personalised outreach email for a single contact of a business.

    Args:
        biz:     Enriched business dict from Stage 6.
        contact: A single contact dict (must have a non-empty "email" field).

    Returns:
        Email dict ready for Stage 8 storage, or None on failure.
        Shape: { lead_name, lead_city, lead_segment, subject, body, status,
                 sent_to_email, sent_to_name, business }
    """
    name         = biz.get("business_name", "")
    city         = biz.get("city", "")
    segment      = biz.get("segment", "Restaurant")
    contact_name = contact.get("name", "") or biz.get("decision_maker_name", "")
    contact_role = contact.get("role", "") or biz.get("decision_maker_role", "Procurement Team")
    has_dessert  = biz.get("has_dessert_menu", False)
    sugar_kg     = biz.get("monthly_sugar_estimate_kg", 0)
    reasoning    = biz.get("ai_reasoning", "")
    rating       = biz.get("rating", 0)
    hotel_cat    = biz.get("hotel_category", "")

    prompt = lead_email_api_prompt(
        business_name=name,
        city=city,
        segment=segment,
        dm=contact_name,
        first_name=contact_name.split()[0] if contact_name else "Team",
        role=contact_role,
        has_dessert_menu=has_dessert,
        monthly_volume_estimate=f"{sugar_kg} kg",
        rating=rating,
        num_outlets=biz.get("num_outlets", 1),
        reasoning=reasoning,
    )
    try:
        raw           = await call_openai(prompt)  # plain text, not forced JSON
        subject, body = _parse_email_output(raw)
        logger.info(f"[EmailGen] Generated email for '{name}' → {contact.get('email')}")
        return {
            "lead_name":     name,
            "lead_city":     city,
            "lead_segment":  segment,
            "subject":       subject,
            "body":          body,
            "status":        EmailStatus.DRAFT,
            "sent_to_email": contact.get("email", ""),
            "sent_to_name":  contact_name,
            "business":      biz,
        }
    except Exception as exc:
        logger.info(f"[EmailGen] Failed for '{name}' / '{contact.get('email')}': {exc}")
        return None


async def generate_email_for_lead(biz: dict) -> dict | None:
    """
    Backward-compatible single-email wrapper (primary contact only).
    Delegates to generate_email_for_contact using the is_primary contact,
    or falls back to decision_maker_name fields.
    """
    contacts_with_email = [c for c in biz.get("contacts", []) if c.get("email")]
    primary = next((c for c in contacts_with_email if c.get("is_primary")), None)
    if not primary and contacts_with_email:
        primary = max(contacts_with_email, key=lambda c: c.get("relevance_score", 0))
    if not primary:
        # No enriched contact — build a stub from decision_maker fields
        primary = {
            "name":  biz.get("decision_maker_name", ""),
            "role":  biz.get("decision_maker_role", ""),
            "email": biz.get("email", ""),
        }
    return await generate_email_for_contact(biz, primary)



# ── START ────────────────────────────────────────────────────────
async def generate_emails_for_leads(enriched_leads: list[dict]) -> list[dict]:
    """
    Generate one personalised email per contact-with-email per lead.

    For every contact that has an email address (from Stage 5 or Stage 6),
    a separate outreach email is generated and returned so Stage 8 can store
    an OutreachEmail row per recipient.

    Args:
        enriched_leads: Contact/email-enriched business dicts from Stage 6.

    Returns:
        List of email dicts ready for Stage 8 storage.
    """
    emails = []
    for biz in enriched_leads:
        contacts_with_email = [c for c in biz.get("contacts", []) if c.get("email")]

        if not contacts_with_email:
            # No enriched contacts — fall back to decision_maker / lead-level email
            result = await generate_email_for_lead(biz)
            if result:
                emails.append(result)
            continue

        for contact in contacts_with_email:
            result = await generate_email_for_contact(biz, contact)
            if result:
                emails.append(result)

    logger.info(f"[EmailGen] {len(emails)} emails generated across all contacts.")
    return emails
