"""
app/services/utils/email_patterns.py
─────────────────────────────────────────────────────────────────────────────
Pattern-based email generation fallback.

When Hunter/Apollo/Snov all fail, we generate educated guesses based on
the contact's name and the company domain. Common patterns used by Indian
businesses match the same conventions as global ones.

Used by Stage 6 (Email Enrichment) as the last-resort fallback before
giving up on finding an email address.
─────────────────────────────────────────────────────────────────────────────
"""
import re


def _clean(name_part: str) -> str:
    """Lowercase, strip spaces, remove non-alpha characters."""
    return re.sub(r"[^a-z]", "", name_part.lower().strip())


def generate_patterns(full_name: str, domain: str) -> list[str]:
    """
    Generate a list of probable email addresses for a person at a company.

    Patterns generated (in priority order):
        1. firstname@domain
        2. firstname.lastname@domain
        3. f.lastname@domain  (first initial + last name)
        4. flastname@domain   (first initial + last name, no dot)
        5. firstname_lastname@domain
        6. lastname@domain

    Args:
        full_name: Full name of the contact, e.g. "Rajesh Sharma".
        domain:    Company domain, e.g. "lafolie.in".

    Returns:
        Ordered list of email candidates. Returns [] if inputs are invalid.
    """
    if not full_name or not domain:
        return []

    parts = full_name.strip().split()
    if not parts:
        return []

    first = _clean(parts[0])
    last  = _clean(parts[-1]) if len(parts) > 1 else ""

    if not first:
        return []

    patterns: list[str] = []

    patterns.append(f"{first}@{domain}")

    if last and last != first:
        patterns.append(f"{first}.{last}@{domain}")
        patterns.append(f"{first[0]}.{last}@{domain}")
        patterns.append(f"{first[0]}{last}@{domain}")
        patterns.append(f"{first}_{last}@{domain}")
        patterns.append(f"{last}@{domain}")

    # deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return unique


def patterns_as_contacts(full_name: str, domain: str) -> list[dict]:
    """
    Return pattern-generated emails as normalised contact dicts
    (same shape as Hunter/Apollo/Snov outputs) for use in Stage 6.

    confidence is set to 0 — pattern emails must be verified before use.
    """
    return [
        {
            "name":            full_name,
            "email":           email,
            "role":            "",
            "department":      "",
            "seniority":       "",
            "linkedin_url":    "",
            "confidence":      0,
            "verified":        "unknown",
            "relevance_score": 10,
            "source":          "pattern_generated",
        }
        for email in generate_patterns(full_name, domain)
    ]
