# pipeline_stages.py
"""
Full ETL pipeline stages for the HORECA lead generation system.

Stages:
  1. extract_business_data     – SerpAPI Google Maps (multi-query, all HORECA segments)
  2. ai_process_business_data  – Gemini: menu, dessert, sugar classification
  3. apply_kpi_filtering       – Composite KPI score + threshold rejection
  4. deduplicate_leads         – Fuzzy name + geo dedup + DB cross-check
  5. enrich_contacts           – SerpAPI + Gemini AI contact discovery
  6. enrich_emails             – Hunter.io + Apollo.io email enrichment
  7. generate_personalized_emails – Gemini AI outreach email generation
  8. store_leads_and_emails    – Persist leads, contacts, emails to DB
"""

import os
import re
import json
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx
import serpapi as serpapi_client
from concurrent.futures import ThreadPoolExecutor
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from dotenv import load_dotenv
from pathlib import Path

from models import Lead, City, OutreachEmail, PipelineRun, Contact
from genai_helper import call_genai

load_dotenv(Path(__file__).parent / '.env')
logger = logging.getLogger(__name__)

# ─── ENV KEYS ────────────────────────────────────────────────────────────────
# Stage 1: SerpAPI Google Maps (primary extraction source)
SERP_API_KEY   = os.getenv("SERP_API_KEY", "")
# Stage 6: Email enrichment
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")


HORECA_QUERY_MAP: dict[str, list[str]] = {
    # ── A. Bakery & Confectionery ──────────────────────────────────────────
    "Bakery":           ["bakeries in {city}", "cake shop {city}", "patisserie {city}"],
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
    "Bakery":         ["bakeries in {city}", "cake shop {city}", "patisserie {city}"],
    "IceCream":       ["ice cream parlour {city}", "gelato shop {city}", "frozen dessert {city}"],
    "Beverage":       ["juice manufacturer {city}", "beverage company {city}", "syrup manufacturer {city}"],
    "Restaurant":     ["restaurants in {city}", "fine dining {city}"],
    "Cafe":           ["cafes in {city}", "coffee shops {city}", "dessert cafe {city}"],
    "Hotel":          ["hotels in {city}", "luxury hotels {city}"],
    "Catering":       ["catering services {city}", "event caterers {city}"],
    "CloudKitchen":   ["cloud kitchen {city}", "dark kitchen {city}"],
    "Mithai":         ["sweet shop {city}", "mithai shop {city}", "halwai {city}"],
    "FoodProcessing": ["biscuit manufacturer {city}", "packaged food company {city}", "food processing unit {city}"],
    "Organic":        ["organic food brand {city}", "jaggery products {city}", "ayurvedic food company {city}"],
    "Brewery":        ["brewery {city}", "distillery {city}", "craft beer {city}"],
}

SEGMENT_WEIGHTS = {
    # High-volume, daily consumers
    "Mithai":           100,
    "Bakery":           100,
    "FoodProcessing":   95,
    "IceCream":         90,
    "Beverage":         88,
    # Medium-volume
    "Catering":         80,
    "Cafe":             78,
    "CloudKitchen":     72,
    "Organic":          70,
    "Brewery":          65,
    # Lower per-unit but large collective volume
    "Restaurant":       60,
    "Hotel":            55,
}

ROLE_PRIORITY = [
    # Procurement / Purchase — highest decision power
    "Procurement Manager", "Purchase Manager", "Purchase Head",
    "Supply Chain Manager", "Supply Chain Head",
    # F&B / Production
    "F&B Manager", "F&B Director", "Production Manager", "Plant Manager",
    # Ops / General management
    "Operations Manager", "Operations Director",
    "Store Manager", "General Manager",
    # Founders / Owners
    "Owner", "Founder", "Co-Founder", "Director",
]


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 – DATA EXTRACTION (SerpAPI Google Maps)
# ══════════════════════════════════════════════════════════════════════════════

# Thread pool for running the synchronous serpapi client inside async context
_executor = ThreadPoolExecutor(max_workers=4)


