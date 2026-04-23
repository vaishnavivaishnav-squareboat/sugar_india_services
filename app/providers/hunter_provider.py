"""
app/services/providers/hunter_provider.py
─────────────────────────────────────────────────────────────────────────────
Hunter.io email enrichment provider.

Exposes two strategies:
  • domain_search  — fetch all contacts for a domain (paginated)
  • email_finder   — targeted lookup for a specific person by name + domain

Used by Stage 6 (Email Enrichment) as the primary email source.
─────────────────────────────────────────────────────────────────────────────
"""
import asyncio
import logging

from tenacity import retry, stop_after_attempt, wait_exponential
from pyhunter import AsyncPyHunter

from app.core.config import HUNTER_API_KEY
from app.core.constants import DECISION_MAKER_KEYWORDS as _DECISION_MAKER_KEYWORDS, DEPT_SCORE as _DEPT_SCORE, HUNTER_TARGET_DEPARTMENTS, HUNTER_TARGET_SENIORITY

logger = logging.getLogger(__name__)


def score_contact(person: dict) -> int:
    """Rank a Hunter contact by procurement relevance."""
    score    = 0
    dept     = (person.get("department") or "").lower()
    score   += _DEPT_SCORE.get(dept, 10)
    position = (person.get("position") or person.get("role") or "").lower()
    hits     = sum(1 for kw in _DECISION_MAKER_KEYWORDS if kw in position)
    score   += min(hits * 30, 60)
    verification = (person.get("verification") or {}).get("status", "")
    if verification == "valid":
        score += 20
    elif verification == "accept_all":
        score += 10
    score += int((person.get("confidence") or 0) / 5)
    return score


# ── domain search ─────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
async def domain_search(domain: str, max_pages: int = 3) -> list[dict]:
    """
    Fetch all contacts for a domain via Hunter Domain Search (paginated).

    Returns a list of normalized contact dicts with relevance_score attached.
    """
    if not HUNTER_API_KEY or not domain:
        return []

    all_contacts: list[dict] = []
    limit = 20

    async with AsyncPyHunter(
        HUNTER_API_KEY,
        max_retries=2,
        retry_backoff=0.5,
    ) as hunter:
        for page in range(max_pages):
            offset = page * limit
            try:
                data = await hunter.domain_search(
                    domain,
                    # limit=limit,
                    # offset=offset,
                )
                logger.info(f"[Hunter] domain_search page={page} response: {data}")
            except Exception as exc:
                logger.info(f"[Hunter] domain_search failed for '{domain}': {exc}")
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
                    "phone":           person.get("phone_number") or "",
                    "twitter":         person.get("twitter") or "",
                    "confidence":      int(person.get("confidence") or 0),
                    "verified":        (person.get("verification") or {}).get("status", ""),
                    "relevance_score": score_contact(person),
                    "source":          "hunter_domain_search",
                })

            if len(emails) < limit:
                break
            await asyncio.sleep(0.5)

    logger.info(f"[Hunter] domain_search '{domain}' → {len(all_contacts)} contact(s)")
    return all_contacts


# ── email finder ──────────────────────────────────────────────────────────────

async def email_finder_by_linkedin(linkedin_url: str, max_duration: int = 15) -> dict:
    """
    Find a person's business email using their LinkedIn profile URL.
    Does NOT require knowing the company domain — useful when Stage 5 found a
    LinkedIn URL but the business has no website.

    Uses: hunter.email_finder(linkedin_handle='kevinsystrom', max_duration=15)
    where the handle is extracted from the LinkedIn profile URL.

    Args:
        linkedin_url:  Full LinkedIn URL, e.g. https://linkedin.com/in/kevinsystrom
        max_duration:  Max seconds Hunter will spend searching (default 15).

    Returns:
        Normalised contact dict, or {} if not found.
    """
    if not HUNTER_API_KEY or not linkedin_url:
        return {}

    # Extract the handle from any LinkedIn URL format:
    #   https://linkedin.com/in/kevinsystrom
    #   https://www.linkedin.com/in/kevin-systrom-123/
    import re as _re
    match = _re.search(r"linkedin\.com/in/([\w\-]+)", linkedin_url)
    if not match:
        logger.info(f"[Hunter] email_finder_by_linkedin: could not parse handle from '{linkedin_url}'")
        return {}

    handle = match.group(1).rstrip("/")
    logger.info(f"[Hunter] email_finder_by_linkedin: handle='{handle}'")

    async with AsyncPyHunter(HUNTER_API_KEY) as hunter:
        try:
            raw_resp = await hunter.email_finder(
                linkedin_handle=handle,
                max_duration=max_duration,
                raw=True,
            )
            data: dict = raw_resp.json().get("data", {})
            email = data.get("email", "")
            if email:
                confidence    = int(data.get("score") or 0)
                first_name    = data.get("first_name") or ""
                last_name_    = data.get("last_name")  or ""
                resolved_name = f"{first_name} {last_name_}".strip()
                logger.info(f"[Hunter] email_finder_by_linkedin hit: {email} (confidence={confidence})")
                return {
                    "name":            resolved_name,
                    "email":           email,
                    "role":            data.get("position") or "",
                    "linkedin_url":    linkedin_url,
                    "phone":           data.get("phone_number") or "",
                    "company":         data.get("company") or "",
                    "confidence":      confidence,
                    "verified":        (data.get("verification") or {}).get("status", ""),
                    "relevance_score": score_contact({
                        "position":     data.get("position"),
                        "confidence":   data.get("score"),
                        "verification": data.get("verification"),
                    }),
                    "source":          "hunter_linkedin_finder",
                }
        except Exception as exc:
            logger.info(f"[Hunter] email_finder_by_linkedin failed for handle='{handle}': {exc}")
    return {}


async def email_finder(domain: str, full_name: str) -> dict:
    """
    Targeted email lookup for a known contact name via Hunter Email Finder.
    Used as a precision fallback when domain_search returns nothing.

    Returns a single normalised contact dict, or {} if not found.
    """
    if not HUNTER_API_KEY or not domain or not full_name:
        return {}

    parts = full_name.strip().split(" ", 1)
    first = parts[0]
    last  = parts[1] if len(parts) > 1 else ""

    async with AsyncPyHunter(HUNTER_API_KEY) as hunter:
        try:
            raw_resp = await hunter.email_finder(
                domain, first_name=first, last_name=last, raw=True
            )
            # raw=True returns the full HTTP response; parse the data payload
            data: dict = raw_resp.json().get("data", {})
            email = data.get("email", "")
            if email:
                confidence  = int(data.get("score") or 0)
                first_name  = data.get("first_name") or ""
                last_name_  = data.get("last_name")  or ""
                resolved_name = f"{first_name} {last_name_}".strip() or full_name
                logger.info(f"[Hunter] email_finder hit: {email} (confidence={confidence})")
                return {
                    "name":            resolved_name,
                    "email":           email,
                    "role":            data.get("position") or "",
                    "linkedin_url":    data.get("linkedin_url") or "",
                    "phone":           data.get("phone_number") or "",
                    "twitter":         data.get("twitter") or "",
                    "company":         data.get("company") or "",
                    "confidence":      confidence,
                    "verified":        (data.get("verification") or {}).get("status", ""),
                    "relevance_score": score_contact({
                        "position":     data.get("position"),
                        "confidence":   data.get("score"),
                        "verification": data.get("verification"),
                    }),
                    "source":          "hunter_email_finder",
                }
        except Exception as exc:
            logger.info(f"[Hunter] email_finder failed for '{full_name}' @ '{domain}': {exc}")
    return {}
