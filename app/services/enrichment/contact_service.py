"""
app/services/enrichment/contact_service.py
─────────────────────────────────────────────────────────────────────────────
Stage 5 — Contact Discovery Orchestrator.

Flow:
  1. For each target role, run a SerpAPI Google search for the business
  2. Feed all SERP snippets into the AI extraction model
  3. Collect candidates, rank by confidence_score
  4. Return the best contact + full list of found contacts

This is the clean, modular replacement for the inline enrich_contacts()
function in stages.py. stages.py delegates to this service.
─────────────────────────────────────────────────────────────────────────────
"""
import json
import logging

from app.providers.serpapi_provider import search_google
from app.agents.prompts.contact_extraction import contact_extraction_prompt
from app.core.openai_client import call_openai
from app.core.constants import roles as DEFAULT_ROLES

logger = logging.getLogger(__name__)



async def _ai_extract_contact(
    biz_name: str,
    city: str,
    segment: str,
    serp_snippets: list[dict],
) -> dict:
    """
    Run OpenAI over SERP snippets and extract the best procurement contact.

    Returns a dict with: name, role, linkedin_url, confidence_score, reasoning.
    """
    snippets_text = "\n".join(
        f"- {r.get('title', '')} | URL: {r.get('link', '')} | {r.get('snippet', '')}"
        for r in serp_snippets[:5]
    ) or "No search results found."

    prompt = contact_extraction_prompt(
        biz_name=biz_name,
        city=city,
        segment=segment,
        snippets_text=snippets_text,
    )
    try:
        return json.loads(await call_openai(prompt, force_json=True))
    except Exception as exc:
        logger.info(f"[ContactService] AI extraction failed for '{biz_name}': {exc}")
        return {"name": "", "role": "", "linkedin_url": "", "confidence_score": 0.0}



async def discover_contacts(
    business_name: str,
    city: str,
    segment: str,
    roles: list[str] | None = None,
    min_confidence: float = 0.5,
) -> dict:
    """
    Discover procurement decision-makers for a HORECA business.

    Strategy:
      • For each role keyword, search Google for "{business} {city} {role} LinkedIn"
      • Extract contact info with AI from each batch of SERP snippets
      • De-duplicate by name, filter by min_confidence
      • Select the best candidate (highest confidence_score)

    Args:
        business_name:   Name of the HORECA business.
        city:            City the business is in.
        segment:         HORECA segment (e.g. "Bakery").
        roles:           Role titles to search for. Defaults to the full roles list.
        min_confidence:  Minimum AI confidence to include a contact (0.0–1.0).

    Returns:
        {
          "best":     { name, role, linkedin_url, confidence_score, ... },
          "contacts": [ ... all candidates ... ],
        }
    """
    if roles is None:
        roles = DEFAULT_ROLES

    contacts: list[dict] = []
    seen_names: set[str] = set()

    # ── Single combined query (1 SerpAPI credit per lead) ─────────────────────
    # LinkedIn people-search pattern: scope to linkedin.com/in profiles, OR all
    # roles, anchor on business name / city, filter by industry keywords + India.
    roles_or = " OR ".join(f'"{r}"' for r in roles)
    query = (
        f'site:linkedin.com/in ({roles_or}) '
        f'("{business_name}" OR "{city}") '
        f'("food" OR "FMCG" OR "beverages" OR "hospitality") '
        f'"India"'
    )
    try:
        snippets = await search_google(query)
        contact  = await _ai_extract_contact(business_name, city, segment, snippets)
        name     = contact.get("name", "")
        score    = float(contact.get("confidence_score", 0))
        if name and score >= min_confidence and name not in seen_names:
            seen_names.add(name)
            contacts.append({
                "name":             name,
                "role":             contact.get("role", ""),
                "linkedin_url":     contact.get("linkedin_url", ""),
                "email":            "",
                "confidence_score": score,
                "source":           "serp+openai",
            })
    except Exception as exc:
        logger.info(f"[ContactService] Search failed for '{business_name}': {exc}")

    best = max(contacts, key=lambda c: c.get("confidence_score", 0)) if contacts else {}
    logger.info(
        f"[ContactService] '{business_name}': {len(contacts)} contact(s) found. "
        f"Best: {best.get('name') or 'none'} ({best.get('confidence_score', 0):.0%})"
    )
    return {"best": best, "contacts": contacts}


# ── START ────────────────────────────────────────────────────────
async def enrich_leads_contacts(leads: list[dict]) -> list[dict]:
    """
    Run contact discovery for a list of lead dicts (pipeline-compatible wrapper).

    Mutates each lead dict in-place, adding:
      - decision_maker_name
      - decision_maker_role
      - decision_maker_linkedin
      - contacts (list of all found candidates)

    Returns the mutated list.
    """
    for biz in leads:
        # Skip Stage 5 for leads without a website — they have no domain for
        # Stage 6 email enrichment anyway, so spending a SerpAPI credit here
        # would produce a contact name we can never email. Fall through with
        # empty contacts so Stage 6 also skips them cleanly.
        if not biz.get("website", "").strip():
            logger.info(
                f"[ContactService] '{biz.get('business_name')}': skipping — no website (saves 1 SerpAPI credit)"
            )
            biz["contacts"] = []
            continue

        result = await discover_contacts(
            business_name=biz.get("business_name", ""),
            city=biz.get("city", ""),
            segment=biz.get("segment", "Restaurant"),
        )
        best = result.get("best", {})
        if best:
            biz["decision_maker_name"]     = best.get("name", "")
            biz["decision_maker_role"]     = best.get("role", "")
            biz["decision_maker_linkedin"] = best.get("linkedin_url", "")
        biz["contacts"] = result.get("contacts", [])
    return leads
