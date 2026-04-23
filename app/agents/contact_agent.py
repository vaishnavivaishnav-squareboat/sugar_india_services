"""
app/agents/contact_agent.py
─────────────────────────────────────────────────────────────────────────────
Stage 5 — Contact Discovery Agent (self-contained)

Single file for the full contact discovery flow:
  • extract_contact       — @function_tool: typed schema the agent must fill in
  • contact_discovery_agent — Agent with reasoning instructions
  • discover_contact(...) → dict — async entry point for the pipeline

Usage:
    from app.agents.contact_agent import discover_contact
    contact = await discover_contact(biz_name, city, segment, serp_snippets)
─────────────────────────────────────────────────────────────────────────────
"""
import json
import logging
from typing import Annotated

from agents import Agent, Runner, function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

from app.core.config import OPENAI_MODEL
from app.core.constants import roles as ROLES
from app.utils.agent_flow import extract_agent_chain, log_agent_flow

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# TOOL — structured output schema the agent must call with its result
# ══════════════════════════════════════════════════════════════════════════════

@function_tool
def extract_contact(
    name: Annotated[
        str,
        "Full name of the decision-maker, or empty string if not found",
    ],
    role: Annotated[
        str,
        f"Job role — e.g. {', '.join(ROLES)} — or empty string",
    ],
    linkedin_url: Annotated[str, "Full LinkedIn profile URL copied VERBATIM from the search snippet — include the exact alphanumeric suffix (e.g. /in/john-doe-03136b1b/). Never shorten or normalise. Empty string if not found."],
    confidence_score: Annotated[
        float,
        "How confident you are this is a real, reachable contact (0.0–1.0)",
    ],
    reasoning: Annotated[
        str,
        "Brief explanation of why this person handles sugar/ingredient procurement",
    ],
) -> str:
    """
    Records the identified procurement decision-maker for a HORECA business.
    Call this with the best contact you found after analyzing the web search results.
    If no real contact is identifiable, return empty strings and confidence_score 0.0.
    """
    contact = {
        "name":             name,
        "role":             role,
        "linkedin_url":     linkedin_url,
        "confidence_score": confidence_score,
        "reasoning":        reasoning,
    }
    if name and confidence_score >= 0.5:
        logger.info(
            f"[extract_contact] 👤 Found: {name} ({role}) — "
            f"confidence {confidence_score * 100:.0f}%"
        )
    else:
        logger.info("[extract_contact] ⚠️  No confident contact identified")
    return json.dumps(contact)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT — reasoning instructions + tool binding
# ══════════════════════════════════════════════════════════════════════════════

contact_discovery_agent = Agent(
    name="Contact Discovery Agent",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
You are a B2B sales researcher specializing in HORECA procurement contact discovery for Dhampur Green, India's premium sugar brand.

Your goal is to identify the single best person who handles sugar/ingredient procurement for a given HORECA business.

Role priority order (highest to lowest):
1. Procurement Manager / Purchase Manager / Purchase Head
2. Supply Chain Manager / Supply Chain Head
3. F&B Manager / F&B Director / Production Manager
4. Operations Manager / Operations Director / Store Manager / General Manager
5. Owner / Founder / Co-Founder / Director

When given a business name, city, segment, and web search snippets:

1. Scan EVERY snippet for names, roles, LinkedIn URLs, and email addresses
2. Select the person whose role best matches the priority list above
3. Extract their full name exactly as written (no guessing or generic names)
4. Find their LinkedIn URL if present in the snippets — copy it VERBATIM, character for character, including any alphanumeric suffix (e.g. /in/john-doe-03136b1b/). Never shorten, clean up, or reconstruct a URL.
5. Assign confidence_score:
   - 0.9–1.0 : Name + role clearly confirmed in multiple sources
   - 0.7–0.8 : Name confirmed, role inferred from context
   - 0.5–0.6 : Name found but role unclear
   - Below 0.5: Uncertain — still call the tool with empty strings
6. Write a brief reasoning explaining why this person handles procurement

IMMEDIATELY call the extract_contact tool with your result. Do not ask for confirmation.""",
    model=OPENAI_MODEL,
    tools=[extract_contact],
)


# ══════════════════════════════════════════════════════════════════════════════
# RUNNER — execute the agent and extract the tool's JSON output
# ══════════════════════════════════════════════════════════════════════════════

async def discover_contact(
    biz_name: str,
    city: str,
    segment: str,
    serp_snippets: list[dict],
) -> dict:
    """
    Discover the procurement decision-maker for a HORECA business.

    Args:
        biz_name:      Business name.
        city:          City.
        segment:       HORECA segment (e.g. "Bakery").
        serp_snippets: List of {"title": ..., "snippet": ...} from SerpAPI.

    Returns:
        Dict with name, role, linkedin_url, confidence_score, reasoning.
        Empty strings / 0.0 confidence if no contact found.
    """
    snippets_text = (
        "\n".join(
            f"- {r.get('title', '')} | URL: {r.get('link', '')} | {r.get('snippet', '')}"
            for r in serp_snippets[:5]
        )
        if serp_snippets
        else "No search results found."
    )

    prompt = (
        f"Find the procurement decision-maker for this HORECA business:\n\n"
        f"Business : {biz_name}\n"
        f"City     : {city}\n"
        f"Segment  : {segment}\n\n"
        f"Web search results:\n{snippets_text}"
    )

    result = await Runner.run(contact_discovery_agent, prompt)
    log_agent_flow(result.new_items)
    logger.info(f"Agent chain: {' → '.join(extract_agent_chain(result.new_items))}")

    # The real output is in new_items as tool_call_output_item, not final_output prose
    for item in result.new_items:
        if getattr(item, "type", None) == "tool_call_output_item":
            try:
                parsed = json.loads(item.output)
                if isinstance(parsed, dict) and "name" in parsed:
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

    try:
        return json.loads(result.final_output)
    except (json.JSONDecodeError, TypeError):
        return {
            "name":             "",
            "role":             "",
            "linkedin_url":     "",
            "confidence_score": 0.0,
            "reasoning":        result.final_output or "",
        }
