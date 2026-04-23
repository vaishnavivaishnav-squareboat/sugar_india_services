"""
app/services/enrichment/email_service.py
─────────────────────────────────────────────────────────────────────────────
Stage 6 — Email Enrichment Orchestrator.

Multi-source fallback pipeline (in priority order):
  1. Hunter.io  domain_search   — bulk email discovery for the domain
  2. Hunter.io  email_finder    — targeted lookup for the known DM name
  3. Apollo.io  people_match    — secondary fallback
  4. Snov.io    domain_search   — tertiary fallback for Indian SME domains
  5. Pattern generation          — last-resort educated guess

Each source returns normalised contact dicts scored by procurement relevance.
The top-ranked contact is attached to the lead as the primary email.

This is the clean, modular replacement for the inline enrich_emails()
function in stages.py. stages.py delegates to this service.
─────────────────────────────────────────────────────────────────────────────
"""
import logging

from app.providers import snov_provider
from app.utils.domain_utils import extract_domain
from app.utils.email_patterns import patterns_as_contacts
from app.providers import apollo_provider, hunter_provider
from app.core.constants import DECISION_MAKER_KEYWORDS, roles as TARGET_ROLES

logger = logging.getLogger(__name__)

# Pre-build a lowercase keyword set from both the roles list and DM keywords
# so position matching is a single O(1) check.
_ROLE_KEYWORDS: frozenset[str] = frozenset(
    kw.lower()
    for entry in TARGET_ROLES
    for kw in entry.lower().split()
) | frozenset(DECISION_MAKER_KEYWORDS)


def _position_is_relevant(contact: dict) -> bool:
    """
    Return True if the contact's role/position/department contains at least
    one keyword from the procurement-relevant keyword set defined in constants.
    """
    text = " ".join([
        (contact.get("role")       or ""),
        (contact.get("position")   or ""),
        (contact.get("department") or ""),
        (contact.get("seniority")  or ""),
    ]).lower()
    return any(kw in text for kw in _ROLE_KEYWORDS)


async def enrich_email(
    business_name: str,
    website: str,
    decision_maker_name: str = "",
) -> dict:
    """
    Find the best email contact for a single HORECA business.

    Fallback chain:
      Hunter domain_search → Hunter email_finder → Apollo → Snov domain_search
      → Snov email_finder → Pattern generation

    Args:
        business_name:       Name of the business (for logging).
        website:             Business website URL (used to extract domain).
        decision_maker_name: Known DM name (enables targeted finder calls).

    Returns:
        Best normalised contact dict, or {} if nothing was found.
    """
    domain = extract_domain(website)

    contacts: list[dict] = []

    # ── 1. Hunter domain search ───────────────────────────────────────────────
    if domain:
        try:
            contacts = await hunter_provider.domain_search(domain)
        except Exception as exc:
            logger.info(f"[EmailService] Hunter domain_search failed for '{domain}': {exc}")

    # ── 2. Hunter email finder (targeted) ─────────────────────────────────────
    if not contacts and decision_maker_name and domain:
        try:
            result = await hunter_provider.email_finder(domain, decision_maker_name)
            if result.get("email"):
                contacts = [result]
        except Exception as exc:
            logger.info(f"[EmailService] Hunter email_finder failed: {exc}")

    # ── 3. Apollo fallback ────────────────────────────────────────────────────
    if not contacts and decision_maker_name and domain:
        try:
            result = await apollo_provider.find_email(decision_maker_name, domain)
            if result.get("email"):
                contacts = [result]
        except Exception as exc:
            logger.info(f"[EmailService] Apollo failed: {exc}")

    # ── 4. Snov domain search ─────────────────────────────────────────────────
    if not contacts and domain:
        try:
            contacts = await snov_provider.domain_search(domain)
        except Exception as exc:
            logger.info(f"[EmailService] Snov domain_search failed: {exc}")

    # ── 5. Snov email finder (targeted) ──────────────────────────────────────
    if not contacts and decision_maker_name and domain:
        try:
            result = await snov_provider.find_email(decision_maker_name, domain)
            if result.get("email"):
                contacts = [result]
        except Exception as exc:
            logger.info(f"[EmailService] Snov email_finder failed: {exc}")

    # ── 6. Pattern generation (last resort) ───────────────────────────────────
    if not contacts and decision_maker_name and domain:
        contacts = patterns_as_contacts(decision_maker_name, domain)
        if contacts:
            logger.info(f"[EmailService] '{business_name}': using pattern-generated email(s)")

    if not contacts:
        logger.info(f"[EmailService] '{business_name}': no email found across all sources")
        return {}

    best = max(contacts, key=lambda c: c.get("relevance_score", 0))
    logger.info(
        f"[EmailService] '{business_name}': best → {best.get('email')} "
        f"(source={best.get('source')}, confidence={best.get('confidence')})"
    )
    return best


