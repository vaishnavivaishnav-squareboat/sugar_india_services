"""
test_pipeline.py
─────────────────────────────────────────────────────────────────────────────
Standalone test script for the HORECA ETL pipeline.

Run a single stage:
    1. python tests/test_pipeline.py --stage 1 --city Gurgaon (SerpApi call to find all the restaurants, cafes...in {city})
    Response:
    {
        "place_id": "ChIJL7-ALkoZDTkRhIFPFMUs1oE",
        "business_name": "Theobroma Bakery and Cake Shop - Baani Square, Gurugram",
        "address": "Shop No. G-6, Ground Floor, B Block A, Baani Square, Sector 50, Gurugram, Haryana 122018, India",
        "phone": "+91 81828 81881",
        "website": "https://order.theobroma.in",
        "description": "",
        "rating": 4.6,
        "reviews_count": 437,
        "lat": 28.4257079,
        "lng": 77.05772809999999,
        "types": ["bakery"],
        "highlights": ["Great coffee","Great dessert","Great tea selection","Sports"],
        "offerings": ["Coffee"],
        "from_the_business": [],
        "segment": "Bakery",
        "city": "Gurugram",
        "state": "Haryana",
        "tier": 1,
        "num_outlets": 1,
        "is_chain": False,
        "source": "serpapi_google_maps"
    }



    2. python tests/test_pipeline.py --stage 2 --city Gurgaon (Stage 2 — Dessert menu and sugar dependency estimation — AI processing {n} businesses)
    Response:
    {
        "place_id": "ChIJL7-ALkoZDTkRhIFPFMUs1oE",
        "business_name": "Theobroma Bakery and Cake Shop - Baani Square, Gurugram",
        "address": "Shop No. G-6, Ground Floor, B Block A, Baani Square, Sector 50, Gurugram, Haryana 122018, India",
        "phone": "+91 81828 81881",
        "website": "https://order.theobroma.in",
        "description": "",
        "rating": 4.6,
        "reviews_count": 437,
        "lat": 28.4257079,
        "lng": 77.05772809999999,
        "highlights": [
            "Great coffee",
            "Great dessert",
            "Great tea selection",
            "Sports"
        ],
        "offerings": [
            "Coffee"
        ],
        "from_the_business": [],
        "segment": "Bakery",
        "city": "Gurugram",
        "state": "Haryana",
        "tier": 1,
        "num_outlets": 1,
        "is_chain": false,
        "source": "serpapi_google_maps",
        "has_dessert_menu": true,
        "sugar_items_count": 15,
        "avg_price_range": "mid-range",
        "hotel_category": "",
        "monthly_sugar_estimate_kg": 300,
        "sweetness_dependency_pct": 80,
        "sugar_signal_from_highlights": true,
        "highlight_sugar_signals": [
            "Great dessert",
            "Great coffee"
        ],
        "ai_reasoning": "The name 'Theobroma Bakery and Cake Shop' and business type 'bakery' strongly indicate a focus on desserts and sugar-heavy items. Highlights such as 'Great dessert' confirm this, and 'Great coffee' suggests sweet beverages are offered. The independent outlet has a 4.6 rating with 437 reviews, indicating moderate popularity. As a bakery, the sugar usage is estimated at 300 kg per month with 80% sweetness dependency. The mid-range pricing is inferred from the high rating and location in Gurugram. The classification as a 'Bakery' aligns with the available information."
        }


    3. python tests/test_pipeline.py --stage 3 --city Gurgaon (Stage 3 — KPI filtering {n} businesses)
    Response:
    {
        "place_id": "ChIJL7-ALkoZDTkRhIFPFMUs1oE",
        "business_name": "Theobroma Bakery and Cake Shop - Baani Square, Gurugram",
        "address": "Shop No. G-6, Ground Floor, B Block A, Baani Square, Sector 50, Gurugram, Haryana 122018, India",
        "phone": "+91 81828 81881",
        "website": "https://order.theobroma.in",
        "description": "",
        "rating": 4.6,
        "reviews_count": 437,
        "lat": 28.4257079,
        "lng": 77.05772809999999,
        "highlights": [
            "Great coffee",
            "Great dessert",
            "Great tea selection",
            "Sports"
        ],
        "offerings": [
            "Coffee"
        ],
        "from_the_business": [],
        "segment": "Bakery",
        "city": "Gurugram",
        "state": "Haryana",
        "tier": 1,
        "num_outlets": 1,
        "is_chain": false,
        "source": "serpapi_google_maps",
        "has_dessert_menu": true,
        "sugar_items_count": 20,
        "avg_price_range": "mid-range",
        "hotel_category": "",
        "monthly_sugar_estimate_kg": 250,
        "sweetness_dependency_pct": 85,
        "sugar_signal_from_highlights": true,
        "highlight_sugar_signals": [
            "Great dessert",
            "Great coffee"
        ],
        "ai_reasoning": "Sugar ~250.0 kg/month | Sweetness dependency 85.0% | Has dessert menu | Highlight sugar signals: Great dessert, Great coffee | Segment Bakery (w=100) | 437 reviews",
        "kpi_score": 71.19,
        "priority": "High"
    }

    4. python tests/test_pipeline.py --stage 4 --city Gurgaon (Stage 4 — Deduplication of 1 businesses)
    Response: [INFO] [Dedup] 1/1 unique leads after dedup.

    5. python tests/test_pipeline.py --stage 5 --city Gurgaon (Stage 5 — Contact enrichment for 1 leads)
    Response:  








    3. python tests/test_pipeline.py --stage all --city Gurgaon

Run all stages end-to-end:
    python tests/test_pipeline.py --stage all --city Delhi

Dry-run (skip real API calls, use mock data):
    python tests/test_pipeline.py --stage all --city Gurgaon --dry-run
─────────────────────────────────────────────────────────────────────────────
"""

