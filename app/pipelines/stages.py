"""
app/pipelines/stages.py
─────────────────────────────────────────────────────────────────────────────
Full ETL pipeline stages for the HORECA lead generation system.

Stages:
  1. extract_business_data     – SerpAPI Google Maps + Hunter Discover (multi-query, all HORECA segments)
  2. ai_process_business_data  – Gemini: menu, dessert, sugar classification
  3. apply_kpi_filtering       – Composite KPI score + threshold rejection
  4. deduplicate_leads         – Fuzzy name + geo dedup + DB cross-check
  5. enrich_contacts           – SerpAPI + Gemini AI contact discovery
  6. enrich_emails             – Hunter.io + Apollo.io email enrichment
  7. generate_personalized_emails – Gemini AI outreach email generation
  8. store_leads_and_emails    – Persist leads, contacts, emails to DB
─────────────────────────────────────────────────────────────────────────────
"""

import os
import re
import json
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import httpx
import serpapi as serpapi_client
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import SERP_API_KEY, HUNTER_API_KEY, APOLLO_API_KEY
from pyhunter import AsyncPyHunter
from app.prompts.business_intelligence import business_intelligence_prompt
from app.prompts.contact_extraction    import contact_extraction_prompt
from app.prompts.email_generation      import email_generation_prompt

from app.db.orm import Lead, City, OutreachEmail, PipelineRun, Contact
from app.utils.genai import call_genai


logger = logging.getLogger(__name__)

# ─── QUERY MAPS ──────────────────────────────────────────────────────────────


HORECA_QUERY_MAP: dict[str, list[str]] = {
    # ── A. Bakery & Confectionery ──────────────────────────────────────────
    "Bakery":           ["bakeries in {city}"
                        #  , "cake shop {city}", "patisserie {city}"
                         ],
    # # ── B. Dairy & Frozen ─────────────────────────────────────────────────
    # "IceCream":         ["ice cream parlour {city}", "gelato shop {city}", "frozen dessert {city}"],
    # # ── C. Beverage ───────────────────────────────────────────────────────
    # "Beverage":         ["juice manufacturer {city}", "beverage company {city}", "syrup manufacturer {city}"],
    # # ── D. HORECA ─────────────────────────────────────────────────────────
    # "Restaurant":       ["restaurants in {city}", "fine dining {city}"],
    # "Cafe":             ["cafes in {city}", "coffee shops {city}", "dessert cafe {city}"],
    # "Hotel":            ["hotels in {city}", "luxury hotels {city}"],
    # "Catering":         ["catering services {city}", "event caterers {city}"],
    # "CloudKitchen":     ["cloud kitchen {city}", "dark kitchen {city}"],
    # # ── E. Traditional Sweets ─────────────────────────────────────────────
    # "Mithai":           ["sweet shop {city}", "mithai shop {city}", "halwai {city}"],
    # # ── F. Food Processing ────────────────────────────────────────────────
    # "FoodProcessing":   ["biscuit manufacturer {city}", "packaged food company {city}", "food processing unit {city}"],
    # # ── G. Health / Organic / Jaggery ─────────────────────────────────────
    # "Organic":          ["organic food brand {city}", "jaggery products {city}", "ayurvedic food company {city}"],
    # # ── H. Fermentation (Brewery / Distillery) ────────────────────────────
    # "Brewery":          ["brewery {city}", "distillery {city}", "craft beer {city}"],
}

# Full query map used when a specific segment_filter is requested (e.g. from discover endpoint).
# HORECA_QUERY_MAP above controls which segments the weekly cron processes.
_FULL_QUERY_MAP: dict[str, list[str]] = {
    "Bakery":         ["bakeries in {city}"
                    #    , "cake shop {city}", "patisserie {city}"
                       ],
    # "IceCream":       ["ice cream parlour {city}", "gelato shop {city}", "frozen dessert {city}"],
    # "Beverage":       ["juice manufacturer {city}", "beverage company {city}", "syrup manufacturer {city}"],
    # "Restaurant":     ["restaurants in {city}", "fine dining {city}"],
    # "Cafe":           ["cafes in {city}", "coffee shops {city}", "dessert cafe {city}"],
    # "Hotel":          ["hotels in {city}", "luxury hotels {city}"],
    # "Catering":       ["catering services {city}", "event caterers {city}"],
    # "CloudKitchen":   ["cloud kitchen {city}", "dark kitchen {city}"],
    # "Mithai":         ["sweet shop {city}", "mithai shop {city}", "halwai {city}"],
    # "FoodProcessing": ["biscuit manufacturer {city}", "packaged food company {city}", "food processing unit {city}"],
    # "Organic":        ["organic food brand {city}", "jaggery products {city}", "ayurvedic food company {city}"],
    # "Brewery":        ["brewery {city}", "distillery {city}", "craft beer {city}"],
}

