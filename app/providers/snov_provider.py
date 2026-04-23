"""
app/services/providers/snov_provider.py
─────────────────────────────────────────────────────────────────────────────
Snov.io email enrichment provider.

Used by Stage 6 (Email Enrichment) as a tertiary fallback after Hunter.io
and Apollo.io. Snov.io is strong for smaller Indian company domains that
Apollo/Hunter may not cover well.

Setup:
  Add to .env:
    SNOV_CLIENT_ID=your_client_id
    SNOV_CLIENT_SECRET=your_client_secret

Docs: https://snov.io/api
─────────────────────────────────────────────────────────────────────────────
"""
import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import SNOV_CLIENT_ID, SNOV_CLIENT_SECRET, SNOV_TOKEN_URL, SNOV_SEARCH_URL, SNOV_EMAIL_URL

logger = logging.getLogger(__name__)

_token_cache: dict = {}


async def _get_access_token() -> str:
    """Obtain (or reuse) a Snov.io OAuth access token."""
    if _token_cache.get("token"):
        return _token_cache["token"]

    if not SNOV_CLIENT_ID or not SNOV_CLIENT_SECRET:
        return ""

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(SNOV_TOKEN_URL, data={
            "grant_type":    "client_credentials",
            "client_id":     SNOV_CLIENT_ID,
            "client_secret": SNOV_CLIENT_SECRET,
        })
        data = resp.json()
        token = data.get("access_token", "")
        _token_cache["token"] = token
        return token


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=6))
async def domain_search(domain: str, limit: int = 10) -> list[dict]:
    """
    Find email contacts for a domain via Snov.io Prospects by Domain.

    Returns a list of normalised contact dicts, or [] on failure.
    """
    token = await _get_access_token()
    if not token:
        logger.info("[Snov] No access token — skipping domain search.")
        return []

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(SNOV_SEARCH_URL, json={
                "access_token": token,
                "domain":       domain,
                "type":         "personal",
                "limit":        limit,
            })
            data = resp.json()
            prospects = data.get("data", []) or []
            contacts = []
            for p in prospects:
                email = p.get("email", "")
                if not email:
                    continue
                contacts.append({
                    "name":            f"{p.get('firstName', '')} {p.get('lastName', '')}".strip() or "Unknown",
                    "email":           email,
                    "role":            p.get("position") or "",
                    "department":      "",
                    "seniority":       "",
                    "linkedin_url":    p.get("linkedIn") or "",
                    "confidence":      int(p.get("confidence") or 0),
                    "verified":        "unknown",
                    "relevance_score": 40,
                    "source":          "snov_domain_search",
                })
            logger.info(f"[Snov] domain_search '{domain}' → {len(contacts)} contact(s)")
            return contacts
        except Exception as exc:
            logger.info(f"[Snov] domain_search failed for '{domain}': {exc}")
            return []


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=6))
async def find_email(full_name: str, domain: str) -> dict:
    """
    Look up a specific person by name + domain via Snov.io Email From Names.

    Returns a normalised contact dict or {} if not found.
    """
    token = await _get_access_token()
    if not token or not full_name or not domain:
        return {}

    parts     = full_name.strip().split(" ", 1)
    first     = parts[0]
    last      = parts[1] if len(parts) > 1 else ""

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(SNOV_EMAIL_URL, json={
                "access_token": token,
                "domain":       domain,
                "firstName":    first,
                "lastName":     last,
            })
            data   = resp.json()
            emails = data.get("data", {}).get("emails", [])
            if emails:
                email = emails[0].get("email", "")
                if email:
                    logger.info(f"[Snov] find_email hit: {email}")
                    return {
                        "name":            full_name,
                        "email":           email,
                        "role":            "",
                        "department":      "",
                        "seniority":       "",
                        "linkedin_url":    "",
                        "confidence":      50,
                        "verified":        "unknown",
                        "relevance_score": 40,
                        "source":          "snov_email_finder",
                    }
        except Exception as exc:
            logger.info(f"[Snov] find_email failed for '{full_name}' @ '{domain}': {exc}")
    return {}