import asyncio
import argparse
import json
import sys
import logging
from pathlib import Path

# ── must come before ANY app.* import ────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parents[1]   # sugar_india_services/
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

import app.core.openai_client  # noqa: registers AsyncOpenAI client
from app.db.session import AsyncSessionLocal
import app.pipelines.stages as ps
from app.agents.bridge import run_stage2, run_stage5, run_stage7
from app.core.constants import roles
from app.providers.serpapi_provider import search_contact_signals
from app.services.enrichment.contact_service import enrich_leads_contacts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline_test")

async def _call_agents_bridge(stage: int, businesses: list) -> dict:
    """
    Dispatches to the correct Python agent runner for the given pipeline stage.

    Stage 2 → run_stage2  → Business Intelligence Agent  → {"businesses": [...]}
    Stage 5 → run_stage5  → Contact Discovery Agent      → {"businesses": [...]}
    Stage 7 → run_stage7  → Email Generator Agent        → {"emails": [...]}
    """
    logger.info(f"[Agents] Calling stage {stage} agent with {len(businesses)} business(es)")
    if stage == 2:
        return await run_stage2(businesses)
    if stage == 5:
        return await run_stage5(businesses)
    if stage == 7:
        return await run_stage7(businesses)
    raise ValueError(f"Unknown agent stage: {stage}")