def _serp_maps_search_sync(query: str, api_key: str, start: int = 0) -> dict:
    """
    Synchronous SerpAPI call using the official serpapi Python client.
    Runs in a thread pool so it doesn't block the event loop.
    """
    client = serpapi_client.Client(api_key=api_key)
    return client.search({
        "engine":  "google_maps",
        "q":       query,
        "type":    "search",
        "start":   start,        # pagination offset (0, 20, 40 …)
        "hl":      "en",
        "gl":      "in",         # country = India
    })


async def _serp_maps_page(query: str, start: int = 0) -> list:
    """Async wrapper — runs one SerpAPI Maps page in the thread pool."""
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            _executor,
            _serp_maps_search_sync,
            query,
            SERP_API_KEY,
            start,
        )
        return result.get("local_results", [])
    except Exception as exc:
        logger.error(f"[Extract] SerpAPI failed for '{query}' (start={start}): {exc}")
        return []


def _parse_extensions(raw_extensions: list) -> dict:
    """
    Flatten the SerpAPI extensions list into a structured dict.

    SerpAPI returns extensions as a list of dicts, each with one key:
      [{"highlights": [...]}, {"service_options": [...]}, {"from_the_business": [...]}]
    """
    parsed = {"highlights": [], "from_the_business": []}
    for ext in (raw_extensions or []):
        for key in ("highlights", "from_the_business"):
            if key in ext:
                parsed[key].extend(ext[key])
    return parsed


def _infer_segment_from_query(query: str, segment_key: str) -> str:
    """Return the HORECA segment that generated this query."""
    return segment_key


def _normalize_serp_result(place: dict, segment: str, city: str) -> dict:
    """
    Map a SerpAPI Google Maps local_result dict to a normalised business dict.

    SerpAPI local_result fields used:
      place_id, title, address, phone, website,
      rating, reviews, gps_coordinates, type, extensions
    """
    gps        = place.get("gps_coordinates") or {}
    extensions = _parse_extensions(place.get("extensions", []))

    return {
        "place_id":         place.get("place_id", ""),
        "business_name":    place.get("title", "").strip(),
        "address":          place.get("address", ""),
        "phone":            place.get("phone", ""),
        "website":          place.get("website", ""),
        "description":      place.get("description", ""),
        "rating":           float(place.get("rating") or 0.0),
        "reviews_count":    int(place.get("reviews") or 0),
        "lat":              float(gps.get("latitude")  or 0.0),
        "lng":              float(gps.get("longitude") or 0.0),
        "types":            [place.get("type", "")],
        # ── extension fields ────────────────────────────────────────────────
        "highlights":       extensions["highlights"],        # e.g. ["Great dessert", "Great coffee"]
        "from_the_business":extensions["from_the_business"], # e.g. ["Identifies as women-owned"]
        # ── classification ──────────────────────────────────────────────────
        "segment":          segment,
        "city":             city,
        "state":            "",
        "tier":             1,
        "num_outlets":      1,
        "is_chain":         False,
        "source":           "serpapi_google_maps",
    }


