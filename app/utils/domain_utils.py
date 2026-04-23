"""
app/services/utils/domain_utils.py
─────────────────────────────────────────────────────────────────────────────
Website → clean domain extraction utility.

Used by Stage 6 (Email Enrichment) before calling Hunter/Apollo/Snov,
all of which require a bare domain like "lafolie.in" not "https://www.lafolie.in/menu".
─────────────────────────────────────────────────────────────────────────────
"""
import re


def extract_domain(url: str) -> str:
    """
    Extract a bare registrable domain from any URL or domain-like string.

    Examples:
        "https://www.lafolie.in/menu"  →  "lafolie.in"
        "www.hotelleela.com"           →  "hotelleela.com"
        "monginis.net"                 →  "monginis.net"
        ""                            →  ""

    Args:
        url: Raw website string (may include scheme, www, path, query).

    Returns:
        Bare domain string, e.g. "lafolie.in". Returns "" if nothing valid found.
    """
    if not url:
        return ""

    website = url.lower().strip()
    # strip scheme
    website = re.sub(r"^https?://", "", website)
    # strip www.
    website = re.sub(r"^www\.", "", website)
    # keep only host part (drop path, query, fragment)
    domain  = website.split("/")[0].split("?")[0].split("#")[0]
    # basic sanity: must contain at least one dot
    if "." not in domain:
        return ""
    # Strip non-www subdomains (e.g. order.theobroma.in → theobroma.in,
    # app.hotel.com → hotel.com). Keep two-part domains and known ccTLDs
    # like .co.in, .net.in untouched.
    parts = domain.split(".")
    # e.g. ["order", "theobroma", "in"] → strip leading part if >2 parts
    # but preserve co.in / net.in / org.in style ccTLD pairs
    KNOWN_SECOND_LEVEL = {"co", "net", "org", "gov", "ac", "edu"}
    if len(parts) > 2:
        # last two parts form the TLD+SLD, e.g. "theobroma.in"
        # unless second-to-last is a known second-level label, e.g. "co.in"
        if parts[-2] in KNOWN_SECOND_LEVEL and len(parts) > 3:
            # e.g. ["order", "theobroma", "co", "in"] → "theobroma.co.in"
            domain = ".".join(parts[-3:])
        else:
            # e.g. ["order", "theobroma", "in"] → "theobroma.in"
            domain = ".".join(parts[-2:])
    return domain