SEGMENT_WEIGHTS = {
    "Mithai":         100,
    "Bakery":         100,
    "FoodProcessing":  95,
    "IceCream":        90,
    "Beverage":        88,
    "Catering":        80,
    "Cafe":            78,
    "CloudKitchen":    72,
    "Organic":         70,
    "Brewery":         65,
    "Restaurant":      60,
    "Hotel":           55,
}

ROLE_PRIORITY = [
    "Procurement Manager", "Purchase Manager", "Purchase Head",
    "Supply Chain Manager", "Supply Chain Head",
    "F&B Manager", "F&B Director", "Production Manager", "Plant Manager",
    "Operations Manager", "Operations Director",
    "Store Manager", "General Manager",
    "Owner", "Founder", "Co-Founder", "Director",
]


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 – DATA EXTRACTION (SerpAPI Google Maps)
# ══════════════════════════════════════════════════════════════════════════════

_executor = ThreadPoolExecutor(max_workers=4)


def _serp_maps_search_sync(query: str, api_key: str, start: int = 0) -> dict:
    client = serpapi_client.Client(api_key=api_key)
    return client.search({
        "engine": "google_maps",
        "q":      query,
        "type":   "search",
        "start":  start,
        "hl":     "en",
        "gl":     "in",
    })


async def _serp_maps_page(query: str, start: int = 0) -> list:
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor, _serp_maps_search_sync, query, SERP_API_KEY, start,
        )
        return result.get("local_results", [])
    except Exception as exc:
        logger.error(f"[Extract] SerpAPI failed for '{query}' (start={start}): {exc}")
        return []


def _parse_extensions(raw_extensions: list) -> dict:
    parsed = {"highlights": [], "from_the_business": []}
    for ext in (raw_extensions or []):
        for key in ("highlights", "from_the_business"):
            if key in ext:
                parsed[key].extend(ext[key])
    return parsed


def _normalize_serp_result(place: dict, segment: str, city: str) -> dict:
    gps        = place.get("gps_coordinates") or {}
    extensions = _parse_extensions(place.get("extensions", []))
    return {
        "place_id":          place.get("place_id", ""),
        "business_name":     place.get("title", "").strip(),
        "address":           place.get("address", ""),
        "phone":             place.get("phone", ""),
        "website":           place.get("website", ""),
        "description":       place.get("description", ""),
        "rating":            float(place.get("rating") or 0.0),
        "reviews_count":     int(place.get("reviews") or 0),
        "lat":               float(gps.get("latitude")  or 0.0),
        "lng":               float(gps.get("longitude") or 0.0),
        "types":             [place.get("type", "")],
        "highlights":        extensions["highlights"],
        "offerings":         extensions["offerings"],
        "from_the_business": extensions["from_the_business"],
        "segment":           segment,
        "city":              city,
        "state":             "",
        "tier":              1,
        "num_outlets":       1,
        "is_chain":          False,
        "source":            "serpapi_google_maps",
    }


async def _hunter_discover(query: str, limit: int = 50) -> list[dict]:
    """
    Calls Hunter Discover API for a free-text query and returns a list of
    normalised business dicts with whatever Hunter knows (domain, org name).
    These are merged into Stage 1 results so their domains are available for
    Stage 6 email enrichment even if SerpAPI didn't find them.
    """
    if not HUNTER_API_KEY:
        return []
    try:
        async with AsyncPyHunter(HUNTER_API_KEY) as hunter:
            data = await hunter.discover(query=query, limit=limit)
        companies = (data or {}).get("data", [])
        logger.info(f"[Extract] Hunter Discover '{query}': {len(companies)} result(s)")
        return companies
    except Exception as exc:
        logger.warning(f"[Extract] Hunter Discover failed for '{query}': {exc}")
        return []


def _hunter_company_to_biz(company: dict, segment: str, city: str) -> dict:
    """
    Normalise a Hunter Discover company record to the same shape as a
    SerpAPI Google Maps result so both sources flow through identical stages.
    """
    org    = company.get("organization") or ""
    domain = company.get("domain") or ""
    return {
        "place_id":          f"hunter_{domain}",
        "business_name":     org,
        "address":           "",
        "phone":             "",
        "website":           f"https://{domain}" if domain else "",
        "description":       "",
        "rating":            0.0,
        "reviews_count":     0,
        "lat":               0.0,
        "lng":               0.0,
        "types":             [],
        "highlights":        [],
        "offerings":         [],
        "from_the_business": [],
        "segment":           segment,
        "city":              city,
        "state":             "",
        "tier":              1,
        "num_outlets":       1,
        "is_chain":          False,
        "source":            "hunter_discover",
    }