async def extract_business_data(
    city: str,
    session: AsyncSession,
    segment_filter: Optional[str] = None,
) -> list:
    """
    Stage 1: Discover HORECA businesses via SerpAPI Google Maps engine.

    - If segment_filter is provided: queries only that segment using _FULL_QUERY_MAP
      (used by the on-demand /discover endpoint)
    - If segment_filter is None: iterates every segment in HORECA_QUERY_MAP
      (used by the weekly cron)
    - Paginates up to 3 pages (start=0, 20, 40) per query → up to 60 results
    - Deduplicates by place_id across all queries
    - Returns a list of normalised business dicts

    API: https://serpapi.com/search.json?engine=google_maps&q=<query>
    """
    if not SERP_API_KEY:
        logger.warning("[Extract] SERP_API_KEY not set – skipping extraction.")
        return []

    # Choose query map based on whether a specific segment was requested
    if segment_filter:
        # Use curated queries if available, otherwise auto-generate generic ones
        # so that admin-defined segments (not in _FULL_QUERY_MAP) still work.
        curated = _FULL_QUERY_MAP.get(segment_filter)
        if curated:
            queries = curated
            logger.info(f"[Extract] Segment filter '{segment_filter}': using {len(queries)} curated queries")
        else:
            # Fallback: derive reasonable search terms from the segment key
            # e.g. "FarmToTable" → ["FarmToTable in {city}", "farm to table {city}"]
            label = re.sub(r'([A-Z])', r' \1', segment_filter).strip()  # CamelCase → words
            queries = [
                f"{segment_filter} in {{city}}",
                f"{label.lower()} {{city}}",
            ]
            logger.info(
                f"[Extract] Segment filter '{segment_filter}' not in _FULL_QUERY_MAP – "
                f"auto-generated {len(queries)} generic queries"
            )
        query_map = {segment_filter: queries}
    else:
        query_map = HORECA_QUERY_MAP
        logger.info(f"[Extract] No segment filter — querying all {len(query_map)} segments from HORECA_QUERY_MAP")

    seen_ids: set  = set()
    results:  list = []

    for segment, query_templates in query_map.items():
        for query_template in query_templates:
            query = query_template.format(city=city)

            for page_num in range(3):            # 3 pages × 20 results = up to 60 per query
                start = page_num * 20
                places = await _serp_maps_page(query, start=start)

                if not places:
                    break                        # no more results for this query

                logger.info(
                    f"[Extract] '{query}' page {page_num + 1}: {len(places)} results"
                )

                for place in places:
                    pid = place.get("place_id") or place.get("title", "")
                    if not pid or pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    results.append(_normalize_serp_result(place, segment, city))

                await asyncio.sleep(0.5)         # stay within SerpAPI rate limits

    logger.info(f"[Extract] Total unique businesses for '{city}': {len(results)}")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2 – AI PROCESSING (Gemini)
# ══════════════════════════════════════════════════════════════════════════════

async def ai_process_business_data(raw_data: list, session: AsyncSession) -> list:
    """
    Stage 2: Use Gemini to enrich each business with:
      - Dessert / sugar menu classification
      - Monthly sugar consumption estimate
      - Sweetness dependency %
      - Business segment correction

      Sends each business to Gemini with a structured prompt — 
      gets back dessert menu flag, sugar item count, monthly sugar 
      kg estimate, sweetness dependency %, hotel category, and AI reasoning
    """
    enriched = []
    print(f"Raw Data for enrichment based on KPIs: {raw_data}")

    for biz in raw_data:
        name             = biz.get("business_name", "")
        segment          = biz.get("segment", "Restaurant")
        city             = biz.get("city", "")
        website          = biz.get("website", "")
        rating           = biz.get("rating", 0.0)
        types            = ", ".join(biz.get("types", []))
        highlights       = biz.get("highlights", [])
        description      = biz.get("description", [])
        from_the_business= biz.get("from_the_business", [])

        # Format highlights for the prompt
        highlights_text = ", ".join(highlights) if highlights else "Not available"
        description_text = ", ".join(description) if description else "Not available"
        # service_text    = ", ".join(service_options) if service_options else "Not available"
        identity_text   = ", ".join(from_the_business) if from_the_business else "Not available"

        prompt = f"""
You are a HORECA business intelligence analyst for a sugar supplier in India.

Analyze this business and return intelligence for sugar sales targeting:

Business Name  : {name}
Segment        : {segment}
City           : {city}
Website        : {website or 'Not available'}
Rating         : {rating}/5
Types          : {types}
Description    : {description_text}
Highlights     : {highlights_text}
Business Tags  : {identity_text}

IMPORTANT: Pay close attention to the Highlights field and Description field.
Keywords like "Great dessert", "Great coffee", "Great tea selection", "Bakery items",
"Sweets", "Pastries", "Cakes", "Ice cream" are STRONG indicators of sugar consumption.

Return ONLY a JSON object with these exact fields:
{{
  "has_dessert_menu"              : true or false,
  "sugar_items_count"             : <integer – estimated items on menu that need sugar>,
  "menu_categories"               : ["list", "of", "menu", "categories"],
  "avg_price_range"               : "<budget | mid-range | premium>",
  "business_classification"       : "<Hotel | Restaurant | Cafe | Bakery | Catering>",
  "is_chain"                      : true or false,
  "hotel_category"                : "<3-star | 4-star | 5-star | empty string if not hotel>",
  "monthly_sugar_estimate_kg"     : <integer – estimated kg sugar per month based on highlights and description>,
  "sweetness_dependency_pct"      : <integer 0-100 – % of menu that is sugar-dependent based on highlights and description>,
  "sugar_signal_from_highlights"  : true or false,
  "highlight_sugar_signals"       : ["list of highlight keywords that indicate sugar usage"],
  "ai_reasoning"                  : "<1-2 sentence justification that mentions highlights and description if relevant>"
}}
"""
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

