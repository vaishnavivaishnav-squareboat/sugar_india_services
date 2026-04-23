"""
app/services/providers/apollo_provider.py
─────────────────────────────────────────────────────────────────────────────
Apollo.io People Match provider.

Used by Stage 6 (Email Enrichment) as a secondary fallback after Hunter.io
fails to return results for a given domain.
─────────────────────────────────────────────────────────────────────────────
"""
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import APOLLO_API_KEY, APOLLO_PEOPLE_MATCH_URL

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=6))
async def find_email(full_name: str, domain: str) -> dict:
    """
    Look up a person by name + domain using Apollo People Match.

    Args:
        full_name: Full name of the contact (e.g. "Rajesh Sharma").
        domain:    Company domain (e.g. "lafolie.in").

    Returns:
        Normalised contact dict with email, role, linkedin_url, etc.
        Returns {} if not found or API key is missing.
    """
    if not APOLLO_API_KEY or not domain:
        return {}

    headers = {
        "Content-Type": "application/json",
        "x-api-key":    APOLLO_API_KEY,
    }
    payload = {"name": full_name, "domain": domain}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(APOLLO_PEOPLE_MATCH_URL, json=payload, headers=headers)
            if resp.status_code == 200:
                person = resp.json().get("person", {})
                email  = person.get("email", "")
                if email:
                    logger.info(f"[Apollo] Hit for '{full_name}' @ '{domain}': {email}")
                return {
                    "name":            full_name,
                    "email":           email,
                    "role":            person.get("title", ""),
                    "department":      "",
                    "seniority":       "",
                    "linkedin_url":    person.get("linkedin_url", ""),
                    "confidence":      80 if email else 0,
                    "verified":        "unknown",
                    "relevance_score": 50,
                    "source":          "apollo",
                }
            else:
                logger.info(f"[Apollo] HTTP {resp.status_code} for '{full_name}' @ '{domain}'")
        except Exception as exc:
            logger.info(f"[Apollo] Request failed for '{full_name}' @ '{domain}': {exc}")
    return {}
