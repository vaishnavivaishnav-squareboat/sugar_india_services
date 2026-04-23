"""
app/services/providers/serpapi_provider.py
─────────────────────────────────────────────────────────────────────────────
SerpAPI Google Web Search provider.

Wraps the SerpAPI organic search endpoint.
Used by Stage 5 (Contact Discovery) to find decision-maker signals for
HORECA businesses.
─────────────────────────────────────────────────────────────────────────────
"""
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import SERP_API_KEY, SERP_ENDPOINT

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def search_google(query: str, num_results: int = 5) -> list[dict]:
    """
    Run a Google web search via SerpAPI and return organic results.

    Args:
        query:       Search query string.
        num_results: Number of results to request (max 10).

    Returns:
        List of organic result dicts (title, link, snippet).
        Returns [] if SERP_API_KEY is not set or the request fails.
    """
    if not SERP_API_KEY:
        logger.info("[SerpAPI] SERP_API_KEY not set — skipping search.")
        return []

    params = {
        "engine":  "google",
        "q":       query,
        "num":     num_results,
        "api_key": SERP_API_KEY,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(SERP_ENDPOINT, params=params)
        logger.info(f"[SearchAPI] '{query}' → HTTP {resp.status_code}")
        resp.raise_for_status()
        return resp.json().get("organic_results", [])


async def search_contact_signals(
    business_name: str,
    city: str,
    roles: list[str],
) -> list[dict]:
    """
    Run multiple role-specific searches for a business and aggregate results.

    Args:
        business_name: Name of the HORECA business.
        city:          City the business is in.
        roles:         List of role titles to search for (e.g. "Procurement Manager").

    Returns:
        Flat list of organic result dicts from all queries.
    """
    # Build a single LinkedIn people-search query combining all roles with OR
    roles_clause = " OR ".join(f'"{r}"' for r in roles)
    query = (
        f'site:linkedin.com/in ({roles_clause}) '
        f'("{business_name}" OR "{city}") '
    )
    try:
        return await search_google(query)
    except Exception as exc:
        logger.info(f"[SerpAPI] Search failed for '{business_name}': {exc}")
        return []
