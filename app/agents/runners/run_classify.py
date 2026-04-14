"""
app/agents/runners/run_classify.py
─────────────────────────────────────────────────────────────────────────────
Runner for Stage 2 — Business Intelligence

Mirrors: agents/src/runners/runClassify.js
Call classify_business_runner(biz) from pipeline code to classify a single
HORECA business using the Business Intelligence Agent.
─────────────────────────────────────────────────────────────────────────────
"""
import asyncio
import json
import logging

from agents import Runner

from app.agents.agents.business_intelligence import business_intelligence_agent
from app.utils.agent_flow import extract_agent_chain, log_agent_flow

logger = logging.getLogger(__name__)


async def classify_business_runner(biz: dict) -> dict:
    """
    Classifies a single HORECA business using the Business Intelligence Agent.

    Args:
        biz: Raw business dict (same shape as pipeline_stages.py Stage 1 output).

    Returns:
        Parsed analysis dict with sugar-intelligence fields.
    """
    prompt = (
        f"Analyze this HORECA business for sugar intelligence:\n\n"
        f"Business Name  : {biz.get('business_name', '')}\n"
        f"Segment        : {biz.get('segment', 'Restaurant')}\n"
        f"City           : {biz.get('city', '')}\n"
        f"Address        : {biz.get('address', 'Not available')}\n"
        f"Website        : {biz.get('website', 'Not available')}\n"
        f"Rating         : {biz.get('rating', 0)}/5  ({biz.get('reviews_count', 0):,} reviews)\n"
        f"Outlets        : {biz.get('num_outlets', 1)}  |  Chain: {biz.get('is_chain', False)}\n"
        f"Types          : {', '.join(biz.get('types', [])) or 'Not available'}\n"
        f"Description    : {biz.get('description', 'Not available')}\n"
        f"Highlights     : {', '.join(biz.get('highlights', [])) or 'Not available'}\n"
        f"Business Tags  : {', '.join(biz.get('from_the_business', [])) or 'Not available'}\n"
        f"Dining Options : {', '.join(biz.get('dining_options', [])) or 'Not available'}\n"
        f"Offerings      : {', '.join(biz.get('offerings', [])) or 'Not available'}"
    )

    result = await Runner.run(business_intelligence_agent, prompt)
    log_agent_flow(result.new_items)

    chain = extract_agent_chain(result.new_items)
    logger.info(f"Agent chain: {' → '.join(chain)}")

    # result.final_output is the agent's prose reply — NOT the tool's JSON.
    # The actual tool return value is stored in new_items as tool_call_output_item.
    for item in result.new_items:
        if getattr(item, "type", None) == "tool_call_output_item":
            try:
                parsed = json.loads(item.output)
                if isinstance(parsed, dict) and "has_dessert_menu" in parsed:
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

    # Fallback: try final_output as last resort
    try:
        return json.loads(result.final_output)
    except (json.JSONDecodeError, TypeError):
        return {"raw": result.final_output}


# # ── CLI / direct execution ────────────────────────────────────────────────────
# if __name__ == "__main__":
#     # Must import client BEFORE running any agents
#     import app.services.openai_client  # noqa: F401

#     sample_biz = {
#         "business_name": "Monginis Cake Shop",
#         "segment":       "Bakery",
#         "city":          "Mumbai",
#         "website":       "www.monginis.net",
#         "rating":        4.2,
#         "types":         ["Bakery", "Cake Shop"],
#         "description":   "Multi-outlet bakery chain specializing in cakes, pastries, and confectionery",
#         "highlights":    ["Great dessert", "Bakery items", "Great cakes"],
#         "from_the_business": ["Identifies as chain business"],
#     }

#     print("\n🏭  Running Stage 2: Business Intelligence\n")
#     analysis = asyncio.run(classify_business_runner(sample_biz))
#     print("\n📊  Analysis:", json.dumps(analysis, indent=2))