def _compute_kpi_score(biz: dict) -> tuple:
    """
    Composite KPI formula (100-point scale):
      sugar_consumption   0.20
      sweetness_dep       0.15
      dessert_menu        0.15
      segment_weight      0.10
      outlet_count        0.10
      rating              0.10
      review_strength     0.10
      hotel_category      0.05
      is_chain            0.05
    """
    score   = 0.0
    reasons = []

    # Sugar consumption (kg/month) → normalised to 0-100
    sugar_kg   = float(biz.get("monthly_sugar_estimate_kg", 0) or 0)
    sugar_norm = min(sugar_kg / 1000.0, 1.0) * 100
    score     += sugar_norm * 0.20
    reasons.append(f"Sugar ~{sugar_kg} kg/month")

    # Sweetness dependency %
    sweet = float(biz.get("sweetness_dependency_pct", 0) or 0)
    score += sweet * 0.15
    if sweet > 50:
        reasons.append(f"Sweetness dependency {sweet}%")

    # Dessert menu present
    if biz.get("has_dessert_menu"):
        score += 15
        reasons.append("Has dessert menu")

    # AI detected sugar signals from Google Maps highlights
    if biz.get("sugar_signal_from_highlights"):
        score += 10
        signals = biz.get("highlight_sugar_signals", [])
        reasons.append(f"Highlight sugar signals: {', '.join(signals[:3])}")

    # Segment weight
    seg_w  = SEGMENT_WEIGHTS.get(biz.get("segment", "Restaurant"), 50)
    score += seg_w * 0.10
    reasons.append(f"Segment {biz.get('segment')} (w={seg_w})")

    # Outlet count
    outlets    = int(biz.get("num_outlets", 1) or 1)
    outlet_scr = min(outlets * 5, 100)
    score     += outlet_scr * 0.10
    if outlets > 5:
        reasons.append(f"{outlets} outlets")

    # Rating
    rating = float(biz.get("rating", 0) or 0)
    score += min((rating / 5.0) * 100, 100) * 0.10

    # Review volume
    reviews = int(biz.get("reviews_count", 0) or 0)
    score  += min((reviews / 500.0) * 100, 100) * 0.10
    if reviews > 100:
        reasons.append(f"{reviews} reviews")

    # Hotel category
    hotel_cat_scores = {"5-star": 100, "4-star": 75, "3-star": 50}
    score += hotel_cat_scores.get(biz.get("hotel_category", ""), 0) * 0.05

    # Chain bonus
    if biz.get("is_chain"):
        score += 5
        reasons.append("Chain business")

    score    = round(min(score, 100), 2)
    priority = "High" if score >= 65 else ("Medium" if score >= 35 else "Low")
    return score, priority, " | ".join(reasons) or "Low data quality"


async def apply_kpi_filtering(ai_data: list, session: AsyncSession) -> list:
    """
    Stage 3: Score every business, attach kpi_score / priority, and discard
    those below the minimum threshold.

    Computes a 100-point composite KPI score using 9 weighted factors (sugar 
    consumption, sweetness %, dessert menu, segment, outlet count, rating, 
    reviews, hotel category, chain bonus). Rejects businesses scoring < 20.
    """
    MIN_KPI_SCORE = 20.0
    filtered = []

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


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 4 – DEDUPLICATION
# ══════════════════════════════════════════════════════════════════════════════