# ─── MOCK DATA (used when --dry-run is set) ──────────────────────────────────
MOCK_BUSINESSES = [
    {
        "place_id": "ChIJl1Hw7h4ZDTkR2DrfIpwcH0M",
        "business_name": "CAKE ‘O’ CLOCKS - TEST",
        "address": "Shop no. 5, Plot-55, Mehrauli-Gurgaon Rd, Block C, Sukhrali, Sector 17, Gurugram, Haryana 122007, India",
        "phone": "7042852897",
        "website": "https://www.cakeoclocks.com",
        "description": "",
        "rating": 4.1,
        "reviews_count": 141,
        "lat": 28.4754789,
        "lng": 77.0616746,
        "types": [
            "Bakery",
            "Cake shop",
            "Cupcake shop",
            "Dessert shop",
            "Patisserie"
        ],
        "highlights": ["cakes","Great dessert","sweets & treats","cheesecakes"],
        "offerings": ["desserts"],
        "from_the_business": [],
        "segment": "Bakery",
        "city": "Gurugram",
        "state": "Haryana",
        "tier": 1,
        "num_outlets": 1,
        "is_chain": False,
        "source": "serpapi_google_maps"
    },
    {
        "place_id": "ChIJHyro7KYZDTkRBa7PICK2gow",
        "business_name": "De Cakery - TEST",
        "address": "Shop 201, De Cakery, South point mall, Golf Course Rd, DLF Phase 5, Sector 53, Gurugram, Haryana 122011, India",
        "phone": "8800339207",
        "website": "http://www.decakery.com",
        "description": "",
        "rating": 4.7,
        "reviews_count": 328,
        "lat": 28.4482162,
        "lng": 77.09899109999999,
        "types": [
            "Cake shop",
            "Cafe"
        ],
        "highlights": ["Great coffee","Great dessert","Great tea selection","Sports"],
        "offerings": ["Coffee"],
        "from_the_business": [],
        "segment": "Bakery",
        "city": "Gurugram",
        "state": "Haryana",
        "tier": 1,
        "num_outlets": 1,
        "is_chain": False,
        "source": "serpapi_google_maps"
    }
]


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _print_result(stage_name: str, data: list):
    print(f"\n{'═'*60}")
    print(f"  {stage_name}  →  {len(data)} record(s)")
    print(f"{'═'*60}")
    for item in data[:3]:     # print first 3 only
        simplified = {
            k: v for k, v in item.items()
            if k not in ("types", "menu_categories", "business")
        }
        # Print contacts as a sub-section for readability
        contacts = item.get("contacts", [])
        print(json.dumps(simplified, indent=2, default=str))
        if contacts:
            print(f"  contacts ({len(contacts)}):")
            for c in contacts:
                print(f"    [{'★' if c.get('is_primary') else ' '}] "
                      f"{c.get('name','?'):30s} | {c.get('role',''):40s} | "
                      f"email: {c.get('email') or '—':35s} | "
                      f"src: {c.get('source','?')}")
    if len(data) > 3:
        print(f"  ... and {len(data) - 3} more")


def _print_emails(emails: list):
    print(f"\n{'═'*60}")
    print(f"  Stage 7 – Generated Emails  →  {len(emails)} email(s)")
    print(f"{'═'*60}")
    for e in emails:
        print(f"\nTo   : {e.get('sent_to_name', e.get('lead_name'))} <{e.get('sent_to_email', '')}>")
        print(f"Subj : {e.get('subject')}")
        print(f"Body :\n{e.get('body', '')[:300]}...")
        print(f"{'─'*60}")


# ─── STAGE RUNNERS ───────────────────────────────────────────────────────────

async def run_stage_1(city: str, dry_run: bool) -> list:
    print(f"\n🔍  Stage 1 — Extract businesses for '{city}'")
    if dry_run:
        logger.info("[DryRun] Using mock business data.")
        result = [b for b in MOCK_BUSINESSES if b["city"].lower() == city.lower()]
        result = result or MOCK_BUSINESSES          # fallback: return all mock data
    else:
        async with AsyncSessionLocal() as session:
            # result = await ps.extract_business_data(city, session)
            result = MOCK_BUSINESSES
    _print_result("Stage 1: Extracted", result)
    return result