async def extract_business_data(
    city: str,
    session: AsyncSession,
    segment_filter: str | None = None,
) -> list:
    """
    Stage 1: Discover HORECA businesses via SerpAPI Google Maps + Hunter Discover.
    SerpAPI provides rich place data; Hunter Discover adds companies whose
    domains Hunter knows, seeding Stage 6 email enrichment.
    Paginates SerpAPI up to 3 pages per query; deduplicates by place_id / domain.
    """
    if not SERP_API_KEY:
        logger.warning("[Extract] SERP_API_KEY not set – skipping extraction.")
        return []

    if segment_filter:
        curated = _FULL_QUERY_MAP.get(segment_filter)
        if curated:
            queries   = curated
        else:
            label   = re.sub(r"([A-Z])", r" \1", segment_filter).strip()
            queries = [f"{segment_filter} in {{city}}", f"{label.lower()} {{city}}"]
        query_map = {segment_filter: queries}
    else:
        query_map = HORECA_QUERY_MAP

    seen_ids: set  = set()
    results:  list = []

    for segment, query_templates in query_map.items():
        for query_template in query_templates:
            query = query_template.format(city=city)

            # ── Run SerpAPI pages + Hunter Discover concurrently ─────────────
            hunter_query = f"{segment} companies in {city} India"
            serp_pages, hunter_companies = await asyncio.gather(
                asyncio.gather(*[
                    _serp_maps_page(query, start=page_num * 20)
                    for page_num in range(3)
                ]),
                _hunter_discover(hunter_query, limit=50),
            )

            # ── Merge SerpAPI results ────────────────────────────────────────
            for page_num, places in enumerate(serp_pages):
                if not places:
                    break
                logger.info(f"[Extract] '{query}' page {page_num + 1}: {len(places)} results")
                for place in places:
                    pid = place.get("place_id") or place.get("title", "")
                    if not pid or pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    results.append(_normalize_serp_result(place, segment, city))
                await asyncio.sleep(0.5)

            # ── Merge Hunter Discover results (skip duplicates by domain) ────
            for company in hunter_companies:
                domain = company.get("domain") or ""
                pid    = f"hunter_{domain}"
                if not domain or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                biz = _hunter_company_to_biz(company, segment, city)
                results.append(biz)
                logger.debug(f"[Extract] Hunter Discover added: {biz['business_name']} ({domain})")

    logger.info(f"[Extract] Total unique businesses for '{city}': {len(results)}")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2 – AI PROCESSING (Gemini)
# ══════════════════════════════════════════════════════════════════════════════

async def ai_process_business_data(raw_data: list, session: AsyncSession) -> list:
    """
    Stage 2: Enrich each business with Gemini AI — dessert/sugar menu
    classification, monthly sugar estimate, sweetness dependency %.
    """
    enriched = []
    print(f"Raw Data for enrichment based on KPIs: {raw_data}")

    for biz in raw_data:
        name              = biz.get("business_name", "")
        segment           = biz.get("segment", "Restaurant")
        city              = biz.get("city", "")
        website           = biz.get("website", "")
        rating            = biz.get("rating", 0.0)
        types             = ", ".join(biz.get("types", []))
        highlights        = biz.get("highlights", [])
        description       = biz.get("description", [])
        from_the_business = biz.get("from_the_business", [])

        highlights_text = ", ".join(highlights) if highlights else "Not available"
        description_text = ", ".join(description) if description else "Not available"
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
            ai = json.loads(call_genai(prompt, force_json=True))
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
            logger.warning(f"[AI] Processing failed for '{name}': {exc}")
            biz.setdefault("has_dessert_menu", segment in ["Cafe", "Bakery", "Hotel"])
            biz.setdefault("monthly_sugar_estimate_kg", 0)
            biz.setdefault("sweetness_dependency_pct", 0)
            biz.setdefault("sugar_signal_from_highlights", False)
            biz.setdefault("highlight_sugar_signals", [])
            biz.setdefault("ai_reasoning", "")

        enriched.append(biz)

    logger.info(f"[AI] Processed {len(enriched)} businesses.")
    return enriched


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 3 – KPI FILTERING
# ══════════════════════════════════════════════════════════════════════════════