# ── START ────────────────────────────────────────────────────────
async def enrich_leads_emails(businesses: list[dict]) -> list[dict]:
    """
    Run email enrichment for a list of lead dicts (pipeline-compatible wrapper).

    Mutates each lead dict in-place, merging enriched contacts back
    (same shape as the existing enrich_emails() in stages.py).

    Returns the mutated list.
    """
    for biz in businesses:
        domain      = extract_domain(biz.get("website", ""))
        dm_name     = biz.get("decision_maker_name", "")
        dm_linkedin = biz.get("decision_maker_linkedin", "")

        # ── No domain + no LinkedIn → nothing we can do, skip entirely ────────
        if not domain and not dm_linkedin:
            logger.info(
                f"[EmailService] '{biz.get('business_name')}': no website or LinkedIn — skipping."
            )
            continue

        hunter_contacts: list[dict] = []

        # ── No domain but LinkedIn URL found by Stage 5 ───────────────────────
        # Hunter email_finder accepts a LinkedIn handle directly — no domain needed.
        # This covers businesses without a website where Stage 5 still found a
        # decision-maker's LinkedIn profile.
        if not domain and dm_linkedin:
            logger.info(
                f"[EmailService] '{biz.get('business_name')}': no website but has LinkedIn — "
                f"trying Hunter linkedin_handle finder."
            )
            try:
                r = await hunter_provider.email_finder_by_linkedin(dm_linkedin)
                if r.get("email"):
                    hunter_contacts = [r]
            except Exception as exc:
                logger.info(f"[EmailService] Hunter linkedin finder failed: {exc}")
            # After LinkedIn attempt, go straight to merge — no domain chain possible
            # (fall through to the unified merge block below)

        # ── Has domain: credit-saving shortcut when no DM name ────────────────
        # If Stage 5 found no decision-maker name, Hunter domain_search may
        # return generic contacts (e.g. IT, HR) that pass no relevance filter
        # anyway. Skip the full chain and fall straight to pattern generation,
        # saving up to 2 Hunter + 1 Apollo + 2 Snov credits per no-contact lead.
        elif domain and not dm_name:
            logger.info(
                f"[EmailService] '{biz.get('business_name')}': no DM name from Stage 5 — "
                f"skipping Hunter/Apollo/Snov, using pattern generation only."
            )
            hunter_contacts = patterns_as_contacts("", domain)
            biz["contacts"] = list(hunter_contacts)
            if hunter_contacts:
                primary = hunter_contacts[0]
                biz["email"]               = primary.get("email", "")
                biz["decision_maker_name"] = primary.get("name", "")
            continue

        # ── Has domain + DM name: run full fallback chain ─────────────────────
        elif domain and dm_name:
            # 1. Hunter domain search
            try:
                hunter_contacts = await hunter_provider.domain_search(domain)
            except Exception as exc:
                hunter_contacts = []
                logger.info(f"[EmailService] Hunter domain_search failed for '{domain}': {exc}")

            # 2. Hunter email finder by name+domain
            if not hunter_contacts:
                try:
                    r = await hunter_provider.email_finder(domain, dm_name)
                    if r.get("email"):
                        hunter_contacts = [r]
                except Exception:
                    pass

            # 2b. Hunter email finder by LinkedIn handle (if we also have a LinkedIn URL)
            if not hunter_contacts and dm_linkedin:
                try:
                    r = await hunter_provider.email_finder_by_linkedin(dm_linkedin)
                    if r.get("email"):
                        hunter_contacts = [r]
                        logger.info(
                            f"[EmailService] '{biz.get('business_name')}': "
                            f"Hunter linkedin_handle finder succeeded as fallback."
                        )
                except Exception:
                    pass

            # 3. Apollo fallback
            if not hunter_contacts:
                try:
                    r = await apollo_provider.find_email(dm_name, domain)
                    if r.get("email"):
                        hunter_contacts = [r]
                except Exception:
                    pass

            # 4. Snov domain search
            if not hunter_contacts:
                try:
                    hunter_contacts = await snov_provider.domain_search(domain)
                except Exception:
                    pass

            # 5. Snov email finder
            if not hunter_contacts:
                try:
                    r = await snov_provider.find_email(dm_name, domain)
                    if r.get("email"):
                        hunter_contacts = [r]
                except Exception:
                    pass

            # 6. Pattern generation (last resort, zero API cost)
            if not hunter_contacts:
                hunter_contacts = patterns_as_contacts(dm_name, domain)

        # Filter to contacts whose position is procurement-relevant before merging.
        # This prevents unrelated roles (e.g. IT Executive, QA Manager) from
        # being merged in unless their title matches the target roles in constants.py.
        relevant_contacts = [c for c in hunter_contacts if _position_is_relevant(c)]
        if not relevant_contacts and hunter_contacts:
            logger.info(
                f"[EmailService] '{biz.get('business_name')}': "
                f"{len(hunter_contacts)} hunter contact(s) found but none matched "
                f"procurement-relevant positions — skipping merge."
            )

        # Always start from the stage-5 contacts already on the biz dict;
        # merge only the relevant newly discovered contacts on top.
        ranked = sorted(relevant_contacts, key=lambda c: c.get("relevance_score", 0), reverse=True)

        # ── Build unified contacts dict keyed by name ──────────────────────────
        # Seed with stage-5 contacts (serp+openai), then overlay stage-6
        # relevant contacts on top. Same name → fields are merged, not replaced.
        unified: dict[str, dict] = {}

        for c in biz.get("contacts", []):
            name = c.get("name", "")
            if name:
                unified[name] = dict(c)  # copy so we don't mutate the stage-5 list in place

        for hc in ranked:
            name = hc.get("name", "")
            if not name:
                continue
            if name in unified:
                # Enrich existing stage-5 contact with email + provider metadata
                unified[name].update({
                    "email":            hc["email"],
                    "email_confidence": hc["confidence"],
                    "verified":         hc["verified"],
                    "department":       hc.get("department") or unified[name].get("department", ""),
                    "seniority":        hc.get("seniority")  or unified[name].get("seniority", ""),
                })
                if not unified[name].get("linkedin_url"):
                    unified[name]["linkedin_url"] = hc.get("linkedin_url", "")
                if not unified[name].get("phone"):
                    unified[name]["phone"] = hc.get("phone", "")
                if not unified[name].get("role"):
                    unified[name]["role"] = hc.get("role", "")
                # Upgrade relevance_score if hunter scored this person higher
                if hc.get("relevance_score", 0) > unified[name].get("relevance_score", 0):
                    unified[name]["relevance_score"] = hc["relevance_score"]
            else:
                # New contact discovered in stage 6 — add to unified list
                unified[name] = {
                    "name":             name,
                    "role":             hc.get("role", ""),
                    "email":            hc["email"],
                    "phone":            hc.get("phone", ""),
                    "linkedin_url":     hc.get("linkedin_url", ""),
                    "confidence_score": round(hc["confidence"] / 100, 2),
                    "email_confidence": hc["confidence"],
                    "verified":         hc["verified"],
                    "department":       hc.get("department", ""),
                    "seniority":        hc.get("seniority", ""),
                    "relevance_score":  hc.get("relevance_score", 0),
                    "source":           hc.get("source", "unknown"),
                    "is_primary":       False,
                }

        # ── LinkedIn-based email lookup for contacts without email ────────────
        # Any contact discovered by Stage 5 (or Stage 6) that has a linkedin_url
        # but no email yet gets a targeted Hunter linkedin_handle finder attempt.
        for name, c in unified.items():
            if c.get("linkedin_url") and not c.get("email"):
                try:
                    r = await hunter_provider.email_finder_by_linkedin(c["linkedin_url"])
                    if r.get("email"):
                        c["email"]            = r["email"]
                        c["email_confidence"] = r.get("confidence", 0)
                        c["verified"]         = r.get("verified", "")
                        c["source"]           = r.get("source", "hunter_linkedin")
                        logger.info(
                            f"[EmailService] '{biz.get('business_name')}': "
                            f"LinkedIn finder → {r['email']} for {name}"
                        )
                except Exception as exc:
                    logger.info(
                        f"[EmailService] Hunter linkedin finder failed for '{name}': {exc}"
                    )

        # Only keep contacts where an email was found; drop the rest entirely.
        all_contacts = sorted(
            (c for c in unified.values() if c.get("email")),
            key=lambda c: c.get("relevance_score", 0),
            reverse=True,
        )

        # Mark the top email-bearing contact as primary
        for c in all_contacts:
            c["is_primary"] = False
        primary = next((c for c in all_contacts if c.get("email")), None)
        if primary:
            primary["is_primary"] = True

        biz["contacts"] = list(all_contacts)

        if primary:
            biz["email"]                  = primary["email"]
            biz["decision_maker_name"]     = primary["name"]
            biz["decision_maker_role"]     = primary.get("role", "") or biz.get("decision_maker_role", "")
            biz["decision_maker_linkedin"] = primary.get("linkedin_url", "") or biz.get("decision_maker_linkedin", "")

        with_email    = sum(1 for c in all_contacts if c.get("email"))
        without_email = len(all_contacts) - with_email
        logger.info(
            f"[EmailService] '{biz.get('business_name')}': unified {len(all_contacts)} contact(s) "
            f"({with_email} with email, {without_email} from stage-5)."
        )

    return businesses