async def run_stage_2(businesses: list, dry_run: bool) -> list:
    print(f"\n🤖  Stage 2 — AI processing {len(businesses)} businesses")
    if dry_run:
        # Simulate AI output
        for b in businesses:
            b.update({
                "has_dessert_menu":          b["segment"] in ["Bakery", "Cafe"],
                "sugar_items_count":         10 if b["segment"] == "Bakery" else 4,
                "monthly_sugar_estimate_kg": 400 if b["segment"] == "Bakery" else 120,
                "sweetness_dependency_pct":  70 if b["segment"] == "Bakery" else 35,
                "avg_price_range":           "mid-range",
                "hotel_category":            "",
                "ai_reasoning":              "Mock AI: high dessert dependency detected.",
            })
        result = businesses
    else:
        # ── Agentic flow: Business Intelligence Agent (Stage 2) ──────────────
        print("  🤖 Calling Business Intelligence Agent directly ...")
        try:
            output = await _call_agents_bridge(2, businesses)
            result = output.get("businesses", businesses)
        except Exception as exc:
            logger.info(f"[Agents] Bridge failed, falling back to service layer: {exc}")
            async with AsyncSessionLocal() as session:
                result = await ps.ai_process_business_data(businesses, session)
    _print_result("Stage 2: AI Enriched", result)
    return result


async def run_stage_3(businesses: list) -> list:
    print(f"\n📊  Stage 3 — KPI filtering {len(businesses)} businesses")
    async with AsyncSessionLocal() as session:
        result = await ps.apply_kpi_filtering(businesses, session)
    _print_result("Stage 3: KPI Filtered", result)
    return result


async def run_stage_4(businesses: list) -> list:
    print(f"\n🔁  Stage 4 — Deduplication of {len(businesses)} businesses")
    async with AsyncSessionLocal() as session:
        result = await ps.deduplicate_leads(businesses, session)
    _print_result("Stage 4: Deduplicated", result)
    return result


async def run_stage_5(businesses: list, dry_run: bool) -> list:
    print(f"\n👤  Stage 5 — Contact enrichment for {len(businesses)} leads")
    if dry_run:
        for b in businesses:
            b["decision_maker_name"]     = "Priya Sharma"
            b["decision_maker_role"]     = "F&B Manager"
            b["decision_maker_linkedin"] = "https://linkedin.com/in/priyasharma"
            b["contacts"] = [{
                "name":             "Priya Sharma",
                "role":             "F&B Manager",
                "linkedin_url":     "https://linkedin.com/in/priyasharma",
                "email":            "",
                "confidence_score": 0.8,
                "source":           "mock",
            }]
        result = businesses
    else:
        # Step 1: fetch SERP snippets using the centralised search_contact_signals
        # (builds the same site:linkedin.com/in OR-roles query as contact_service)
        print("  🔍 Fetching LinkedIn snippets via search_contact_signals ...")
        businesses_with_snippets = []
        for biz in businesses:
            name = biz.get("business_name", "")
            city = biz.get("city", "")
            snippets = await search_contact_signals(
                business_name=name,
                city=city,
                roles=roles,
            )
            logger.info(f"  → {len(snippets)} snippet(s) retrieved for '{name}', here ---->{snippets}")
            businesses_with_snippets.append({**biz, "_serp_snippets": snippets})

        # Step 2: Contact Discovery Agent extracts the decision-maker
        print("  🤖 Calling Contact Discovery Agent ...")
        try:
            output = await _call_agents_bridge(5, businesses_with_snippets)
            result = output.get("businesses", businesses)
        except Exception as exc:
            logger.info(f"[Agents] Bridge failed, falling back to enrich_leads_contacts: {exc}")
            result = await enrich_leads_contacts(businesses)
    _print_result("Stage 5: Contacts Enriched", result)
    return result


async def run_stage_6(businesses: list, dry_run: bool) -> list:
    print(f"\n📧  Stage 6 — Email enrichment for {len(businesses)} leads")
    if dry_run:
        for b in businesses:
            for c in b.get("contacts", []):
                c["email"]            = f"priya@{b.get('website','example.com').replace('https://','')}"
                c["email_confidence"] = 90
                c["verified"]         = "valid"
                c["relevance_score"]  = 120
            if b.get("contacts"):
                b["email"] = b["contacts"][0]["email"]
        result = businesses
    else:
        async with AsyncSessionLocal() as session:
            result = await ps.enrich_emails(businesses, session)
    _print_result("Stage 6: Emails Enriched", result)
    return result


