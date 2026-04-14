"""
app/agents/runners/run_email.py
─────────────────────────────────────────────────────────────────────────────
Runner for Stage 7 — Personalized Email Generation

Mirrors: agents/src/runners/runEmail.js
Call generate_outreach_email(lead) to compose a personalized B2B outreach
email. Generated emails are also appended to generated_emails.jsonl.
─────────────────────────────────────────────────────────────────────────────
"""
import asyncio
import json
import logging

from agents import Runner

from app.agents.agents.email_generator import email_generator_agent
from app.utils.agent_flow import extract_agent_chain, log_agent_flow

logger = logging.getLogger(__name__)


async def generate_outreach_email(lead: dict) -> dict:
    """
    Generates a personalized B2B outreach email for a HORECA lead.

    Args:
        lead: Enriched lead dict (matches pipeline_stages.py Stage 7 input).

    Returns:
        Dict with 'subject' and 'body' keys.
    """
    prompt = (
        f"Generate a personalized B2B outreach email for this HORECA lead:\n\n"
        f"Business      : {lead.get('business_name', '')}\n"
        f"City          : {lead.get('city', '')}\n"
        f"Segment       : {lead.get('segment', 'Restaurant')}\n"
        f"Contact       : {lead.get('decision_maker_name') or 'Procurement Manager'} "
        f"({lead.get('decision_maker_role') or 'F&B Head'})\n"
        f"Dessert Menu  : {'Yes' if lead.get('has_dessert_menu') else 'No'}\n"
        f"Monthly Sugar : ~{lead.get('monthly_sugar_estimate_kg', 0)} kg estimated\n"
        f"Rating        : {lead.get('rating', 0)}/5\n"
        f"Hotel Category: {lead.get('hotel_category') or 'N/A'}\n"
        f"AI Insight    : {lead.get('ai_reasoning', '')}"
    )

    result = await Runner.run(email_generator_agent, prompt)
    log_agent_flow(result.new_items)

    chain = extract_agent_chain(result.new_items)
    logger.info(f"Agent chain: {' → '.join(chain)}")

    # Extract tool JSON from new_items, not final_output prose
    for item in result.new_items:
        if getattr(item, "type", None) == "tool_call_output_item":
            try:
                parsed = json.loads(item.output)
                if isinstance(parsed, dict) and "subject" in parsed:
                    return {"subject": parsed.get("subject", ""), "body": parsed.get("body", "")}
            except (json.JSONDecodeError, TypeError):
                pass

    try:
        parsed = json.loads(result.final_output)
        return {"subject": parsed.get("subject", ""), "body": parsed.get("body", "")}
    except (json.JSONDecodeError, TypeError):
        return {"subject": "", "body": result.final_output or ""}


# ── CLI / direct execution ────────────────────────────────────────────────────
if __name__ == "__main__":
    import app.services.openai_client  # noqa: F401

    sample_lead = {
        "business_name":           "Monginis Cake Shop",
        "city":                    "Mumbai",
        "segment":                 "Bakery",
        "decision_maker_name":     "Suhail Khorakiwala",
        "decision_maker_role":     "Procurement Head",
        "has_dessert_menu":        True,
        "monthly_sugar_estimate_kg": 5000,
        "rating":                  4.2,
        "hotel_category":          "",
        "ai_reasoning":            "Large multi-outlet bakery chain with very high sugar dependency.",
    }

    print("\n✉️   Running Stage 7: Email Generation\n")
    email = asyncio.run(generate_outreach_email(sample_lead))
    print(f"\n📧  Subject: {email['subject']}\n\n{email['body']}")