def _normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r'[^a-z0-9\s]', '', name)
    name = re.sub(r'\s+', ' ', name)
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
    Also cross-checks existing DB leads to avoid re-inserting known businesses.

    Jaccard word-set similarity on normalized names + geo-hash proximity check. 
    Also cross-checks the DB to skip already-stored businesses
    """
    # Load existing lead names from DB
    existing: set = set()
    try:
        rows = (await session.execute(select(Lead.business_name, Lead.city))).all()
        for row in rows:
            existing.add(_normalize_name(f"{row.business_name}_{row.city}"))
    except Exception as exc:
        logger.warning(f"[Dedup] Could not load existing leads: {exc}")

    seen: list  = []
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
            geo_match = bool(geo and s_geo and geo == s_geo)

            if sim > 0.8 or (sim > 0.6 and geo_match):
                logger.debug(f"[Dedup] Dup: '{biz.get('business_name')}' ~ '{s.get('business_name')}'")
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
    """Google search via SerpAPI."""
    if not SERP_API_KEY:
        return []
    params = {"q": query, "api_key": SERP_API_KEY, "num": 5, "engine": "google"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get("https://serpapi.com/search.json", params=params)
        logger.info(f"[SerpAPI] Query: {query} — Status: {resp.status_code}, response: {resp}")
        resp.raise_for_status()
        return resp.json().get("organic_results", [])


async def _ai_extract_contact(biz_name: str, city: str, segment: str, serp_snippets: list) -> dict:
    """Gemini: extract the most likely decision-maker from SERP snippets."""
    snippets_text = "\n".join(
        f"- {r.get('title', '')}: {r.get('snippet', '')}"
        for r in serp_snippets[:5]
    ) or "No search results found."

    prompt = f"""
You are helping find the procurement decision-maker for a HORECA business in India.

Business : {biz_name}
City     : {city}
Segment  : {segment}

Web search results about this business:
{snippets_text}