async def run_stage_7(businesses: list, dry_run: bool) -> list:
    print(f"\n✉️   Stage 7 — Generating personalized emails for {len(businesses)} leads")
    if dry_run:
        result = [{
            "lead_name":    b.get("business_name"),
            "lead_city":    b.get("city"),
            "lead_segment": b.get("segment"),
            "subject":      f"Premium Sugar Supply for {b.get('business_name')} — Dhampur Green",
            "body":         (
                f"Dear {b.get('decision_maker_name', 'Procurement Team')},\n\n"
                f"I'm reaching out from Dhampur Green, India's trusted sugar brand, "
                f"to explore a supply partnership with {b.get('business_name')}.\n\n"
                f"[Mock email body — AI generation skipped in dry-run mode]\n\n"
                f"Best regards,\nDhampur Green Sales Team"
            ),
            "status":   "draft",
            "business": b,
        } for b in businesses]
    else:
        # Use the service layer which generates one email per contact-with-email
        print("  📨 Generating personalised email for every contact with an email address ...")
        async with AsyncSessionLocal() as session:
            result = await ps.generate_personalized_emails(businesses, session)
    _print_emails(result)
    return result


async def run_stage_8(email_items: list) -> bool:
    print(f"\n💾  Stage 8 — Storing {len(email_items)} leads to DB")
    async with AsyncSessionLocal() as session:
        success = await ps.store_leads_and_emails(email_items, session)
    print(f"  → {'✅ Stored successfully' if success else '❌ Storage failed'}")
    return success


# ─── MAIN ORCHESTRATOR ───────────────────────────────────────────────────────