async def apply_kpi_filtering(ai_data: list, session: AsyncSession) -> list:
    """
    Stage 3: Score every business, attach kpi_score / priority, and discard
    those below the minimum threshold (20).
    """
    MIN_KPI_SCORE = 20.0
    filtered      = []

    for biz in ai_data:
        kpi, priority, reasoning = _compute_kpi_score(biz)
        biz["kpi_score"]    = kpi
        biz["priority"]     = priority
        biz["ai_reasoning"] = reasoning

        if kpi < MIN_KPI_SCORE:
            logger.debug(f"[KPI] Rejected '{biz.get('business_name')}' (score={kpi})")
            continue
        filtered.append(biz)

    logger.info(f"[KPI] {len(filtered)}/{len(ai_data)} passed KPI filter (threshold={MIN_KPI_SCORE})")
    return filtered


def _compute_kpi_score(biz: dict) -> tuple:
    """
    Composite KPI formula (100-point scale):
      sugar_consumption 0.20 | sweetness_dep 0.15 | dessert_menu 0.15
      segment_weight 0.10    | outlet_count 0.10  | rating 0.10
      review_strength 0.10   | hotel_category 0.05 | is_chain 0.05
    """
    score, reasons = 0.0, []

    sugar_kg   = float(biz.get("monthly_sugar_estimate_kg", 0) or 0)
    sugar_norm = min(sugar_kg / 1000.0, 1.0) * 100
    score     += sugar_norm * 0.20
    reasons.append(f"Sugar ~{sugar_kg} kg/month")

    sweet  = float(biz.get("sweetness_dependency_pct", 0) or 0)
    score += sweet * 0.15
    if sweet > 50:
        reasons.append(f"Sweetness dependency {sweet}%")

    if biz.get("has_dessert_menu"):
        score += 15
        reasons.append("Has dessert menu")

    if biz.get("sugar_signal_from_highlights"):
        score += 10
        signals = biz.get("highlight_sugar_signals", [])
        reasons.append(f"Highlight sugar signals: {', '.join(signals[:3])}")

    seg_w  = SEGMENT_WEIGHTS.get(biz.get("segment", "Restaurant"), 50)
    score += seg_w * 0.10
    reasons.append(f"Segment {biz.get('segment')} (w={seg_w})")

    outlets    = int(biz.get("num_outlets", 1) or 1)
    outlet_scr = min(outlets * 5, 100)
    score     += outlet_scr * 0.10
    if outlets > 5:
        reasons.append(f"{outlets} outlets")

    rating = float(biz.get("rating", 0) or 0)
    score += min((rating / 5.0) * 100, 100) * 0.10

    reviews = int(biz.get("reviews_count", 0) or 0)
    score  += min((reviews / 500.0) * 100, 100) * 0.10
    if reviews > 100:
        reasons.append(f"{reviews} reviews")

    hotel_cat_scores = {"5-star": 100, "4-star": 75, "3-star": 50}
    score += hotel_cat_scores.get(biz.get("hotel_category", ""), 0) * 0.05

    if biz.get("is_chain"):
        score += 5
        reasons.append("Chain business")

    score    = round(min(score, 100), 2)
    priority = "High" if score >= 65 else ("Medium" if score >= 35 else "Low")
    return score, priority, " | ".join(reasons) or "Low data quality"



# ══════════════════════════════════════════════════════════════════════════════
# STAGE 4 – DEDUPLICATION
# ══════════════════════════════════════════════════════════════════════════════

def _normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name)
    stopwords = {"the", "a", "an", "and", "or", "of", "in", "at", "on"}
    return " ".join(w for w in name.split() if w not in stopwords).strip()


def _geo_hash(lat: float, lng: float, precision: int = 3) -> str:
    return f"{round(lat, precision)}:{round(lng, precision)}"


def _jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