Identify the most likely decision-maker for sugar / ingredient procurement.
Return ONLY a JSON object:
{{
  "name"             : "<full name or empty string>",
  "role"             : "<F&B Manager | Procurement Manager | Operations Manager | Store Manager | General Manager | Owner | Founder | empty>",
  "linkedin_url"     : "<LinkedIn URL or empty string>",
  "confidence_score" : <0.0–1.0>
}}
If no real contact is identifiable, return empty strings and confidence_score 0.0.
"""
    try:
        return json.loads(call_genai(prompt, force_json=True))
    except Exception as exc:
        logger.warning(f"[Contacts] AI extraction failed for '{biz_name}': {exc}")
        return {"name": "", "role": "", "linkedin_url": "", "confidence_score": 0.0}


async def enrich_contacts(leads: list, session: AsyncSession) -> list:
    """
    Stage 5: For each lead, search SerpAPI for decision-maker signals,
    then ask Gemini to extract a ranked contact list.

    SerpAPI searches "<name> <city> F&B Manager LinkedIn" for 3 role types, 
    then asks Gemini to extract name/role/LinkedIn URL + confidence score. 
    Best contact promoted to lead's decision_maker_* fields.
    """
    for biz in leads:
        name    = biz.get("business_name", "")
        city    = biz.get("city", "")
        segment = biz.get("segment", "Restaurant")
        contacts: list = []

        for role_query in ["F&B Manager", "Procurement Manager", "Owner", "General Manager", "Operations Manager", "Sales Manager"]:
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

        # Attach best contact to the lead dict
        if contacts:
            best = max(contacts, key=lambda c: c.get("confidence_score", 0))
            biz["decision_maker_name"]     = best.get("name", "")
            biz["decision_maker_role"]     = best.get("role", "")
            biz["decision_maker_linkedin"] = best.get("linkedin_url", "")

        biz["contacts"] = contacts
        logger.info(f"[Contacts] '{name}': {len(contacts)} contact(s) found.")

    return leads


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 6 – EMAIL ENRICHMENT (Hunter.io Domain Search + Apollo.io fallback)
# ══════════════════════════════════════════════════════════════════════════════

# Departments most likely to handle sugar / ingredient procurement in HORECA
HUNTER_TARGET_DEPARTMENTS = "management,operations,executive,sales"

# Seniority levels we care about (excludes junior)
HUNTER_TARGET_SENIORITY = "senior,executive"

# Only return emails that are verified or likely valid
HUNTER_VERIFICATION_STATUS = "valid,accept_all"

# Role keywords that indicate a procurement / F&B decision-maker
_DECISION_MAKER_KEYWORDS = [
    "f&b", "food", "beverage", "procurement", "purchase", "supply",
    "operations", "founder", "owner", "director", "manager", "head",
    "executive", "ceo", "coo", "gm", "general manager",
]

# Department → relevance score for ranking fetched contacts
_DEPT_SCORE: dict[str, int] = {
    "executive":   100,
    "management":   90,
    "operations":   80,
    "sales":        70,
    "finance":      50,
    "support":      30,
}


def _extract_domain(website: str) -> str:
    if not website:
        return ""
    website = website.lower().strip()
    website = re.sub(r'^https?://', '', website)
    website = re.sub(r'^www\.', '', website)
    return website.split('/')[0]


def _score_hunter_contact(person: dict) -> int:
    """
    Score a Hunter.io email record by how relevant the person is to
    sugar / ingredient procurement decisions.

    Scoring:
      - Department relevance   (0-100)
      - Role keyword match     (+30 per keyword hit, max 60)
      - Verification: valid    (+20) | accept_all (+10)
      - Confidence score       (+0-20 proportional)
    """
    score = 0

    dept = (person.get("department") or "").lower()
    score += _DEPT_SCORE.get(dept, 10)

    position = (person.get("position") or "").lower()
    hits = sum(1 for kw in _DECISION_MAKER_KEYWORDS if kw in position)
    score += min(hits * 30, 60)

    verification = (person.get("verification") or {}).get("status", "")
    if verification == "valid":
        score += 20
    elif verification == "accept_all":
        score += 10

    confidence = int(person.get("confidence") or 0)
    score += int(confidence / 5)        # max +20 when confidence = 100

    return score


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _hunter_domain_search(domain: str, limit: int = 20, offset: int = 0) -> dict:
    """
    Hunter.io Domain Search API.
    Endpoint : GET https://api.hunter.io/v2/domain-search
    Filtered by departments and seniority relevant to HORECA procurement.

    Returns the full JSON response dict.
    """
    if not HUNTER_API_KEY or not domain:
        return {}
    params = {
        "domain":              domain,
        # "type":                "personal",          # personal emails only
        # "department":          HUNTER_TARGET_DEPARTMENTS,
        # "seniority":           HUNTER_TARGET_SENIORITY,
        # "verification_status": HUNTER_VERIFICATION_STATUS,
        # "limit":               limit,
        # "offset":              offset,
        "api_key":             HUNTER_API_KEY,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get("https://api.hunter.io/v2/domain-search", params=params)
        if resp.status_code == 200:
            return resp.json()
        logger.warning(
            f"[Emails] Hunter domain-search {resp.status_code} for '{domain}': {resp.text[:200]}"
        )
    return {}


async def _hunter_fetch_all_contacts(domain: str) -> list:
    """
    Page through Hunter Domain Search results (up to 3 pages × 20 = 60 contacts).
    Returns a list of scored contact dicts ready for ranking.
    """
    all_contacts: list = []
    limit = 20

    for page in range(3):
        offset = page * limit
        data   = await _hunter_domain_search(domain, limit=limit, offset=offset)
        emails = (data.get("data") or {}).get("emails", [])

        if not emails:
            break

        for person in emails:
            email = person.get("value", "")
            if not email:
                continue
            all_contacts.append({
                "name":             f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                "email":            email,
                "role":             person.get("position") or "",
                "department":       person.get("department") or "",
                "seniority":        person.get("seniority") or "",
                "linkedin_url":     person.get("linkedin") or "",
                "confidence":       int(person.get("confidence") or 0),
                "verified":         (person.get("verification") or {}).get("status", ""),
                "relevance_score":  _score_hunter_contact(person),
                "source":           "hunter_domain_search",
            })

        # If Hunter returned fewer results than the limit, no more pages
        meta_results = (data.get("meta") or {}).get("results", 0)
        if offset + limit >= meta_results:
            break

        await asyncio.sleep(0.5)    # respect rate limit (15 req/s, 500 req/min)

    return all_contacts


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=6))
async def _apollo_find_email(full_name: str, domain: str) -> dict:
    """Apollo.io fallback – used when Hunter returns no results for a domain."""
    if not APOLLO_API_KEY or not domain:
        return {}
    headers = {"Content-Type": "application/json", "x-api-key": APOLLO_API_KEY}
    payload = {"name": full_name, "domain": domain}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://api.apollo.io/v1/people/match", json=payload, headers=headers
        )
        if resp.status_code == 200:
            person = resp.json().get("person", {})
            email  = person.get("email", "")
            return {
                "name":          full_name,
                "email":         email,
                "role":          person.get("title", ""),
                "linkedin_url":  person.get("linkedin_url", ""),
                "confidence":    80 if email else 0,
                "verified":      "unknown",
                "relevance_score": 50,
                "source":        "apollo",
            }
    return {}


async def enrich_emails(businesses: list, session: AsyncSession) -> list:
    """
    Stage 6: Hunter.io Domain Search → score & rank all contacts by procurement
    relevance → attach top contacts to each lead.

    Flow per business:
      1. Extract domain from website
      2. Call Hunter Domain Search (departments: management, operations, executive, sales)
      3. Score every returned person by role/department/verification
      4. Sort by relevance_score descending
      5. If Hunter returns nothing → Apollo.io fallback
      6. Attach top-ranked contacts; promote best email to business record
    """
    for biz in businesses:
        domain = _extract_domain(biz.get("website", ""))

        if not domain:
            logger.debug(f"[Emails] No domain for '{biz.get('business_name')}' – skipping.")
            continue

        # ── Hunter Domain Search ──────────────────────────────────────────
        hunter_contacts: list = []
        try:
            hunter_contacts = await _hunter_fetch_all_contacts(domain)
            logger.info(
                f"[Emails] Hunter: '{domain}' → {len(hunter_contacts)} contact(s) found"
            )
        except Exception as exc:
            logger.warning(f"[Emails] Hunter domain-search failed for '{domain}': {exc}")

        # ── Apollo fallback if Hunter returned nothing ─────────────────────
        if not hunter_contacts:
            dm_name = biz.get("decision_maker_name", "")
            if dm_name:
                try:
                    apollo_result = await _apollo_find_email(dm_name, domain)
                    if apollo_result.get("email"):
                        hunter_contacts = [apollo_result]
                        logger.info(
                            f"[Emails] Apollo fallback hit for '{dm_name}' @ '{domain}'"
                        )
                except Exception as exc:
                    logger.debug(f"[Emails] Apollo failed for '{domain}': {exc}")

        if not hunter_contacts:
            continue

        # ── Rank by relevance score ────────────────────────────────────────
        ranked = sorted(hunter_contacts, key=lambda c: c.get("relevance_score", 0), reverse=True)

        # Merge with existing contacts (from Stage 5) or create new list
        existing_contacts = {c.get("name", ""): c for c in biz.get("contacts", [])}

        for hc in ranked:
            name = hc.get("name", "")
            if name in existing_contacts:
                # Enrich existing contact with email data
                existing_contacts[name]["email"]            = hc["email"]
                existing_contacts[name]["email_confidence"] = hc["confidence"]
                existing_contacts[name]["verified"]         = hc["verified"]
                existing_contacts[name]["department"]       = hc.get("department", "")
                existing_contacts[name]["seniority"]        = hc.get("seniority", "")
                if not existing_contacts[name].get("linkedin_url"):
                    existing_contacts[name]["linkedin_url"] = hc.get("linkedin_url", "")
            else:
                # New contact discovered by Hunter
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

        # Promote the highest-relevance email + contact to the lead's primary fields
        best = max(biz["contacts"], key=lambda c: c.get("relevance_score", 0))
        if best.get("email"):
            biz["email"] = best["email"]
        if best.get("name") and not biz.get("decision_maker_name"):
            biz["decision_maker_name"]     = best["name"]
            biz["decision_maker_role"]     = best.get("role", "")
            biz["decision_maker_linkedin"] = best.get("linkedin_url", "")

        logger.info(
            f"[Emails] '{biz.get('business_name')}': "
            f"{len(biz['contacts'])} enriched contact(s), "
            f"best → {best.get('name')} ({best.get('role')}) [{best.get('verified')}]"
        )

    return businesses


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 7 – PERSONALIZED EMAIL GENERATION (Gemini)
# ══════════════════════════════════════════════════════════════════════════════

async def generate_personalized_emails(enriched_leads: list, session: AsyncSession) -> list:
    """
    Stage 7: Generate a personalized outreach email for every qualified lead
    using Gemini AI. Returns a list of dicts ready to be persisted as
    OutreachEmail records (each dict also carries the source `business` dict).

    Gemini generates a personalized 150–200 word outreach email (subject + body) 
    per lead, tailored to segment, sugar usage, and contact name.
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

        prompt = f"""
You are a B2B sales executive at Dhampur Green, India's premium quality sugar brand.
Write a personalized outreach email to the following HORECA business to introduce
Dhampur Green as a sugar supplier.

Business Details:
  Name          : {name}
  City          : {city}
  Segment       : {segment}
  Contact       : {contact_name or 'Procurement Team'}
  Role          : {contact_role}
  Dessert Menu  : {'Yes' if has_dessert else 'No'}
  Monthly Sugar : ~{sugar_kg} kg estimated
  Rating        : {rating}/5
  Hotel Category: {hotel_cat or 'N/A'}
  AI Insight    : {reasoning}

Guidelines:
  - 150-200 words, concise and professional.
  - Personalise based on segment / sugar usage.
  - Highlight Dhampur Green: quality, sulphur-free sugar, reliable supply.
  - Include a clear CTA (sample request or 15-min call).
  - Warm but professional tone; address contact by name if available.

Return ONLY a JSON object:
{{
  "subject" : "<email subject line>",
  "body"    : "<full email body with greeting, value prop, and CTA>"
}}
"""
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
    Stage 8: Persist leads, their contacts, and outreach emails to the database.
    `final_leads` is the list of email dicts produced by Stage 7, each carrying
    a `business` key with the fully enriched business dict.

    Persists Lead, Contact (per discovered contact), and OutreachEmail records 
    in a single transaction. Rolls back on failure.
    """
    stored = 0

    for item in final_leads:
        biz = item.get("business", {})
        try:
            now = datetime.now(timezone.utc)
            lead = Lead(
                id                      = str(uuid.uuid4()),
                business_name           = biz.get("business_name", ""),
                segment                 = biz.get("segment", "Restaurant"),
                city                    = biz.get("city", ""),
                state                   = biz.get("state", ""),
                tier                    = int(biz.get("tier", 2) or 2),
                address                 = biz.get("address", ""),
                phone                   = biz.get("phone", ""),
                email                   = biz.get("email", ""),
                website                 = biz.get("website", ""),
                rating                  = float(biz.get("rating", 0) or 0),
                num_outlets             = int(biz.get("num_outlets", 1) or 1),
                decision_maker_name     = biz.get("decision_maker_name", ""),
                decision_maker_role     = biz.get("decision_maker_role", ""),
                decision_maker_linkedin = biz.get("decision_maker_linkedin", ""),
                has_dessert_menu        = bool(biz.get("has_dessert_menu", False)),
                hotel_category          = biz.get("hotel_category", ""),
                is_chain                = bool(biz.get("is_chain", False)),
                ai_score                = int(biz.get("kpi_score", 0) or 0),
                ai_reasoning            = biz.get("ai_reasoning", ""),
                priority                = biz.get("priority", "Low"),
                status                  = "new",
                source                  = biz.get("source", "pipeline"),
                monthly_volume_estimate         = f"{biz.get('monthly_sugar_estimate_kg', '')} kg",
                highlights                      = biz.get("highlights", []),
                offerings                       = biz.get("offerings", []),
                dining_options                  = biz.get("dining_options", []),
                sugar_signal_from_highlights    = bool(biz.get("sugar_signal_from_highlights", False)),
                highlight_sugar_signals         = biz.get("highlight_sugar_signals", []),
                created_at                      = now,
                updated_at                      = now,
            )
            session.add(lead)
            await session.flush()  # resolve lead.id before FK references

            # Contacts
            for cd in biz.get("contacts", []):
                if not cd.get("name"):
                    continue
                session.add(Contact(
                    lead_id     = lead.id,
                    name        = cd.get("name", ""),
                    role        = cd.get("role", ""),
                    email       = cd.get("email", ""),
                    linkedin_url= cd.get("linkedin_url", ""),
                    created_at  = now,
                    updated_at  = now,
                ))

            # Outreach email
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