async def run_pipeline(city: str, stage: str, dry_run: bool):
    print(f"\n{'━'*60}")
    print(f"  HORECA Pipeline Test  |  City: {city}  |  Stage: {stage}")
    print(f"  Mode: {'🏜  Dry-run (mock data, no real API calls)' if dry_run else '🌐  Live (real API calls)'}")
    print(f"{'━'*60}")

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 – DATA EXTRACTION - Extraction of businesses from SERPAPI/SEARCHAPI based on city and segment keywords
# ══════════════════════════════════════════════════════════════════════════════

    if stage in ("1", "all"):
        businesses = await run_stage_1(city, dry_run)
        # businesses = MOCK_BUSINESSES
        if not businesses:
            print("\n⚠️  No businesses found. Check SERP_API_KEY or use --dry-run.")
            return
        if stage == "1":
            return


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2 – AI CLASSIFICATION - AI enrichment (Business Intelligence Agent - sugar estimates, etc)
# ══════════════════════════════════════════════════════════════════════════════

    if stage in ("2", "all"):
        if stage == "2":
            businesses = MOCK_BUSINESSES
            businesses = await run_stage_1(city, dry_run=False)
        businesses = await run_stage_2(businesses, dry_run)
        if stage == "2":
            return

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 3 – KPI FILTERING
# ══════════════════════════════════════════════════════════════════════════════
    if stage in ("3", "all"):
        if stage == "3":
            businesses = MOCK_BUSINESSES
            businesses = await run_stage_1(city, dry_run=False)
            businesses = await run_stage_2(businesses, dry_run=False)
        businesses = await run_stage_3(businesses)
        if stage == "3":
            return

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 4 – DEDUPLICATION
# ══════════════════════════════════════════════════════════════════════════════
    if stage in ("4", "all"):
        if stage == "4":
            businesses = MOCK_BUSINESSES
            businesses = await run_stage_1(city, dry_run=False)
            businesses = await run_stage_2(businesses, dry_run=False)
            businesses = await run_stage_3(businesses)
        businesses = await run_stage_4(businesses)
        if stage == "4":
            return

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 5 – CONTACT ENRICHMENT - including LinkedIn snippets retrieval
# ══════════════════════════════════════════════════════════════════════════════

    if stage in ("5", "all"):
        if stage == "5":
            businesses = MOCK_BUSINESSES
            businesses = await run_stage_1(city, dry_run=False)
            businesses = await run_stage_2(businesses, dry_run=False)
            businesses = await run_stage_3(businesses)
            businesses = await run_stage_4(businesses)
        businesses = await run_stage_5(businesses, dry_run)
        if stage == "5":
            return

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 6 – EMAIL FINDING/ENRICHMENT - finding email addresses for the discovered contacts + using business domain
# ══════════════════════════════════════════════════════════════════════════════
    if stage in ("6", "all"):
        if stage == "6":
            businesses = MOCK_BUSINESSES
            businesses = await run_stage_1(city, dry_run=False)
            businesses = await run_stage_2(businesses, dry_run=False)
            businesses = await run_stage_3(businesses)
            businesses = await run_stage_4(businesses)
            businesses = await run_stage_5(businesses, dry_run=False)
        businesses = await run_stage_6(businesses, dry_run)
        if stage == "6":
            return

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 7 – PERSONALIZED EMAIL GENERATION
# ══════════════════════════════════════════════════════════════════════════════
    if stage in ("7", "all"):
        if stage == "7":
            businesses = MOCK_BUSINESSES
            businesses = await run_stage_1(city, dry_run=False)
            businesses = await run_stage_2(businesses, dry_run=False)
            businesses = await run_stage_3(businesses)
            businesses = await run_stage_4(businesses)
            businesses = await run_stage_5(businesses, dry_run=False)
            businesses = await run_stage_6(businesses, dry_run=False)

        # Filter to only businesses that have at least one contact with an email
        businesses_with_email = [
            b for b in businesses
            if any(c.get("email") for c in b.get("contacts", []))
        ]
        skipped = len(businesses) - len(businesses_with_email)
        if skipped:
            print(f"\n⏭  {skipped} business(es) skipped — no email addresses found after Stage 6")
        if not businesses_with_email:
            print("⚠️  No businesses have contacts with emails — skipping Stage 7 & 8.")
            return
        businesses = businesses_with_email

        email_items = await run_stage_7(businesses, dry_run)
        if stage == "7":
            return

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 8 – STORAGE - Store leads and emails to DB
# ══════════════════════════════════════════════════════════════════════════════

    if stage in ("8", "all"):
        if stage == "8":
            # Bootstrap minimal email items for storage test
            businesses = MOCK_BUSINESSES
            businesses = await run_stage_1(city, dry_run=False)
            businesses = await run_stage_2(businesses, dry_run=False)
            businesses = await run_stage_3(businesses)
            businesses = await run_stage_4(businesses)
            businesses = await run_stage_5(businesses, dry_run=False)
            businesses = await run_stage_6(businesses, dry_run=False)
            email_items = await run_stage_7(businesses, dry_run=False)
        await run_stage_8(email_items)

    print(f"\n{'━'*60}")
    print(f"  ✅  Pipeline run complete for '{city}'")
    print(f"{'━'*60}\n")


# ─── PER-BUSINESS PIPELINE ────────────────────────────────────────────────────
# Runs Stage 1 once, then for each extracted business independently runs
# Stages 2 → 8 before moving on to the next business.
# ─────────────────────────────────────────────────────────────────────────────

