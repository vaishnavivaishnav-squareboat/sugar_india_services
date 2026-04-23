"""
app/services/classification/classification_service.py
─────────────────────────────────────────────────────────────────────────────
Stage 2 — AI Business Classification.

For each business dict produced by Stage 1, calls OpenAI with the
business_intelligence prompt to extract:
  • has_dessert_menu           — bool
  • sugar_items_count          — int
  • menu_categories            — list[str]
  • avg_price_range            — str
  • business_classification    — refined segment string
  • is_chain                   — bool
  • hotel_category             — str ("3-star", "4-star", "5-star" or "")
  • monthly_sugar_estimate_kg  — int
  • sweetness_dependency_pct   — int (0–100)
  • sugar_signal_from_highlights — bool
  • highlight_sugar_signals    — list[str]
  • ai_reasoning               — str

This is the clean, modular replacement for the inline ai_process_business_data()
function in stages.py. stages.py delegates to this service.
─────────────────────────────────────────────────────────────────────────────
"""
import json
import logging

from app.agents.prompts.business_intelligence import business_intelligence_prompt
from app.core.openai_client import call_openai

logger = logging.getLogger(__name__)


async def classify_business(biz: dict) -> dict:
    """
    Run OpenAI business-intelligence classification on a single business dict.

    Mutates *biz* in-place with AI-derived fields and returns it.
    On failure, safe defaults are applied so downstream stages always see the
    expected keys.

    Args:
        biz: Normalised business dict from Stage 1.

    Returns:
        The same dict with AI fields merged in.
    """
    name              = biz.get("business_name", "")
    segment           = biz.get("segment", "Restaurant")
    city              = biz.get("city", "")
    website           = biz.get("website", "")
    rating            = biz.get("rating", 0.0)
    types             = ", ".join(biz.get("types", []))
    highlights        = biz.get("highlights", [])
    description       = biz.get("description", [])
    from_the_business = biz.get("from_the_business", [])

    highlights_text  = ", ".join(highlights)        if highlights        else "Not available"
    description_text = ", ".join(description)       if description       else "Not available"
    identity_text    = ", ".join(from_the_business) if from_the_business else "Not available"

    prompt = business_intelligence_prompt(
        name=name,
        segment=segment,
        city=city,
        website=website,
        rating=rating,
        types=types,
        description_text=description_text,
        highlights_text=highlights_text,
        identity_text=identity_text,
    )
    try:
        ai = json.loads(await call_openai(prompt, force_json=True))
        biz.update({
            "has_dessert_menu":             ai.get("has_dessert_menu", False),
            "sugar_items_count":            ai.get("sugar_items_count", 0),
            "menu_categories":              ai.get("menu_categories", []),
            "avg_price_range":              ai.get("avg_price_range", "mid-range"),
            "segment":                      ai.get("business_classification", segment),
            "is_chain":                     ai.get("is_chain", False),
            "hotel_category":               ai.get("hotel_category", ""),
            "monthly_sugar_estimate_kg":    ai.get("monthly_sugar_estimate_kg", 0),
            "sweetness_dependency_pct":     ai.get("sweetness_dependency_pct", 0),
            "sugar_signal_from_highlights": ai.get("sugar_signal_from_highlights", False),
            "highlight_sugar_signals":      ai.get("highlight_sugar_signals", []),
            "ai_reasoning":                 ai.get("ai_reasoning", ""),
        })
    except Exception as exc:
        logger.info(f"[Classification] Processing failed for '{name}': {exc}")
        biz.setdefault("has_dessert_menu",             segment in ["Cafe", "Bakery", "Hotel"])
        biz.setdefault("monthly_sugar_estimate_kg",    0)
        biz.setdefault("sweetness_dependency_pct",     0)
        biz.setdefault("sugar_signal_from_highlights", False)
        biz.setdefault("highlight_sugar_signals",      [])
        biz.setdefault("ai_reasoning",                 "")

    return biz




# ── START ────────────────────────────────────────────────────────
async def classify_businesses(raw_data: list[dict]) -> list[dict]:
    """
    Run AI classification for every business in the list (pipeline wrapper).

    Processes each business sequentially to stay within OpenAI rate limits.
    Returns the enriched list.

    Args:
        raw_data: List of normalised business dicts from Stage 1.

    Returns:
        Same list with AI-derived fields added to every dict.
    """
    enriched = []
    for biz in raw_data:
        enriched.append(await classify_business(biz))

    logger.info(f"[Classification] Processed {len(enriched)} businesses.")
    return enriched
