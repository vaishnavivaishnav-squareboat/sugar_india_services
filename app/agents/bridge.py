"""
app/agents/bridge.py
─────────────────────────────────────────────────────────────────────────────
Python ↔ Agent bridge — replaces agents/src/bridge.js

Two usage modes:

  1. Import directly (preferred now that everything is Python):
       from app.agents.bridge import run_stage2, run_stage5, run_stage7

  2. CLI / subprocess (backward-compatible with test_pipeline.py):
       echo '<json>' | python -m app.agents.bridge
       Input  (stdin) : { "stage": 2 | 5 | 7, "businesses": [...] }
       Output (stdout): { "businesses": [...] }  for stages 2 & 5
                        { "emails": [...] }       for stage 7

Mirrors: agents/src/bridge.js
─────────────────────────────────────────────────────────────────────────────
"""
import asyncio
import json
import logging
import sys

# ── CRITICAL: register OpenAI client before any agent imports ─────────────────
import app.services.openai_client  # noqa: F401

from app.agents.runners.run_classify import classify_business_runner
from app.agents.runners.run_contacts import discover_contact
from app.agents.runners.run_email import generate_outreach_email
from app.core.constants import EmailStatus

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2 — Classify businesses via Business Intelligence Agent
# ══════════════════════════════════════════════════════════════════════════════

async def run_stage2(businesses: list[dict]) -> dict:
    """
    Classifies each business using the Business Intelligence Agent.
    Merges AI fields back onto the original business dict.
    """
    results = []
    for biz in businesses:
        logger.info(f"[bridge] Stage 2 — classifying '{biz.get('business_name')}' ...")
        try:
            analysis = await classify_business_runner(biz)
            results.append({
                **biz,
                "has_dessert_menu":             analysis.get("has_dessert_menu",             biz.get("has_dessert_menu", False)),
                "sugar_items_count":            analysis.get("sugar_items_count",            0),
                "menu_categories":              analysis.get("menu_categories",              []),
                "avg_price_range":              analysis.get("avg_price_range",              "mid-range"),
                "segment":                      analysis.get("business_classification",      biz.get("segment")),
                "is_chain":                     analysis.get("is_chain",                     biz.get("is_chain", False)),
                "hotel_category":               analysis.get("hotel_category",               ""),
                "monthly_sugar_estimate_kg":    analysis.get("monthly_sugar_estimate_kg",    0),
                "sweetness_dependency_pct":     analysis.get("sweetness_dependency_pct",     0),
                "sugar_signal_from_highlights": analysis.get("sugar_signal_from_highlights", False),
                "highlight_sugar_signals":      analysis.get("highlight_sugar_signals",      []),
                "ai_reasoning":                 analysis.get("ai_reasoning",                 ""),
            })
        except Exception as exc:
            logger.error(f"[bridge] Stage 2 error for '{biz.get('business_name')}': {exc}")
            results.append({
                **biz,
                "has_dessert_menu":          biz.get("segment") in ("Bakery", "Cafe"),
                "monthly_sugar_estimate_kg": 0,
                "sweetness_dependency_pct":  0,
                "ai_reasoning":              "Agent unavailable — fallback defaults applied",
            })
        await asyncio.sleep(0.3)
    return {"businesses": results}


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 5 — Discover contacts via Contact Discovery Agent
# ══════════════════════════════════════════════════════════════════════════════

async def run_stage5(businesses: list[dict]) -> dict:
    """
    Enriches each business with a procurement contact via the Contact Discovery Agent.
    """
    results = []
    for biz in businesses:
        logger.info(f"[bridge] Stage 5 — finding contact for '{biz.get('business_name')}' ...")
        try:
            snippets = biz.get("_serp_snippets", [])
            contact  = await discover_contact(
                biz.get("business_name", ""),
                biz.get("city", ""),
                biz.get("segment", ""),
                snippets,
            )
            enriched = {k: v for k, v in biz.items() if k != "_serp_snippets"}
            if contact.get("name") and contact.get("confidence_score", 0) >= 0.5:
                enriched["decision_maker_name"]     = contact["name"]
                enriched["decision_maker_role"]     = contact["role"]
                enriched["decision_maker_linkedin"] = contact["linkedin_url"]
                enriched["contacts"] = [
                    *biz.get("contacts", []),
                    {
                        "name":             contact["name"],
                        "role":             contact["role"],
                        "linkedin_url":     contact["linkedin_url"],
                        "email":            "",
                        "confidence_score": contact["confidence_score"],
                        "source":           "agent_contact_discovery",
                    },
                ]
            else:
                enriched["contacts"] = biz.get("contacts", [])
            results.append(enriched)
        except Exception as exc:
            logger.error(f"[bridge] Stage 5 error for '{biz.get('business_name')}': {exc}")
            fallback = {k: v for k, v in biz.items() if k != "_serp_snippets"}
            results.append(fallback)
        await asyncio.sleep(0.3)
    return {"businesses": results}


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 7 — Generate outreach emails via Email Generator Agent
# ══════════════════════════════════════════════════════════════════════════════

async def run_stage7(businesses: list[dict]) -> dict:
    """
    Generates a personalized outreach email for each business.
    """
    emails = []
    for biz in businesses:
        logger.info(f"[bridge] Stage 7 — generating email for '{biz.get('business_name')}' ...")
        try:
            email = await generate_outreach_email(biz)
            emails.append({
                "lead_name":    biz.get("business_name"),
                "lead_city":    biz.get("city"),
                "lead_segment": biz.get("segment"),
                "subject":      email["subject"],
                "body":         email["body"],
                "status":       EmailStatus.DRAFT,
                "business":     biz,
            })
        except Exception as exc:
            logger.error(f"[bridge] Stage 7 error for '{biz.get('business_name')}': {exc}")
            emails.append({
                "lead_name":    biz.get("business_name"),
                "lead_city":    biz.get("city"),
                "lead_segment": biz.get("segment"),
                "subject":      f"Sugar Supply Partnership — {biz.get('business_name')}",
                "body":         "Agent unavailable — email generation failed.",
                "status":       EmailStatus.DRAFT,
                "business":     biz,
            })
        await asyncio.sleep(0.3)
    return {"emails": emails}


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry point — reads JSON from stdin, writes JSON to stdout
# Backward-compatible with test_pipeline.py subprocess usage
# ══════════════════════════════════════════════════════════════════════════════

async def _cli_main() -> None:
    raw   = sys.stdin.read()
    input_data = json.loads(raw)
    stage      = input_data.get("stage")
    businesses = input_data.get("businesses", [])

    if not businesses:
        sys.stdout.write(json.dumps({"businesses": [], "emails": []}))
        return

    if stage == 2:
        output = await run_stage2(businesses)
    elif stage == 5:
        output = await run_stage5(businesses)
    elif stage == 7:
        output = await run_stage7(businesses)
    else:
        raise ValueError(f"Unknown stage: {stage}")

    sys.stdout.write(json.dumps(output))


if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    asyncio.run(_cli_main())