async def run_pipeline_per_business(city: str, dry_run: bool):
    print(f"\n{'━'*60}")
    print(f"  HORECA Pipeline  |  Mode: per-business  |  City: {city}")
    print(f"  Mode: {'🏜  Dry-run (mock data)' if dry_run else '🌐  Live (real API calls)'}")
    print(f"{'━'*60}")

    # ── Stage 1: extract the full business list once ──────────────────────────
    businesses = await run_stage_1(city, dry_run)
    if not businesses:
        print("\n⚠️  No businesses found. Check SERP_API_KEY or use --dry-run.")
        return

    total = len(businesses)
    print(f"\n▶  Processing {total} business(es) one by one through Stages 2–8…\n")

    all_email_items: list = []

    for idx, business in enumerate(businesses, start=1):
        bname = business.get("business_name", f"business #{idx}")
        print(f"\n{'─'*60}")
        print(f"  [{idx}/{total}]  {bname}")
        print(f"{'─'*60}")

        batch = [business]   # single-item list for all stage runners

        # Stage 2 – AI classification
        try:
            batch = await run_stage_2(batch, dry_run)
        except Exception as exc:
            print(f"  ⚠  Stage 2 failed for '{bname}': {exc} — skipping")
            continue

        # Stage 3 – KPI filtering (may return empty list if filtered out)
        try:
            batch = await run_stage_3(batch)
        except Exception as exc:
            print(f"  ⚠  Stage 3 failed for '{bname}': {exc} — skipping")
            continue
        if not batch:
            print(f"  ⏭  '{bname}' filtered out by KPI check — skipping")
            continue

        # Stage 4 – Deduplication
        try:
            batch = await run_stage_4(batch)
        except Exception as exc:
            print(f"  ⚠  Stage 4 failed for '{bname}': {exc} — skipping")
            continue
        if not batch:
            print(f"  ⏭  '{bname}' already in DB (duplicate) — skipping")
            continue

        # Stage 5 – Contact enrichment
        try:
            batch = await run_stage_5(batch, dry_run)
        except Exception as exc:
            print(f"  ⚠  Stage 5 failed for '{bname}': {exc} — skipping")
            continue

        # Stage 6 – Email enrichment
        try:
            batch = await run_stage_6(batch, dry_run)
        except Exception as exc:
            print(f"  ⚠  Stage 6 failed for '{bname}': {exc} — skipping")
            continue

        # Guard: skip Stage 7 if no contacts have an email address
        contacts_with_email = [
            c for b in batch for c in b.get("contacts", []) if c.get("email")
        ]
        if not contacts_with_email:
            print(f"  ⏭  '{bname}' — no email addresses found after Stage 6, skipping email generation")
            continue

        # Stage 7 – Email generation
        try:
            email_items = await run_stage_7(batch, dry_run)
        except Exception as exc:
            print(f"  ⚠  Stage 7 failed for '{bname}': {exc} — skipping")
            continue

        # Stage 8 – Store to DB immediately
        try:
            await run_stage_8(email_items)
        except Exception as exc:
            print(f"  ⚠  Stage 8 failed for '{bname}': {exc}")
            continue

        all_email_items.extend(email_items)
        print(f"  ✅  '{bname}' done — {len(email_items)} email(s) stored")

    print(f"\n{'━'*60}")
    print(f"  ✅  Per-business pipeline complete for '{city}'")
    print(f"  📊  {len(all_email_items)} total email(s) generated across {total} business(es)")
    print(f"{'━'*60}\n")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test HORECA pipeline stages")
    parser.add_argument(
        "--stage",
        default="all",
        choices=["1", "2", "3", "4", "5", "6", "7", "8", "all"],
        help="Which stage to test (default: all)",
    )
    parser.add_argument(
        "--city",
        default="Gurgaon",
        help="City to run the pipeline for (default: Gurgaon)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip real API calls; use mock data instead",
    )
    parser.add_argument(
        "--mode",
        default="batch",
        choices=["batch", "per-business"],
        help=(
            "batch        (default) — run each stage across all businesses before the next stage.\n"
            "per-business — extract once (Stage 1), then run Stages 2-8 for each business individually before moving to the next."
        ),
    )
    args = parser.parse_args()

    if args.mode == "per-business":
        asyncio.run(run_pipeline_per_business(city=args.city, dry_run=args.dry_run))
    else:
        asyncio.run(run_pipeline(city=args.city, stage=args.stage, dry_run=args.dry_run))
