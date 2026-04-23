"""
app/services/extraction/extraction_service.py
─────────────────────────────────────────────────────────────────────────────
Stage 1 — Business Data Extraction.

Discovers HORECA businesses via two parallel sources per query:
  1. SerpAPI Google Maps  — rich place data (name, address, phone, rating,
                            reviews, GPS, highlights, offerings)
  2. Hunter Discover      — adds companies whose domains Hunter knows,
                            seeding Stage 6 email enrichment even when
                            SerpAPI has no record.

Paginates SerpAPI up to 3 pages per query (20 results each = up to 60).
Deduplicates by place_id / hunter domain key within the run.

This is the clean, modular replacement for the inline extract_business_data()
function and its private helpers in stages.py. stages.py delegates to this
service.
─────────────────────────────────────────────────────────────────────────────
"""
import re
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import httpx
from pyhunter import PyHunter

from app.core.config import SERP_API_KEY, SERP_ENDPOINT, HUNTER_API_KEY
from app.core.constants import HORECA_QUERY_MAP, _FULL_QUERY_MAP

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


# ── SearchAPI helpers ────────────────────────────────────────────────────────

async def _serp_maps_page(query: str, start: int = 0) -> list:
    """Fetch one page of Google Maps results from searchapi.io asynchronously."""
    params = {
        "engine":  "google_maps",
        "q":       query,
        "type":    "search",
        "start":   start,
        "hl":      "en",
        "gl":      "in",
        "api_key": SERP_API_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(SERP_ENDPOINT, params=params)
            resp.raise_for_status()
            return resp.json().get("local_results", [])
    except Exception as exc:
        logger.info(f"[Extract] SearchAPI failed for '{query}' (start={start}): {exc}")
        return []


def _parse_extensions(raw_extensions: list) -> dict:
    """
    Flatten the extensions array from a SerpAPI place result into
    highlights and from_the_business lists.
    """
    parsed = {"highlights": [], "from_the_business": []}
    for ext in (raw_extensions or []):
        for key in ("highlights", "from_the_business"):
            if key in ext:
                parsed[key].extend(ext[key])
    return parsed


def _normalize_serp_result(place: dict, segment: str, city: str) -> dict:
    """Map a raw SerpAPI place dict to the canonical pipeline business shape."""
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
        "offerings":         extensions["offerings"] if "offerings" in extensions else [],
        "from_the_business": extensions["from_the_business"],
        "segment":           segment,
        "city":              city,
        "state":             "",
        "tier":              1,
        "num_outlets":       1,
        "is_chain":          False,
        "source":            "serpapi_google_maps",
    }


# ── Hunter Discover helpers ───────────────────────────────────────────────────
# AsyncPyHunter does NOT expose .discover — only the sync PyHunter does.
# We run it in the shared ThreadPoolExecutor to stay non-blocking.

def _hunter_discover_sync(query: str, limit: int) -> list[dict]:
    """
    Blocking Hunter Discover call — always run via ThreadPoolExecutor.
    PyHunter.discover is a POST request and only available on the sync client.
    Returns the `data` list of company dicts (PyHunter strips the outer wrapper).
    """
    hunter = PyHunter(HUNTER_API_KEY)
    result = hunter.discover(query=query, limit=limit)
    # PyHunter returns response.json()["data"] directly — already the list.
    return result or []


async def _hunter_discover(query: str, limit: int = 50) -> list[dict]:
    """
    Async wrapper around the sync Hunter Discover call.
    Returns a list of raw company dicts; empty list on any error or missing key.
    """
    if not HUNTER_API_KEY:
        return []
    loop = asyncio.get_event_loop()
    try:
        companies = await loop.run_in_executor(
            _executor, _hunter_discover_sync, query, limit
        )
        logger.info(f"[Extract] Hunter Discover '{query}': {len(companies)} result(s)")
        return companies
    except Exception as exc:
        err = str(exc)
        # Hunter Discover requires a paid plan — downgrade to DEBUG so it
        # doesn't pollute logs when the key is set but the plan doesn't
        # include this endpoint.
        if "error response" in err.lower() or "payment" in err.lower() or "upgrade" in err.lower():
            logger.info(f"[Extract] Hunter Discover unavailable for '{query}' (plan limitation): {exc}")
        else:
            logger.info(f"[Extract] Hunter Discover failed for '{query}': {exc}")
        return []


def _hunter_company_to_biz(company: dict, segment: str, city: str) -> dict:
    """
    Normalise a Hunter Discover company record to the canonical pipeline
    business shape so both sources flow through identical downstream stages.
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



# ── START ────────────────────────────────────────────────────────
async def extract_businesses(
    city: str,
    segment_filter: str | None = None,
    max_pages: int = 1,
    hunter_limit: int = 10,
) -> list[dict]:
    """
    Discover HORECA businesses for a city via SerpAPI + Hunter Discover.

    Args:
        city:             Target city (e.g. "Mumbai").
        segment_filter:   Optionally restrict to a single HORECA segment key
                          from HORECA_QUERY_MAP / _FULL_QUERY_MAP. When None,
                          all active segments in HORECA_QUERY_MAP are queried.
        max_pages:        Number of SerpAPI Google Maps pages to fetch per query
                          (default 1 = 20 results, max 3 = 60 results).
                          Each page costs 1 SerpAPI credit.
        hunter_limit:     Maximum companies to fetch from Hunter Discover per
                          segment query (default 10). Costs 1 Hunter credit per call.

    Returns:
        Deduplicated list of normalised business dicts.
    """
    if not SERP_API_KEY:
        logger.info("[Extract] SERP_API_KEY not set – skipping extraction.")
        return []

    # ── Build the query map for this run ─────────────────────────────────────
    if segment_filter:
        curated = _FULL_QUERY_MAP.get(segment_filter)
        if curated:
            queries = curated
        else:
            label   = re.sub(r"([A-Z])", r" \1", segment_filter).strip()
            queries = [f"{segment_filter} in {{city}}", f"{label.lower()} {{city}}"]
        query_map = {segment_filter: queries}
    else:
        query_map = HORECA_QUERY_MAP

    seen_ids: set  = set()
    results:  list = []

    for segment, query_templates in query_map.items():
        # ── Hunter Discover: ONE call per segment, not per query template ────
        # Firing once per segment costs 1 Hunter credit regardless of how many
        # query templates the segment has (e.g. IceCream has 3 templates — the
        # old code fired 3 Hunter calls for the same segment, wasting 2 credits).
        hunter_query    = f"{segment} companies in {city} India"
        hunter_companies = await _hunter_discover(hunter_query, limit=hunter_limit)

        # Merge Hunter results once per segment ──────────────────────────────
        for company in hunter_companies:
            domain = company.get("domain") or ""
            pid    = f"hunter_{domain}"
            if not domain or pid in seen_ids:
                continue
            seen_ids.add(pid)
            biz = _hunter_company_to_biz(company, segment, city)
            results.append(biz)
            logger.info(f"[Extract] Hunter Discover added: {biz['business_name']} ({domain})")

        for query_template in query_templates:
            query = query_template.format(city=city)

            # ── SerpAPI pages (Hunter Discover already fired above) ───────────
            # max_pages controls SerpAPI credit spend (1 page = 1 credit = 20 results).
            serp_pages = await asyncio.gather(*[
                _serp_maps_page(query, start=page_num * 20)
                for page_num in range(max_pages)
            ])

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

    logger.info(f"[Extract] Total unique businesses for '{city}': {len(results)}")
    return results