async def deduplicate_leads(filtered_data: list, session: AsyncSession) -> list:
    """
    Stage 4: Remove duplicates using Jaccard name similarity + geo proximity.
    Cross-checks existing DB leads to avoid re-inserting known businesses.
    """
    existing: set = set()
    try:
        rows = (await session.execute(select(Lead.business_name, Lead.city))).all()
        for row in rows:
            existing.add(_normalize_name(f"{row.business_name}_{row.city}"))
    except Exception as exc:
        logger.warning(f"[Dedup] Could not load existing leads: {exc}")

    seen:   list = []
    deduped: list = []

    for biz in filtered_data:
        norm   = _normalize_name(biz.get("business_name", ""))
        city   = biz.get("city", "")
        db_key = _normalize_name(f"{biz.get('business_name', '')}_{city}")

        if db_key in existing:
            logger.debug(f"[Dedup] Already in DB: '{biz.get('business_name')}'")
            continue

        lat = float(biz.get("lat", 0) or 0)
        lng = float(biz.get("lng", 0) or 0)
        geo = _geo_hash(lat, lng) if (lat and lng) else None

        is_dup = False
        for s in seen:
            s_norm = _normalize_name(s.get("business_name", ""))
            sim    = _jaccard(norm, s_norm)
            s_lat  = float(s.get("lat", 0) or 0)
            s_lng  = float(s.get("lng", 0) or 0)
            s_geo  = _geo_hash(s_lat, s_lng) if (s_lat and s_lng) else None
            if sim > 0.8 or (sim > 0.6 and geo and s_geo and geo == s_geo):
                is_dup = True
                break

        if not is_dup:
            seen.append(biz)
            deduped.append(biz)

    logger.info(f"[Dedup] {len(deduped)}/{len(filtered_data)} unique leads after dedup.")
    return deduped


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 5 – CONTACT ENRICHMENT (SerpAPI + Gemini)
# ══════════════════════════════════════════════════════════════════════════════

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _serp_search(query: str) -> list:
    """Google web search via SerpAPI."""
    if not SERP_API_KEY:
        return []
    params = {"q": query, "api_key": SERP_API_KEY, "num": 5, "engine": "google"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get("https://serpapi.com/search.json", params=params)
        logger.info(f"[SerpAPI] Query: {query} — Status: {resp.status_code}")
        resp.raise_for_status()
        return resp.json().get("organic_results", [])


async def _ai_extract_contact(biz_name: str, city: str, segment: str, serp_snippets: list) -> dict:
    snippets_text = "\n".join(
        f"- {r.get('title', '')}: {r.get('snippet', '')}" for r in serp_snippets[:5]
    ) or "No search results found."

    prompt = contact_extraction_prompt(
        biz_name=biz_name,
        city=city,
        segment=segment,
        snippets_text=snippets_text,
    )
    try:
        return json.loads(call_genai(prompt, force_json=True))
    except Exception as exc:
        logger.warning(f"[Contacts] AI extraction failed for '{biz_name}': {exc}")
        return {"name": "", "role": "", "linkedin_url": "", "confidence_score": 0.0}


async def enrich_contacts(leads: list, session: AsyncSession) -> list:
    """
    Stage 5: SerpAPI search for decision-maker signals, Gemini extraction of
    name/role/LinkedIn. Best contact promoted to lead's decision_maker_* fields.
    """
    for biz in leads:
        name     = biz.get("business_name", "")
        city     = biz.get("city", "")
        segment  = biz.get("segment", "Restaurant")
        contacts: list = []

        for role_query in [
            "F&B Manager", "Procurement Manager", "Owner",
            "General Manager", "Operations Manager", "Sales Manager",
        ]:
            query = f'"{name}" {city} {role_query} LinkedIn'
            try:
                snippets = await _serp_search(query)
                contact  = await _ai_extract_contact(name, city, segment, snippets)
                if contact.get("name") and float(contact.get("confidence_score", 0)) >= 0.5:
                    if contact["name"] not in [c["name"] for c in contacts]:
                        contacts.append({
                            "name":             contact.get("name", ""),
                            "role":             contact.get("role", role_query),
                            "linkedin_url":     contact.get("linkedin_url", ""),
                            "email":            "",
                            "confidence_score": float(contact.get("confidence_score", 0.5)),
                            "source":           "serp+gemini",
                        })
            except Exception as exc:
                logger.warning(f"[Contacts] Search failed for '{name}'/'{role_query}': {exc}")

        if contacts:
            best = max(contacts, key=lambda c: c.get("confidence_score", 0))
            biz["decision_maker_name"]     = best.get("name", "")
            biz["decision_maker_role"]     = best.get("role", "")
            biz["decision_maker_linkedin"] = best.get("linkedin_url", "")

        biz["contacts"] = contacts
        logger.info(f"[Contacts] '{name}': {len(contacts)} contact(s) found.")

    return leads


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 6 – EMAIL ENRICHMENT (Hunter.io + Apollo.io fallback)
# ══════════════════════════════════════════════════════════════════════════════

HUNTER_TARGET_DEPARTMENTS  = "management,operations,executive,sales"
HUNTER_TARGET_SENIORITY    = "senior,executive"
HUNTER_VERIFICATION_STATUS = "valid,accept_all"

_DECISION_MAKER_KEYWORDS = [
    "f&b", "food", "beverage", "procurement", "purchase", "supply",
    "operations", "founder", "owner", "director", "manager", "head",
    "executive", "ceo", "coo", "gm", "general manager",
]

_DEPT_SCORE: dict[str, int] = {
    "executive":  100,
    "management":  90,
    "operations":  80,
    "sales":       70,
    "finance":     50,
    "support":     30,
}


def _extract_domain(website: str) -> str:
    if not website:
        return ""
    website = website.lower().strip()
    website = re.sub(r"^https?://", "", website)
    website = re.sub(r"^www\.", "", website)
    return website.split("/")[0]


def _score_hunter_contact(person: dict) -> int:
    score = 0
    dept     = (person.get("department") or "").lower()
    score   += _DEPT_SCORE.get(dept, 10)
    position = (person.get("position") or "").lower()
    hits     = sum(1 for kw in _DECISION_MAKER_KEYWORDS if kw in position)
    score   += min(hits * 30, 60)
    verification = (person.get("verification") or {}).get("status", "")
    if verification == "valid":
        score += 20
    elif verification == "accept_all":
        score += 10
    score += int((person.get("confidence") or 0) / 5)
    return score


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _hunter_fetch_all_contacts(domain: str) -> list:
    """Domain Search via PyHunter — fetches up to 3 pages of contacts."""
    if not HUNTER_API_KEY or not domain:
        return []

    all_contacts: list = []
    limit = 20

    async with AsyncPyHunter(
        HUNTER_API_KEY,
        max_retries=2,
        retry_backoff=0.5,
    ) as hunter:
        for page in range(3):
            offset = page * limit
            try:
                data = await hunter.domain_search(
                    domain,
                    limit=limit,
                    offset=offset,
                    seniority=HUNTER_TARGET_SENIORITY,
                    department=HUNTER_TARGET_DEPARTMENTS,
                    required_field="full_name",
                )
            except Exception as exc:
                logger.warning(f"[Emails] Hunter domain_search failed for '{domain}': {exc}")
                break

            emails = (data or {}).get("emails", [])
            if not emails:
                break

            for person in emails:
                email = person.get("value", "")
                if not email:
                    continue
                all_contacts.append({
                    "name":            f"{person.get('first_name') or ''} {person.get('last_name') or ''}".strip() or "Unknown",
                    "email":           email,
                    "role":            person.get("position") or "",
                    "department":      person.get("department") or "",
                    "seniority":       person.get("seniority") or "",
                    "linkedin_url":    person.get("linkedin") or "",
                    "confidence":      int(person.get("confidence") or 0),
                    "verified":        (person.get("verification") or {}).get("status", ""),
                    "relevance_score": _score_hunter_contact(person),
                    "source":          "hunter_domain_search",
                })

            # stop paginating if this page returned fewer results than requested
            if len(emails) < limit:
                break
            await asyncio.sleep(0.5)

    return all_contacts


async def _hunter_find_email(domain: str, full_name: str) -> dict:
    """
    Email Finder via PyHunter — targeted lookup for a known contact name.
    Used as a precision fallback when domain_search returns nothing.
    """
    if not HUNTER_API_KEY or not domain or not full_name:
        return {}

    parts = full_name.strip().split(" ", 1)
    first = parts[0]
    last  = parts[1] if len(parts) > 1 else ""

    async with AsyncPyHunter(HUNTER_API_KEY) as hunter:
        try:
            email, confidence = await hunter.email_finder(
                domain, first_name=first, last_name=last
            )
            if email:
                return {
                    "name":            full_name,
                    "email":           email,
                    "role":            "",
                    "department":      "",
                    "seniority":       "",
                    "linkedin_url":    "",
                    "confidence":      int(confidence or 0),
                    "verified":        "",
                    "relevance_score": 60,
                    "source":          "hunter_email_finder",
                }
        except Exception as exc:
            logger.debug(f"[Emails] Hunter email_finder failed for '{full_name}' @ '{domain}': {exc}")
    return {}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=6))
