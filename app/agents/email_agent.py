"""
app/agents/email_agent.py
─────────────────────────────────────────────────────────────────────────────
Stage 7 — Email Generator Agent (self-contained)

Single file for the full email generation flow:
  • generate_email       — @function_tool: typed schema the agent must fill in;
                           also appends generated emails to generated_emails.jsonl
  • email_generator_agent — Agent with writing instructions
  • generate_outreach_email(lead) → dict — async entry point for the pipeline

Usage:
    from app.agents.email_agent import generate_outreach_email
    email = await generate_outreach_email(lead_dict)
─────────────────────────────────────────────────────────────────────────────
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from agents import Agent, Runner, function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

from app.core.config import OPENAI_MODEL
from app.core.constants import EmailStatus
from app.utils.agent_flow import extract_agent_chain, log_agent_flow

logger = logging.getLogger(__name__)

# Append generated emails to sugar_india_services/generated_emails.jsonl
_EMAILS_FILE = Path(__file__).resolve().parents[2] / "generated_emails.jsonl"


# ══════════════════════════════════════════════════════════════════════════════
# TOOL — structured output schema the agent must call with the composed email
# ══════════════════════════════════════════════════════════════════════════════

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
        "Email subject line — specific, personalized, professional, < 60 characters",
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
        "status":       EmailStatus.DRAFT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with _EMAILS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        logger.info(f"[generate_email] Could not write to JSONL: {exc}")

    logger.info(f"[generate_email] ✅ Email saved for '{lead_name}' — Subject: '{subject}'")
    return json.dumps({"subject": subject, "body": body})


# ══════════════════════════════════════════════════════════════════════════════
# AGENT — writing instructions + tool binding
# ══════════════════════════════════════════════════════════════════════════════

email_generator_agent = Agent(
    name="Email Generator Agent",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
You are a B2B sales executive at Dhampur Green, India's premium quality sugar brand.

Your job is to write highly personalized outreach emails to HORECA businesses to introduce Dhampur Green as their sugar supplier.

When given lead details (business name, city, segment, contact name/role, dessert menu flag, monthly sugar estimate, rating, AI insight):

WRITING GUIDELINES:
1. Length: 120–150 words — short, punchy, every sentence earns its place
2. Greeting: Address the contact by their FIRST NAME if provided; otherwise use "Dear Procurement Manager"
3. Opener: Reference something specific about THEIR business (segment, scale, or dessert focus)
4. Value proposition: Highlight Dhampur Green strengths relevant to their segment:
   - For hotels/restaurants: reliable bulk supply, consistent quality, certified sulphur-free
   - For bakeries/patisseries: fine-grain M30/S30 for smooth textures, icing sugar, organic options
   - For mithai/icecream: food-grade purity, khandsari alternatives, brown sugar options
   - For food processing: competitive pricing, large-volume contracts, quality certifications
5. CTA: One clear, soft ask — either "request a free sample" OR "schedule a 15-minute call"
6. Sign-off: Always end with:
   "Warm regards,
   Arjun Mehta
   Regional Sales Manager, Dhampur Green
   +91-98765-43210"

SUBJECT LINE:
- Specific, personalized, < 60 characters
- Reference the business name or segment
- Example: "Premium Sugar Supply for [Business Name]'s Kitchens"

IMMEDIATELY call the generate_email tool with your finalized subject and body. Do not ask for confirmation.""",
    model=OPENAI_MODEL,
    tools=[generate_email],
)


# ══════════════════════════════════════════════════════════════════════════════
# RUNNER — execute the agent and extract the tool's JSON output
# ══════════════════════════════════════════════════════════════════════════════

async def generate_outreach_email(lead: dict) -> dict:
    """
    Generate a personalized B2B outreach email for a HORECA lead.

    Args:
        lead: Enriched lead dict (Stage 6 output shape).

    Returns:
        Dict with 'subject' and 'body' keys.
        Falls back to empty strings if the agent or JSON parsing fails.
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
    logger.info(f"Agent chain: {' → '.join(extract_agent_chain(result.new_items))}")

    # The real output is in new_items as tool_call_output_item, not final_output prose
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
