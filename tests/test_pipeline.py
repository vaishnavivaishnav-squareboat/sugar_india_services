"""
test_pipeline.py
─────────────────────────────────────────────────────────────────────────────
Standalone test script for the HORECA ETL pipeline.

Run a single stage:
    1. python tests/test_pipeline.py --stage 1 --city Gurgaon (SerpApi call to find all the restaurants, cafes...in {city})
    Response:
    {
        "place_id": "ChIJVVcsPJg9DTkRKOXisrZv2O4",
        "business_name": "Under The Neem",
        "address": "Karma Lakelands, Sector 80, Gurugram, Haryana 122012",
        "phone": "096252 91720",
        "website": "https://karmachalets.co.in/under-the-neem",
        "rating": 4.4,
        "reviews_count": 2897,
        "lat": 28.3616052,
        "lng": 76.958631,
        "segment": "Restaurant",
        "city": "Gurgaon",
        "state": "",
        "tier": 1,
        "num_outlets": 1,
        "is_chain": false,
        "source": "serpapi_google_maps"
        }



    2. python tests/test_pipeline.py --stage 2 --city Gurgaon (Tells us if the restaurant has a dessert menu, and estimates sugar dependency based on the KPIs)
    Response:
    {
        "place_id": "mock_003",
        "business_name": "Brewer's Cafe & Desserts",
        "address": "Golf Course Road, Gurgaon, Haryana",
        "phone": "+91-9988776655",
        "website": "https://brewerscafe.in",
        "rating": 4.6,
        "reviews_count": 480,
        "lat": 28.44,
        "lng": 77.1,
        "segment": "Cafe",
        "city": "Gurgaon",
        "state": "Haryana",
        "tier": 1,
        "num_outlets": 12,
        "is_chain": false,
        "source": "mock",
        "has_dessert_menu": true,
        "sugar_items_count": 15,
        "avg_price_range": "mid-range",
        "hotel_category": "",
        "monthly_sugar_estimate_kg": 25,
        "sweetness_dependency_pct": 60,
        "ai_reasoning": "Brewer's Cafe, based on its name and the presence of desserts, relies heavily on sugar for its menu items. With a 4.6 rating, it likely has decent footfall, justifying a moderate monthly sugar estimate."
        }
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

# ── ensure project root is on sys.path ───────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from database import AsyncSessionLocal
import pipeline_stages as ps

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline_test")


# ─── MOCK DATA (used when --dry-run is set) ──────────────────────────────────
MOCK_BUSINESSES = [
    {
        "place_id":      "mock_001",
        "business_name": "The Grand Bakery Gurgaon",
        "address":       "DLF Cyber City, Gurgaon, Haryana",
        "phone":         "+91-9876543210",
        "website":       "https://grandbakery.in",
        "rating":        4.5,
        "reviews_count": 320,
        "lat":           28.4595,
        "lng":           77.0266,
        "types":         ["bakery", "food"],
        "segment":       "Bakery",
        "city":          "Gurgaon",
        "state":         "Haryana",
        "tier":          1,
        "num_outlets":   6,
        "is_chain":      True,
        "source":        "mock",
    },
    {
        "place_id":      "mock_002",
        "business_name": "Spice Route Restaurant",
        "address":       "Sector 29, Gurgaon, Haryana",
        "phone":         "+91-9123456789",
        "website":       "https://spiceroute.com",
        "rating":        4.2,
        "reviews_count": 210,
        "lat":           28.4700,
        "lng":           77.0350,
        "types":         ["restaurant"],
        "segment":       "Restaurant",
        "city":          "Gurgaon",
        "state":         "Haryana",
        "tier":          1,
        "num_outlets":   3,
        "is_chain":      False,
        "source":        "mock",
    },
    {
        "place_id":      "mock_003",
        "business_name": "Brewer's Cafe & Desserts",
        "address":       "Golf Course Road, Gurgaon, Haryana",
        "phone":         "+91-9988776655",
        "website":       "https://brewerscafe.in",
        "rating":        4.6,
        "reviews_count": 480,
        "lat":           28.4400,
        "lng":           77.1000,
        "types":         ["cafe"],
        "segment":       "Cafe",
        "city":          "Gurgaon",
        "state":         "Haryana",
        "tier":          1,
        "num_outlets":   12,
        "is_chain":      True,
        "source":        "mock",
    },
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
            result = await ps.extract_business_data(city, session)
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
            # businesses = MOCK_BUSINESSES
            businesses = [{
                "place_id": "ChIJ____P9yEXjkRUYF5jt1WDIk",
                "business_name": "Baker's Den",
                "address": "7, Shivalik Plaza, IIM Rd, opposite AMA, Panjara Pol, Ambawadi, Ahmedabad, Gujarat 380015",
                "phone": "076994 54545",
                "website": "https://www.thebakersden.com/",
                "description": "",
                "rating": 4.7,
                "reviews_count": 302,
                "lat": 23.028003599999998,
                "lng": 72.5423191,
                "highlights": [],
                "from_the_business": [],
                "segment": "Bakery",
                "city": "Ahmedabad",
                "state": "",
                "tier": 1,
                "num_outlets": 1,
                "is_chain": False,
                "source": "serpapi_google_maps"
            }]
        # businesses = await run_stage_2(businesses, dry_run)
        businesses = await run_stage_2([{
                "place_id": "ChIJ____P9yEXjkRUYF5jt1WDIk",
                "business_name": "Baker's Den",
                "address": "7, Shivalik Plaza, IIM Rd, opposite AMA, Panjara Pol, Ambawadi, Ahmedabad, Gujarat 380015",
                "phone": "076994 54545",
                "website": "https://www.thebakersden.com/",
                "description": "",
                "rating": 4.7,
                "reviews_count": 302,
                "lat": 23.028003599999998,
                "lng": 72.5423191,
                "highlights": [],
                "from_the_business": [],
                "segment": "Bakery",
                "city": "Ahmedabad",
                "state": "",
                "tier": 1,
                "num_outlets": 1,
                "is_chain": False,
                "source": "serpapi_google_maps"
            }], dry_run)
        if stage == "2":
            return

    # Stage 3
    if stage in ("3", "all"):
        if stage == "3":
            # businesses = MOCK_BUSINESSES
            businesses = [{
                "place_id": "ChIJVVcsPJg9DTkRKOXisrZv2O4",
                "business_name": "Under The Neem",
                "address": "Karma Lakelands, Sector 80, Gurugram, Haryana 122012",
                "phone": "096252 91720",
                "website": "https://karmachalets.co.in/under-the-neem",
                "rating": 4.4,
                "reviews_count": 2897,
                "lat": 28.3616052,
                "lng": 76.958631,
                "segment": "Restaurant",
                "city": "Gurgaon",
                "state": "",
                "tier": 1,
                "num_outlets": 1,
                "is_chain": False,
                "source": "serpapi_google_maps"
                }]
            businesses = await run_stage_2(businesses, dry_run=True)
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
            # businesses = MOCK_BUSINESSES
            businesses = [{
                "place_id": "ChIJVVcsPJg9DTkRKOXisrZv2O4",
                "business_name": "Under The Neem",
                "address": "Karma Lakelands, Sector 80, Gurugram, Haryana 122012",
                "phone": "096252 91720",
                "website": "https://karmachalets.co.in/under-the-neem",
                "rating": 4.4,
                "reviews_count": 2897,
                "lat": 28.3616052,
                "lng": 76.958631,
                "segment": "Restaurant",
                "city": "Gurgaon",
                "state": "",
                "tier": 1,
                "num_outlets": 1,
                "is_chain": False,
                "source": "serpapi_google_maps"
                }]
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