async def _apollo_find_email(full_name: str, domain: str) -> dict:
    if not APOLLO_API_KEY or not domain:
        return {}
    headers = {"Content-Type": "application/json", "x-api-key": APOLLO_API_KEY}
    payload = {"name": full_name, "domain": domain}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post("https://api.apollo.io/v1/people/match", json=payload, headers=headers)
        if resp.status_code == 200:
            person = resp.json().get("person", {})
            email  = person.get("email", "")
            return {
                "name":           full_name,
                "email":          email,
                "role":           person.get("title", ""),
                "linkedin_url":   person.get("linkedin_url", ""),
                "confidence":     80 if email else 0,
                "verified":       "unknown",
                "relevance_score": 50,
                "source":         "apollo",
            }
    return {}


async def enrich_emails(businesses: list, session: AsyncSession) -> list:
    """
    Stage 6: Hunter.io Domain Search → rank by procurement relevance →
    Apollo fallback → attach top contacts to each lead.
    """
    for biz in businesses:
        domain = _extract_domain(biz.get("website", ""))
        if not domain:
            continue

        hunter_contacts: list = []
        try:
            hunter_contacts = await _hunter_fetch_all_contacts(domain)
            logger.info(f"[Emails] Hunter: '{domain}' → {len(hunter_contacts)} contact(s)")
        except Exception as exc:
            logger.warning(f"[Emails] Hunter failed for '{domain}': {exc}")

        if not hunter_contacts:
            dm_name = biz.get("decision_maker_name", "")
            if dm_name and domain:
                try:
                    finder_result = await _hunter_find_email(domain, dm_name)
                    if finder_result.get("email"):
                        hunter_contacts = [finder_result]
                        logger.info(f"[Emails] Hunter email_finder hit for '{dm_name}' @ '{domain}'")
                except Exception as exc:
                    logger.debug(f"[Emails] Hunter email_finder failed for '{domain}': {exc}")

        if not hunter_contacts:
            dm_name = biz.get("decision_maker_name", "")
            if dm_name:
                try:
                    apollo_result = await _apollo_find_email(dm_name, domain)
                    if apollo_result.get("email"):
                        hunter_contacts = [apollo_result]
                except Exception as exc:
                    logger.debug(f"[Emails] Apollo failed for '{domain}': {exc}")

        if not hunter_contacts:
            continue

        ranked = sorted(hunter_contacts, key=lambda c: c.get("relevance_score", 0), reverse=True)
        existing_contacts = {c.get("name", ""): c for c in biz.get("contacts", [])}

        for hc in ranked:
            name = hc.get("name", "")
            if name in existing_contacts:
                existing_contacts[name].update({
                    "email":            hc["email"],
                    "email_confidence": hc["confidence"],
                    "verified":         hc["verified"],
                    "department":       hc.get("department", ""),
                    "seniority":        hc.get("seniority", ""),
                })
                if not existing_contacts[name].get("linkedin_url"):
                    existing_contacts[name]["linkedin_url"] = hc.get("linkedin_url", "")
            else:
                existing_contacts[name] = {
                    "name":             name,
                    "role":             hc.get("role", ""),
                    "email":            hc["email"],
                    "linkedin_url":     hc.get("linkedin_url", ""),
                    "confidence_score": round(hc["confidence"] / 100, 2),
                    "email_confidence": hc["confidence"],
                    "verified":         hc["verified"],
                    "department":       hc.get("department", ""),
                    "seniority":        hc.get("seniority", ""),
                    "relevance_score":  hc.get("relevance_score", 0),
                    "source":           hc.get("source", "hunter_domain_search"),
                }

        biz["contacts"] = list(existing_contacts.values())
        best = max(biz["contacts"], key=lambda c: c.get("relevance_score", 0))
        if best.get("email"):
            biz["email"] = best["email"]
        if best.get("name") and not biz.get("decision_maker_name"):
            biz["decision_maker_name"]     = best["name"]
            biz["decision_maker_role"]     = best.get("role", "")
            biz["decision_maker_linkedin"] = best.get("linkedin_url", "")

        logger.info(
            f"[Emails] '{biz.get('business_name')}': "
            f"{len(biz['contacts'])} enriched contact(s)"
        )

    return businesses


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 7 – PERSONALIZED EMAIL GENERATION (Gemini)
# ══════════════════════════════════════════════════════════════════════════════

