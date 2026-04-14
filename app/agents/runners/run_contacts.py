"""
app/agents/runners/run_contacts.py
─────────────────────────────────────────────────────────────────────────────
Runner for Stage 5 — Contact Discovery

Mirrors: agents/src/runners/runContacts.js
Call discover_contact(biz_name, city, segment, serp_snippets) to identify
the best procurement decision-maker for a HORECA business.
─────────────────────────────────────────────────────────────────────────────
"""
import asyncio
import json
import logging

from agents import Runner

from app.agents.agents.contact_discovery import contact_discovery_agent
from app.utils.agent_flow import extract_agent_chain, log_agent_flow

logger = logging.getLogger(__name__)


async def discover_contact(
    biz_name: str,
    city: str,
    segment: str,
    serp_snippets: list[dict],
) -> dict:
    """
    Discovers the procurement decision-maker for a HORECA business.

    Args:
        biz_name:      Business name.
        city:          City.
        segment:       HORECA segment.
        serp_snippets: List of {"title": ..., "snippet": ...} from SerpAPI.

    Returns:
        Dict with name, role, linkedin_url, confidence_score, reasoning.
    """
    snippets_text = (
        "\n".join(
            f"- {r.get('title', '')}: {r.get('snippet', '')}"
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

    chain = extract_agent_chain(result.new_items)
    logger.info(f"Agent chain: {' → '.join(chain)}")

    # Extract tool JSON from new_items, not final_output prose
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


# ── CLI / direct execution ────────────────────────────────────────────────────
if __name__ == "__main__":
    import app.services.openai_client  # noqa: F401

    sample_snippets = [
        {
            "title":   "Monginis – Company Overview",
            "snippet": "Suhail Khorakiwala, Procurement Head at Monginis Foods Pvt Ltd, oversees all ingredient sourcing.",
        },
        {
            "title":   "LinkedIn – Suhail Khorakiwala",
            "snippet": "Suhail Khorakiwala – Procurement Head, Monginis | linkedin.com/in/suhail-khorakiwala-monginis",
        },
    ]

    print("\n🔍  Running Stage 5: Contact Discovery\n")
    contact = asyncio.run(
        discover_contact("Monginis Cake Shop", "Mumbai", "Bakery", sample_snippets)
    )
    print("\n👤  Contact:", json.dumps(contact, indent=2))
