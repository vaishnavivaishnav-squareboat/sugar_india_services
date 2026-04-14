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

import app.services.openai_client  # noqa: registers AsyncOpenAI client
from app.db.session import AsyncSessionLocal
import app.pipelines.stages as ps
from app.agents.bridge import run_stage2, run_stage5, run_stage7
from app.helpers.constants import roles

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
]


# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _print_result(stage_name: str, data: list):
    print(f"\n{'═'*60}")
    print(f"  {stage_name}  →  {len(data)} record(s)")
    print(f"{'═'*60}")
    for item in data[:3]:     # print first 3 only
        simplified = {
            k: v for k, v in item.items()
            if k not in ("types", "menu_categories", "contacts", "business")
        }
        print(json.dumps(simplified, indent=2, default=str))
    if len(data) > 3:
        print(f"  ... and {len(data) - 3} more")


def _print_emails(emails: list):
    print(f"\n{'═'*60}")
    print(f"  Stage 7 – Generated Emails  →  {len(emails)} email(s)")
    print(f"{'═'*60}")
    for e in emails[:2]:
        print(f"\nTo   : {e.get('lead_name')} ({e.get('lead_city')})")
        print(f"Subj : {e.get('subject')}")
        print(f"Body :\n{e.get('body', '')[:400]}...")


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
            result = [{
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
            }]  # ensure it's a list, not None
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
            # output = await run_stage2(businesses)
            result = output.get("businesses", businesses)
        except Exception as exc:
            logger.warning(f"[Agents] Bridge failed, falling back to Gemini: {exc}")
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
        # Step 1: fetch SerpAPI snippets in Python (unchanged)
        print("  🔍 Fetching search snippets via SerpAPI ...")
        businesses_with_snippets = []
        for biz in businesses:
            name    = biz.get("business_name", "")
            city    = biz.get("city", "")
            segment = biz.get("segment", "Restaurant")
            snippets = []
            
            for role_query in roles:
                try:
                    query = f'"{name}" {city} {role_query} LinkedIn India'
                    hits  = await ps._serp_search(query)
                    snippets.extend(hits[:3])
                except Exception:
                    pass
            logger.info(f"  → Retrieved contacts after SerpAPI Google search: {snippets}")
            # Attach snippets so the bridge can pass them to the agent
            businesses_with_snippets.append({**biz, "_serp_snippets": snippets})
            logger.info(f"  → Attached snippets with business {businesses_with_snippets} snippets to '{name}' for agent processing.")

        # Step 2: Contact Discovery Agent extracts the decision-maker
        print("  🤖 Calling Contact Discovery Agent directly ...")
        try:
            output = await _call_agents_bridge(5, businesses_with_snippets)
            # output = await run_stage5(businesses_with_snippets, dry_run=False)
            result = output.get("businesses", businesses)
        except Exception as exc:
            logger.warning(f"[Agents] Bridge failed, falling back to Gemini: {exc}")
            async with AsyncSessionLocal() as session:
                result = await ps.enrich_contacts(businesses, session)
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
        # ── Agentic flow: Email Generator Agent (Stage 7) ────────────────────
        print("  🤖 Calling Email Generator Agent directly ...")
        try:
            output = await _call_agents_bridge(7, businesses)
            # output = await run_stage7(businesses, dry_run=False)

            result = output.get("emails", [])
        except Exception as exc:
            logger.warning(f"[Agents] Bridge failed, falling back to Gemini: {exc}")
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

    # Stage 1
    if stage in ("1", "all"):
        businesses = await run_stage_1(city, dry_run)
        if not businesses:
            print("\n⚠️  No businesses found. Check SERP_API_KEY or use --dry-run.")
            return
        if stage == "1":
            return

    # Stage 2
    if stage in ("2", "all"):
        if stage == "2":
            businesses = MOCK_BUSINESSES
        businesses = await run_stage_2(businesses, dry_run)
        if stage == "2":
            return

    # Stage 3
    if stage in ("3", "all"):
        if stage == "3":
            businesses = MOCK_BUSINESSES
        businesses = await run_stage_3(businesses)
        if stage == "3":
            return

    # Stage 4
    if stage in ("4", "all"):
        if stage == "4":
            businesses = MOCK_BUSINESSES
        businesses = await run_stage_4(businesses)
        if stage == "4":
            return

    # Stage 5
    if stage in ("5", "all"):
        if stage == "5":
            businesses = MOCK_BUSINESSES
        businesses = await run_stage_5(businesses, dry_run)
        if stage == "5":
            return

    # Stage 6
    if stage in ("6", "all"):
        if stage == "6":
            businesses = MOCK_BUSINESSES
            businesses = await run_stage_5(businesses, dry_run=True)
        businesses = await run_stage_6(businesses, dry_run)
        if stage == "6":
            return

    # Stage 7
    if stage in ("7", "all"):
        if stage == "7":
            businesses = MOCK_BUSINESSES
            businesses = await run_stage_5(businesses, dry_run=True)
            businesses = await run_stage_6(businesses, dry_run=True)
        email_items = await run_stage_7(businesses, dry_run)
        if stage == "7":
            return

    # Stage 8
    if stage in ("8", "all"):
        if stage == "8":
            # Bootstrap minimal email items for storage test
            businesses = MOCK_BUSINESSES
            businesses = await run_stage_2(businesses, dry_run=True)
            businesses = await run_stage_3(businesses)
            businesses = await run_stage_4(businesses)
            businesses = await run_stage_5(businesses, dry_run=True)
            businesses = await run_stage_6(businesses, dry_run=True)
            email_items = await run_stage_7(businesses, dry_run=True)
        await run_stage_8(email_items)

    print(f"\n{'━'*60}")
    print(f"  ✅  Pipeline run complete for '{city}'")
    print(f"{'━'*60}\n")


# ─── CLI ─────────────────────────────────────────────────────────────────────

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
    args = parser.parse_args()
    asyncio.run(run_pipeline(city=args.city, stage=args.stage, dry_run=args.dry_run))