async def generate_personalized_emails(enriched_leads: list, session: AsyncSession) -> list:
    """
    Stage 7: Gemini generates a personalized 150-200 word outreach email per
    qualified lead (subject + body). Returns list of email dicts ready for DB.
    """
    emails = []

    for biz in enriched_leads:
        name         = biz.get("business_name", "")
        city         = biz.get("city", "")
        segment      = biz.get("segment", "Restaurant")
        contact_name = biz.get("decision_maker_name", "")
        contact_role = biz.get("decision_maker_role", "Procurement Team")
        has_dessert  = biz.get("has_dessert_menu", False)
        sugar_kg     = biz.get("monthly_sugar_estimate_kg", 0)
        reasoning    = biz.get("ai_reasoning", "")
        rating       = biz.get("rating", 0)
        hotel_cat    = biz.get("hotel_category", "")

        prompt = email_generation_prompt(
            name=name,
            city=city,
            segment=segment,
            contact_name=contact_name,
            contact_role=contact_role,
            has_dessert=has_dessert,
            sugar_kg=sugar_kg,
            rating=rating,
            hotel_cat=hotel_cat,
            reasoning=reasoning,
        )
        try:
            result = json.loads(call_genai(prompt, force_json=True))
            emails.append({
                "lead_name":    name,
                "lead_city":    city,
                "lead_segment": segment,
                "subject":      result.get("subject", ""),
                "body":         result.get("body", ""),
                "status":       "draft",
                "business":     biz,
            })
            logger.info(f"[EmailGen] Generated email for '{name}'")
        except Exception as exc:
            logger.warning(f"[EmailGen] Failed for '{name}': {exc}")

    logger.info(f"[EmailGen] {len(emails)} emails generated.")
    return emails


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 8 – STORAGE (DB)
# ══════════════════════════════════════════════════════════════════════════════

async def store_leads_and_emails(final_leads: list, session: AsyncSession) -> bool:
    """
    Stage 8: Persist Lead, Contact, and OutreachEmail records to the DB in a
    single transaction. Rolls back on failure.
    """
    stored = 0

    for item in final_leads:
        biz = item.get("business", {})
        try:
            now  = datetime.now(timezone.utc)
            lead = Lead(
                id                           = str(uuid.uuid4()),
                business_name                = biz.get("business_name", ""),
                segment                      = biz.get("segment", "Restaurant"),
                city                         = biz.get("city", ""),
                state                        = biz.get("state", ""),
                country                      = biz.get("country", "India"),
                tier                         = int(biz.get("tier", 2) or 2),
                address                      = biz.get("address", ""),
                phone                        = biz.get("phone", ""),   # business phone from Stage 1
                email                        = biz.get("email", ""),   # business email from Stage 1
                website                      = biz.get("website", ""),
                description                  = biz.get("description", ""),
                rating                       = float(biz.get("rating", 0) or 0),
                num_outlets                  = int(biz.get("num_outlets", 1) or 1),
                has_dessert_menu             = bool(biz.get("has_dessert_menu", False)),
                hotel_category               = biz.get("hotel_category", ""),
                is_chain                     = bool(biz.get("is_chain", False)),
                ai_score                     = int(biz.get("kpi_score", 0) or 0),
                ai_reasoning                 = biz.get("ai_reasoning", ""),
                priority                     = biz.get("priority", "Low"),
                status                       = "new",
                source                       = biz.get("source", "pipeline"),
                monthly_volume_estimate      = f"{biz.get('monthly_sugar_estimate_kg', '')} kg",
                highlights                   = biz.get("highlights", []),
                offerings                    = biz.get("offerings", []),
                dining_options               = biz.get("dining_options", []),
                sugar_signal_from_highlights = bool(biz.get("sugar_signal_from_highlights", False)),
                highlight_sugar_signals      = biz.get("highlight_sugar_signals", []),
                created_at                   = now,
                updated_at                   = now,
            )
            session.add(lead)
            await session.flush()  # resolve lead.id before FK references

            for cd in biz.get("contacts", []):
                if not cd.get("name"):
                    continue
                session.add(Contact(
                    lead_id          = lead.id,
                    name             = cd.get("name", ""),
                    role             = cd.get("role", ""),
                    email            = cd.get("email", ""),
                    email_2          = cd.get("email_2", ""),
                    phone            = cd.get("phone", ""),
                    phone_2          = cd.get("phone_2", ""),
                    linkedin_url     = cd.get("linkedin_url", ""),
                    confidence_score = float(cd.get("confidence_score", 0.0) or 0.0),
                    verified         = cd.get("verified", ""),
                    source           = cd.get("source", "pipeline"),
                    seniority        = cd.get("seniority", ""),
                    department       = cd.get("department", ""),
                    is_primary       = bool(cd.get("is_primary", False)),
                    created_at       = now,
                    updated_at       = now,
                ))

            session.add(OutreachEmail(
                id           = str(uuid.uuid4()),
                lead_id      = lead.id,
                lead_name    = item.get("lead_name", ""),
                lead_city    = item.get("lead_city", ""),
                lead_segment = item.get("lead_segment", ""),
                subject      = item.get("subject", ""),
                body         = item.get("body", ""),
                status       = "draft",
                generated_at = now,
            ))

            stored += 1

        except Exception as exc:
            logger.error(f"[Store] Failed for '{biz.get('business_name')}': {exc}")
            continue

    try:
        await session.commit()
        logger.info(f"[Store] {stored} leads (+ contacts + emails) committed to DB.")
        return True
    except Exception as exc:
        await session.rollback()
        logger.error(f"[Store] DB commit failed: {exc}")
        return False
