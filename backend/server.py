from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, update as sql_update, delete as sql_delete
import os, logging, csv, io, json, uuid, random, httpx
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from emergentintegrations.llm.chat import LlmChat, UserMessage
from database import engine, get_db, Base
from models import Lead, OutreachEmail

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

app = FastAPI()
api_router = APIRouter(prefix="/api")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

METRO_CITIES = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad"]


# ─── STARTUP ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("PostgreSQL tables created/verified")


# ─── SCORING ENGINE ───────────────────────────────────────────────────────────

def calculate_lead_score(data: dict):
    score, reasons = 0, []
    hotel_cat = data.get('hotel_category', '')
    if hotel_cat == '5-star':   score += 30; reasons.append('5-star hotel (+30)')
    elif hotel_cat == '4-star': score += 20; reasons.append('4-star hotel (+20)')
    elif hotel_cat == '3-star': score += 10; reasons.append('3-star hotel (+10)')

    segment = data.get('segment', '')
    seg_pts = {'Bakery': 25, 'Mithai': 22, 'IceCream': 20, 'Cafe': 20,
               'CloudKitchen': 18, 'Catering': 18, 'Restaurant': 15, 'Hotel': 12}
    if segment in seg_pts:
        pts = seg_pts[segment]; score += pts; reasons.append(f'{segment} segment (+{pts})')

    if data.get('is_chain'): score += 15; reasons.append('Chain business (+15)')

    outlets = int(data.get('num_outlets', 1) or 1)
    if outlets >= 10:   score += 15; reasons.append(f'{outlets} outlets (+15)')
    elif outlets >= 3:  score += 10; reasons.append(f'{outlets} outlets (+10)')

    rating = float(data.get('rating', 0) or 0)
    if rating >= 4.5:   score += 10; reasons.append('Rating 4.5+ (+10)')
    elif rating >= 4.0: score += 7;  reasons.append('Rating 4.0+ (+7)')

    tier = int(data.get('tier', 3) or 3)
    if tier == 1:   score += 10; reasons.append('Metro city (+10)')
    elif tier == 2: score += 5;  reasons.append('Tier 2 city (+5)')

    if data.get('has_dessert_menu'): score += 15; reasons.append('Has dessert/sweet menu (+15)')
    if data.get('decision_maker_linkedin'): score += 10; reasons.append('Decision maker on LinkedIn (+10)')

    score = min(score, 100)
    priority = 'High' if score >= 70 else ('Medium' if score >= 40 else 'Low')
    reasoning = ' | '.join(reasons) if reasons else 'Insufficient data for scoring'
    return score, priority, reasoning


def make_lead_obj(data: dict, status: str = "new") -> Lead:
    score, priority, reasoning = calculate_lead_score(data)
    return Lead(
        id=str(uuid.uuid4()),
        business_name=data.get('business_name', ''),
        segment=data.get('segment', 'Restaurant'),
        city=data.get('city', ''),
        state=data.get('state', ''),
        tier=int(data.get('tier', 1) or 1),
        address=data.get('address', ''),
        phone=data.get('phone', ''),
        email=data.get('email', ''),
        website=data.get('website', ''),
        rating=float(data.get('rating', 0) or 0),
        num_outlets=int(data.get('num_outlets', 1) or 1),
        decision_maker_name=data.get('decision_maker_name', ''),
        decision_maker_role=data.get('decision_maker_role', ''),
        decision_maker_linkedin=data.get('decision_maker_linkedin', ''),
        has_dessert_menu=bool(data.get('has_dessert_menu', False)),
        hotel_category=data.get('hotel_category', ''),
        is_chain=bool(data.get('is_chain', False)),
        source=data.get('source', 'manual'),
        monthly_volume_estimate=data.get('monthly_volume_estimate', ''),
        ai_score=score,
        ai_reasoning=reasoning,
        priority=priority,
        status=status,
    )


# ─── PYDANTIC MODELS ─────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    business_name: str
    segment: str = "Restaurant"
    city: str
    state: str = ""
    tier: int = 1
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    rating: float = 0.0
    num_outlets: int = 1
    decision_maker_name: str = ""
    decision_maker_role: str = ""
    decision_maker_linkedin: str = ""
    has_dessert_menu: bool = False
    hotel_category: str = ""
    is_chain: bool = False
    source: str = "manual"
    monthly_volume_estimate: str = ""


class LeadStatusUpdate(BaseModel):
    status: str


class BulkCreateRequest(BaseModel):
    leads: List[dict]


class DiscoverRequest(BaseModel):
    city: str
    segment: str
    state: str = ""


# ─── GOOGLE MAPS INTEGRATION ──────────────────────────────────────────────────

HOTEL_LUXURY = ["taj ", "oberoi", "leela", "four seasons", "jw marriott", "grand hyatt",
                "ritz-carlton", "aman", "raffles", "st. regis", "the imperial", "trident"]
HOTEL_UPSCALE = ["marriott", "hilton", "sheraton", "radisson", "novotel", "crowne plaza",
                 "holiday inn", "hyatt regency", "courtyard", "westin", "renaissance", "le meridien"]

SEGMENT_QUERIES = {
    "Hotel": "hotels in {city}, India",
    "Restaurant": "premium restaurants in {city}, India",
    "Cafe": "cafes coffee shops in {city}, India",
    "Bakery": "bakeries patisserie cake shops in {city}, India",
    "CloudKitchen": "cloud kitchen food delivery in {city}, India",
    "Catering": "catering company services in {city}, India",
    "Mithai": "mithai sweet shops confectionery in {city}, India",
    "IceCream": "ice cream parlors gelato in {city}, India",
}


def detect_hotel_category(name: str) -> str:
    nl = name.lower()
    if any(b in nl for b in HOTEL_LUXURY): return "5-star"
    if any(b in nl for b in HOTEL_UPSCALE): return "4-star"
    return "3-star"


def gmaps_place_to_lead(place: dict, segment: str, city: str, state: str) -> dict:
    name = place.get("displayName", {}).get("text", "")
    address = place.get("formattedAddress", "")
    rating = float(place.get("rating", 0) or 0)
    phone = place.get("internationalPhoneNumber", "")
    website = place.get("websiteUri", "")
    rating_count = int(place.get("userRatingCount", 0) or 0)
    tier = 1 if city in METRO_CITIES else 2

    hotel_cat = detect_hotel_category(name) if segment == "Hotel" else ""
    is_chain = rating_count > 500  # Likely chain if many reviews

    lead = {
        "business_name": name,
        "segment": segment,
        "city": city, "state": state, "tier": tier,
        "address": address, "phone": phone, "email": "", "website": website,
        "rating": rating,
        "num_outlets": 5 if rating_count > 2000 else (3 if rating_count > 500 else 1),
        "decision_maker_name": "", "decision_maker_role": "", "decision_maker_linkedin": "",
        "has_dessert_menu": segment in ["Bakery", "Mithai", "IceCream", "Hotel", "Cafe"],
        "hotel_category": hotel_cat,
        "is_chain": is_chain,
        "source": "google_maps",
        "monthly_volume_estimate": ""
    }
    score, priority, reasoning = calculate_lead_score(lead)
    lead["ai_score"] = score; lead["ai_reasoning"] = reasoning; lead["priority"] = priority
    return lead


async def search_google_maps(text_query: str, api_key: str) -> list:
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.internationalPhoneNumber,places.websiteUri,places.types,places.userRatingCount,places.businessStatus"
    }
    body = {"textQuery": text_query, "pageSize": 10, "languageCode": "en"}
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code == 200:
                return resp.json().get("places", [])
            logger.error(f"Google Maps API {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"Google Maps request failed: {e}")
    return []


# ─── LEAD SIMULATION ENGINE ───────────────────────────────────────────────────

SEGMENT_TEMPLATES = {
    "Restaurant": [
        {"sfx": "Family Dhaba", "rating": 4.1, "outlets": 2, "has_dessert": True, "is_chain": False, "vol": "80-150 kg"},
        {"sfx": "Multi-Cuisine Restaurant", "rating": 4.3, "outlets": 5, "has_dessert": True, "is_chain": True, "vol": "200-350 kg"},
        {"sfx": "Fine Dine Kitchen", "rating": 4.5, "outlets": 1, "has_dessert": True, "is_chain": False, "vol": "100-200 kg"},
        {"sfx": "Buffet & Banquet Hall", "rating": 4.0, "outlets": 3, "has_dessert": True, "is_chain": False, "vol": "300-500 kg"},
        {"sfx": "North Indian Cuisine", "rating": 4.2, "outlets": 8, "has_dessert": True, "is_chain": True, "vol": "250-400 kg"},
        {"sfx": "Pan-Asian Bistro", "rating": 4.4, "outlets": 4, "has_dessert": True, "is_chain": True, "vol": "150-280 kg"},
        {"sfx": "Rooftop Restaurant", "rating": 4.6, "outlets": 2, "has_dessert": True, "is_chain": False, "vol": "120-220 kg"},
        {"sfx": "Thali House", "rating": 4.1, "outlets": 6, "has_dessert": True, "is_chain": True, "vol": "200-350 kg"},
        {"sfx": "Coastal Seafood House", "rating": 4.3, "outlets": 3, "has_dessert": True, "is_chain": False, "vol": "100-180 kg"},
        {"sfx": "Corporate Food Court", "rating": 3.9, "outlets": 12, "has_dessert": True, "is_chain": True, "vol": "400-700 kg"},
    ],
    "Cafe": [
        {"sfx": "Specialty Coffee House", "rating": 4.4, "outlets": 8, "has_dessert": True, "is_chain": True, "vol": "100-200 kg"},
        {"sfx": "Dessert & Brunch Cafe", "rating": 4.6, "outlets": 3, "has_dessert": True, "is_chain": False, "vol": "80-150 kg"},
        {"sfx": "Artisan Coffee Roasters", "rating": 4.5, "outlets": 12, "has_dessert": True, "is_chain": True, "vol": "150-280 kg"},
        {"sfx": "Book Cafe & Bistro", "rating": 4.3, "outlets": 2, "has_dessert": True, "is_chain": False, "vol": "40-80 kg"},
        {"sfx": "Co-working Cafe", "rating": 4.0, "outlets": 5, "has_dessert": True, "is_chain": True, "vol": "100-180 kg"},
        {"sfx": "Bubble Tea & Smoothie Bar", "rating": 4.2, "outlets": 20, "has_dessert": True, "is_chain": True, "vol": "200-350 kg"},
        {"sfx": "Waffle & Crepe Cafe", "rating": 4.5, "outlets": 6, "has_dessert": True, "is_chain": True, "vol": "120-200 kg"},
        {"sfx": "Cold Brew Coffee Studio", "rating": 4.4, "outlets": 4, "has_dessert": True, "is_chain": False, "vol": "60-100 kg"},
    ],
    "Bakery": [
        {"sfx": "Artisan Bakery & Patisserie", "rating": 4.5, "outlets": 4, "has_dessert": True, "is_chain": False, "vol": "200-400 kg"},
        {"sfx": "Cake & Confectionery Shop", "rating": 4.3, "outlets": 12, "has_dessert": True, "is_chain": True, "vol": "500-900 kg"},
        {"sfx": "French Bakery & Boulangerie", "rating": 4.7, "outlets": 3, "has_dessert": True, "is_chain": False, "vol": "250-450 kg"},
        {"sfx": "Wedding Cake Studio", "rating": 4.6, "outlets": 2, "has_dessert": True, "is_chain": False, "vol": "150-300 kg"},
        {"sfx": "Sourdough & Bread House", "rating": 4.4, "outlets": 8, "has_dessert": True, "is_chain": True, "vol": "300-550 kg"},
        {"sfx": "Mithai & Pastry Shop", "rating": 4.2, "outlets": 15, "has_dessert": True, "is_chain": True, "vol": "600-1000 kg"},
        {"sfx": "Cupcake & Macaron Boutique", "rating": 4.6, "outlets": 5, "has_dessert": True, "is_chain": False, "vol": "100-200 kg"},
        {"sfx": "Industrial Bread Factory", "rating": 4.0, "outlets": 1, "has_dessert": True, "is_chain": False, "vol": "1000-2000 kg"},
    ],
    "Hotel": [
        {"sfx": "Business Hotel", "rating": 4.2, "outlets": 1, "has_dessert": True, "is_chain": False, "hotel_cat": "3-star", "vol": "100-200 kg"},
        {"sfx": "Boutique Luxury Hotel", "rating": 4.4, "outlets": 2, "has_dessert": True, "is_chain": False, "hotel_cat": "4-star", "vol": "250-450 kg"},
        {"sfx": "Grand Heritage Hotel", "rating": 4.7, "outlets": 5, "has_dessert": True, "is_chain": True, "hotel_cat": "5-star", "vol": "600-1000 kg"},
        {"sfx": "Airport Transit Hotel", "rating": 3.9, "outlets": 1, "has_dessert": True, "is_chain": True, "hotel_cat": "3-star", "vol": "80-150 kg"},
        {"sfx": "Resort & Spa", "rating": 4.5, "outlets": 3, "has_dessert": True, "is_chain": False, "hotel_cat": "5-star", "vol": "400-700 kg"},
        {"sfx": "Extended Stay Hotel", "rating": 4.1, "outlets": 2, "has_dessert": True, "is_chain": True, "hotel_cat": "3-star", "vol": "150-280 kg"},
        {"sfx": "Convention & Wedding Hotel", "rating": 4.3, "outlets": 4, "has_dessert": True, "is_chain": False, "hotel_cat": "4-star", "vol": "500-900 kg"},
        {"sfx": "Taj Partner Hotel", "rating": 4.6, "outlets": 2, "has_dessert": True, "is_chain": True, "hotel_cat": "5-star", "vol": "550-950 kg"},
    ],
    "CloudKitchen": [
        {"sfx": "Cloud Eats Kitchen", "rating": 4.0, "outlets": 15, "has_dessert": False, "is_chain": True, "vol": "300-500 kg"},
        {"sfx": "Dark Kitchen Hub", "rating": 3.9, "outlets": 8, "has_dessert": True, "is_chain": True, "vol": "200-350 kg"},
        {"sfx": "Multi-Brand Food Factory", "rating": 4.1, "outlets": 25, "has_dessert": True, "is_chain": True, "vol": "500-900 kg"},
        {"sfx": "Healthy Meal Prep Kitchen", "rating": 4.3, "outlets": 6, "has_dessert": False, "is_chain": True, "vol": "100-200 kg"},
        {"sfx": "Dessert Delivery Kitchen", "rating": 4.2, "outlets": 10, "has_dessert": True, "is_chain": True, "vol": "250-450 kg"},
        {"sfx": "Virtual Biryani House", "rating": 4.0, "outlets": 20, "has_dessert": True, "is_chain": True, "vol": "400-700 kg"},
        {"sfx": "Tiffin & Meal Box Kitchen", "rating": 3.8, "outlets": 5, "has_dessert": True, "is_chain": False, "vol": "150-280 kg"},
    ],
    "Catering": [
        {"sfx": "Events & Catering Co", "rating": 4.2, "outlets": 1, "has_dessert": True, "is_chain": False, "vol": "200-400 kg"},
        {"sfx": "Corporate Caterers", "rating": 4.0, "outlets": 3, "has_dessert": True, "is_chain": True, "vol": "300-600 kg"},
        {"sfx": "Wedding & Social Caterers", "rating": 4.4, "outlets": 2, "has_dessert": True, "is_chain": False, "vol": "500-1000 kg"},
        {"sfx": "Industrial & Hospital Catering", "rating": 3.9, "outlets": 8, "has_dessert": True, "is_chain": True, "vol": "800-1500 kg"},
        {"sfx": "School & College Canteen Mgmt", "rating": 4.0, "outlets": 15, "has_dessert": True, "is_chain": True, "vol": "400-800 kg"},
        {"sfx": "Outdoor Event Specialists", "rating": 4.3, "outlets": 1, "has_dessert": True, "is_chain": False, "vol": "600-1200 kg"},
    ],
    "Mithai": [
        {"sfx": "Traditional Sweets & Namkeen", "rating": 4.3, "outlets": 6, "has_dessert": True, "is_chain": True, "vol": "600-1000 kg"},
        {"sfx": "Mithai Bhandar", "rating": 4.4, "outlets": 2, "has_dessert": True, "is_chain": False, "vol": "200-400 kg"},
        {"sfx": "Premium Sweets & Gift Shop", "rating": 4.5, "outlets": 10, "has_dessert": True, "is_chain": True, "vol": "800-1500 kg"},
        {"sfx": "Kaju Katli & Barfi House", "rating": 4.3, "outlets": 4, "has_dessert": True, "is_chain": False, "vol": "300-600 kg"},
        {"sfx": "Halwai & Sweet Maker", "rating": 4.1, "outlets": 1, "has_dessert": True, "is_chain": False, "vol": "150-300 kg"},
        {"sfx": "Festive Sweets Emporium", "rating": 4.4, "outlets": 8, "has_dessert": True, "is_chain": True, "vol": "500-900 kg"},
        {"sfx": "Sugar-Free & Diet Sweets", "rating": 4.2, "outlets": 3, "has_dessert": True, "is_chain": False, "vol": "100-200 kg"},
    ],
    "IceCream": [
        {"sfx": "Artisan Creamery & Scoops", "rating": 4.5, "outlets": 10, "has_dessert": True, "is_chain": True, "vol": "400-700 kg"},
        {"sfx": "Artisan Gelato & Sorbet", "rating": 4.6, "outlets": 3, "has_dessert": True, "is_chain": False, "vol": "150-300 kg"},
        {"sfx": "Kulfi & Falooda Parlour", "rating": 4.2, "outlets": 5, "has_dessert": True, "is_chain": True, "vol": "200-400 kg"},
        {"sfx": "Shake & Sundae Bar", "rating": 4.4, "outlets": 15, "has_dessert": True, "is_chain": True, "vol": "300-600 kg"},
        {"sfx": "Premium Frozen Dessert Shop", "rating": 4.5, "outlets": 8, "has_dessert": True, "is_chain": True, "vol": "350-650 kg"},
        {"sfx": "Natural Fruit Ice Cream", "rating": 4.3, "outlets": 20, "has_dessert": True, "is_chain": True, "vol": "500-900 kg"},
        {"sfx": "Waffle & Ice Cream Studio", "rating": 4.6, "outlets": 6, "has_dessert": True, "is_chain": False, "vol": "250-450 kg"},
    ],
}

DM_NAMES = [
    "Rajesh Kumar", "Priya Sharma", "Amit Singh", "Sunita Verma", "Vikram Nair",
    "Deepa Iyer", "Sanjay Mehta", "Rohit Gupta", "Anita Patel", "Manish Tiwari",
    "Kavita Reddy", "Suresh Menon", "Pooja Agarwal", "Arjun Pillai", "Neha Joshi"
]
DM_ROLES = [
    "Procurement Manager", "F&B Director", "Purchase Head", "Owner",
    "Operations Manager", "Supply Chain Head", "F&B Manager", "Founder & CEO", "Director - Procurement"
]
ROAD_NAMES = ["MG Road", "Main Street", "Park Road", "Station Road", "Brigade Road", "Link Road",
              "Commercial Street", "Anna Salai", "Nehru Place", "Connaught Place", "Bandra-Kurla Complex"]
PREFIXES = ["Golden", "Royal", "Classic", "Heritage", "Prime", "Urban", "The", "New",
            "Elite", "Grand", "Imperial", "Prestige", "Sterling", "Vivanta", "Spice"]


def generate_lead_simulation(city: str, segment: str, state: str) -> list:
    tier = 1 if city in METRO_CITIES else 2
    templates = SEGMENT_TEMPLATES.get(segment, SEGMENT_TEMPLATES["Restaurant"])
    # Shuffle and take up to 8 templates for variety
    shuffled = templates[:]
    random.shuffle(shuffled)
    selected = shuffled[:min(8, len(shuffled))]
    results = []
    used_names = set()
    for tmpl in selected:
        pfx = random.choice(PREFIXES)
        name = f"{pfx} {city} {tmpl['sfx']}"
        # Avoid duplicate names
        if name in used_names:
            pfx = random.choice([p for p in PREFIXES if p != pfx])
            name = f"{pfx} {city} {tmpl['sfx']}"
        used_names.add(name)
        dm_name = random.choice(DM_NAMES)
        lead = {
            "business_name": name, "segment": segment,
            "city": city, "state": state, "tier": tier,
            "address": f"{random.randint(10, 250)}, {random.choice(ROAD_NAMES)}, {city}",
            "phone": f"+91-{random.randint(7,9)}{random.randint(000000000, 999999999):09d}",
            "email": "",
            "website": "",
            "rating": round(tmpl["rating"] + random.uniform(-0.2, 0.2), 1),
            "num_outlets": tmpl["outlets"],
            "decision_maker_name": dm_name,
            "decision_maker_role": random.choice(DM_ROLES),
            "decision_maker_linkedin": "",
            "has_dessert_menu": tmpl.get("has_dessert", False),
            "hotel_category": tmpl.get("hotel_cat", ""),
            "is_chain": tmpl.get("is_chain", False),
            "source": "ai_generated",
            "monthly_volume_estimate": tmpl.get("vol", "")
        }
        score, priority, reasoning = calculate_lead_score(lead)
        lead["ai_score"] = score; lead["ai_reasoning"] = reasoning; lead["priority"] = priority
        results.append(lead)
    return results


# ─── API ROUTES ───────────────────────────────────────────────────────────────

@api_router.get("/")
async def root():
    return {"message": "Dhampur Green HORECA Lead Intelligence API v2.0 (PostgreSQL)"}


@api_router.get("/dashboard/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    total_leads = await db.scalar(select(func.count()).select_from(Lead))
    high_priority = await db.scalar(select(func.count()).select_from(Lead).where(Lead.priority == "High"))
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    new_this_week = await db.scalar(select(func.count()).select_from(Lead).where(Lead.created_at >= week_ago))
    converted = await db.scalar(select(func.count()).select_from(Lead).where(Lead.status == "converted"))
    conversion_rate = round((converted / total_leads * 100), 1) if total_leads else 0

    city_rows = (await db.execute(
        select(Lead.city, func.count(Lead.id).label("count"))
        .group_by(Lead.city).order_by(func.count(Lead.id).desc()).limit(8)
    )).all()
    seg_rows = (await db.execute(
        select(Lead.segment, func.count(Lead.id).label("count"))
        .group_by(Lead.segment).order_by(func.count(Lead.id).desc())
    )).all()
    status_rows = (await db.execute(
        select(Lead.status, func.count(Lead.id).label("count")).group_by(Lead.status)
    )).all()

    recent_leads = (await db.execute(
        select(Lead).order_by(Lead.created_at.desc()).limit(6)
    )).scalars().all()
    top_leads = (await db.execute(
        select(Lead).order_by(Lead.ai_score.desc()).limit(5)
    )).scalars().all()

    return {
        "total_leads": total_leads or 0,
        "high_priority": high_priority or 0,
        "new_this_week": new_this_week or 0,
        "converted": converted or 0,
        "conversion_rate": conversion_rate,
        "city_distribution": [{"city": r.city or "Unknown", "count": r.count} for r in city_rows],
        "segment_distribution": [{"segment": r.segment or "Unknown", "count": r.count} for r in seg_rows],
        "status_distribution": [{"status": r.status or "Unknown", "count": r.count} for r in status_rows],
        "recent_leads": [l.to_dict() for l in recent_leads],
        "top_leads": [l.to_dict() for l in top_leads],
    }


@api_router.get("/leads")
async def get_leads(
    city: Optional[str] = None, segment: Optional[str] = None,
    priority: Optional[str] = None, status: Optional[str] = None,
    min_score: Optional[int] = None, search: Optional[str] = None,
    limit: int = 100, skip: int = 0,
    db: AsyncSession = Depends(get_db)
):
    conditions = []
    if city:      conditions.append(Lead.city.ilike(f"%{city}%"))
    if segment:   conditions.append(Lead.segment == segment)
    if priority:  conditions.append(Lead.priority == priority)
    if status:    conditions.append(Lead.status == status)
    if min_score is not None: conditions.append(Lead.ai_score >= min_score)
    if search:
        conditions.append(or_(
            Lead.business_name.ilike(f"%{search}%"),
            Lead.city.ilike(f"%{search}%"),
            Lead.decision_maker_name.ilike(f"%{search}%")
        ))

    base_q = select(Lead)
    if conditions:
        base_q = base_q.where(and_(*conditions))

    leads = (await db.execute(base_q.order_by(Lead.ai_score.desc()).offset(skip).limit(limit))).scalars().all()
    total = await db.scalar(select(func.count()).select_from(Lead).where(and_(*conditions)) if conditions else select(func.count()).select_from(Lead))
    return {"leads": [l.to_dict() for l in leads], "total": total or 0}


@api_router.get("/leads/csv-template")
async def get_csv_template():
    headers = ["business_name", "segment", "city", "state", "tier", "address", "phone", "email",
               "website", "rating", "num_outlets", "decision_maker_name", "decision_maker_role",
               "decision_maker_linkedin", "has_dessert_menu", "hotel_category", "is_chain", "monthly_volume_estimate"]
    sample = ["The Grand Hotel", "Hotel", "Mumbai", "Maharashtra", "1", "Colaba, Mumbai",
              "9876543210", "procurement@grandhotel.com", "www.grandhotel.com", "4.5", "3",
              "Rajesh Kumar", "Procurement Manager", "linkedin.com/in/rajeshkumar", "true", "5-star", "false", "500kg"]
    content = ",".join(headers) + "\n" + ",".join(sample)
    return Response(content=content, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=horeca_leads_template.csv"})


@api_router.post("/leads/upload-csv")
async def upload_csv(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    try:
        text = content.decode('utf-8-sig')
    except Exception:
        text = content.decode('latin-1')

    reader = csv.DictReader(io.StringIO(text))
    created, errors = [], []
    for i, row in enumerate(reader):
        try:
            data = {
                "business_name": str(row.get('business_name', '')).strip(),
                "segment": str(row.get('segment', 'Restaurant')).strip() or 'Restaurant',
                "city": str(row.get('city', '')).strip(),
                "state": str(row.get('state', '')).strip(),
                "tier": int(str(row.get('tier', '1')).strip() or '1'),
                "address": str(row.get('address', '')).strip(),
                "phone": str(row.get('phone', '')).strip(),
                "email": str(row.get('email', '')).strip(),
                "website": str(row.get('website', '')).strip(),
                "rating": float(str(row.get('rating', '0')).strip() or '0'),
                "num_outlets": int(str(row.get('num_outlets', '1')).strip() or '1'),
                "decision_maker_name": str(row.get('decision_maker_name', '')).strip(),
                "decision_maker_role": str(row.get('decision_maker_role', '')).strip(),
                "decision_maker_linkedin": str(row.get('decision_maker_linkedin', '')).strip(),
                "has_dessert_menu": str(row.get('has_dessert_menu', 'false')).lower() in ('true', '1', 'yes'),
                "hotel_category": str(row.get('hotel_category', '')).strip(),
                "is_chain": str(row.get('is_chain', 'false')).lower() in ('true', '1', 'yes'),
                "source": "csv_upload",
                "monthly_volume_estimate": str(row.get('monthly_volume_estimate', '')).strip()
            }
            if not data['business_name'] or not data['city']:
                errors.append(f"Row {i+2}: Missing business_name or city"); continue
            lead_obj = make_lead_obj(data)
            db.add(lead_obj)
            created.append(lead_obj.to_dict())
        except Exception as e:
            errors.append(f"Row {i+2}: {str(e)}")

    await db.commit()
    return {"created": len(created), "errors": errors}


@api_router.post("/leads/discover")
async def discover_leads(req: DiscoverRequest):
    city = req.city.strip()
    segment = req.segment.strip()
    state = req.state.strip()
    results = []

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if api_key:
        query = SEGMENT_QUERIES.get(segment, f"{segment} in {city}, India").replace("{city}", city)
        places = await search_google_maps(query, api_key)
        for place in places:
            status = place.get("businessStatus", "")
            if status and status != "OPERATIONAL":
                continue
            lead = gmaps_place_to_lead(place, segment, city, state)
            if lead.get("business_name"):
                results.append(lead)

    # Always supplement with AI-generated simulation
    simulated = generate_lead_simulation(city, segment, state)
    results.extend(simulated)

    return results


@api_router.post("/leads/bulk-create")
async def bulk_create_leads(req: BulkCreateRequest, db: AsyncSession = Depends(get_db)):
    created = []
    for ld in req.leads:
        for k in ['ai_score', 'ai_reasoning', 'priority']:
            ld.pop(k, None)
        obj = make_lead_obj(ld)
        db.add(obj)
        created.append(obj.to_dict())
    await db.commit()
    return {"created": len(created), "leads": created}


@api_router.post("/leads")
async def create_lead(lead: LeadCreate, db: AsyncSession = Depends(get_db)):
    obj = make_lead_obj(lead.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj.to_dict()


@api_router.get("/leads/{lead_id}")
async def get_lead(lead_id: str, db: AsyncSession = Depends(get_db)):
    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead.to_dict()


@api_router.put("/leads/{lead_id}/status")
async def update_lead_status(lead_id: str, body: LeadStatusUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        sql_update(Lead).where(Lead.id == lead_id)
        .values(status=body.status, updated_at=datetime.now(timezone.utc))
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Lead not found")
    await db.commit()
    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
    return lead.to_dict()


@api_router.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(sql_delete(Lead).where(Lead.id == lead_id))
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Lead not found")
    await db.commit()
    return {"message": "Lead deleted"}


@api_router.post("/leads/{lead_id}/qualify-ai")
async def qualify_lead_ai(lead_id: str, db: AsyncSession = Depends(get_db)):
    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    api_key = os.environ.get('EMERGENT_LLM_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail="LLM API key not configured")

    try:
        chat = LlmChat(
            api_key=api_key, session_id=f"qualify-{lead_id}-{uuid.uuid4()}",
            system_message="You are a B2B sales qualification expert for Dhampur Green, India's premium sugar and sweetener brand."
        ).with_model("openai", "gpt-5.2")

        prompt = f"""Qualify this HORECA business for Dhampur Green (sugar/jaggery supplier):
Business: {lead.business_name}, Segment: {lead.segment}
Location: {lead.city}, {lead.state or 'India'} | Rating: {lead.rating}/5 | Outlets: {lead.num_outlets}
Hotel Category: {lead.hotel_category or 'N/A'} | Dessert Menu: {lead.has_dessert_menu} | Chain: {lead.is_chain}

Respond ONLY with valid JSON:
{{"ai_score":<0-100>,"monthly_volume_kg":"<range>","qualification_summary":"<2-3 sentences>","sugar_use_cases":["<uc1>","<uc2>","<uc3>"],"key_insight":"<sales insight>","priority":"<High/Medium/Low>","best_contact_time":"<recommendation>"}}"""

        response = await chat.send_message(UserMessage(text=prompt))
        json_str = response.strip()
        if '```json' in json_str: json_str = json_str.split('```json')[1].split('```')[0]
        elif '```' in json_str: json_str = json_str.split('```')[1].split('```')[0]
        ai_data = json.loads(json_str.strip())

        await db.execute(
            sql_update(Lead).where(Lead.id == lead_id).values(
                ai_score=int(ai_data.get('ai_score', lead.ai_score)),
                ai_reasoning=ai_data.get('qualification_summary', lead.ai_reasoning),
                priority=ai_data.get('priority', lead.priority),
                monthly_volume_estimate=ai_data.get('monthly_volume_kg', ''),
                updated_at=datetime.now(timezone.utc)
            )
        )
        await db.commit()
        updated = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one()
        return {"lead": updated.to_dict(), "ai_analysis": ai_data}
    except Exception as e:
        logger.error(f"AI qualify error: {e}")
        raise HTTPException(status_code=500, detail=f"AI qualification failed: {str(e)}")


@api_router.post("/leads/{lead_id}/generate-email")
async def generate_email(lead_id: str, db: AsyncSession = Depends(get_db)):
    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    api_key = os.environ.get('EMERGENT_LLM_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail="LLM API key not configured")

    try:
        chat = LlmChat(
            api_key=api_key, session_id=f"email-{lead_id}-{uuid.uuid4()}",
            system_message="You are an expert B2B sales copywriter for Dhampur Green, India's premium sugar and sweetener brand supplying HORECA businesses."
        ).with_model("openai", "gpt-5.2")

        dm = lead.decision_maker_name or 'Procurement Manager'
        first_name = dm.split()[0] if dm else 'Sir/Madam'

        prompt = f"""Write a personalized B2B outreach email for Dhampur Green targeting:
Business: {lead.business_name} ({lead.segment}, {lead.city})
Decision Maker: {dm} ({lead.decision_maker_role or 'F&B Head'})
Rating: {lead.rating}/5 | Outlets: {lead.num_outlets} | Dessert Menu: {lead.has_dessert_menu}
Monthly Volume Estimate: {lead.monthly_volume_estimate or 'Unknown'}

Dhampur Green Products: Premium refined sugar (M30/S30), sulphur-free jaggery, brown sugar, organic cane sugar, khandsari, icing sugar.

Write a 5-7 line professional email with specific subject, personalized opener, value prop, product rec, soft CTA, sign-off from "Arjun Mehta | Regional Sales Manager, Dhampur Green | +91-98765-43210"

Format EXACTLY:
SUBJECT: [subject]

Dear {first_name},
[body]"""

        response = await chat.send_message(UserMessage(text=prompt))
        lines = response.strip().split('\n')
        subject, body_lines, past_subject = "", [], False
        for line in lines:
            if line.startswith('SUBJECT:') and not past_subject:
                subject = line.replace('SUBJECT:', '').strip(); past_subject = True
            else:
                body_lines.append(line)
        body = '\n'.join(body_lines).strip()

        email_obj = OutreachEmail(
            id=str(uuid.uuid4()), lead_id=lead_id,
            lead_name=lead.business_name, lead_city=lead.city, lead_segment=lead.segment,
            subject=subject, body=body, status="draft"
        )
        db.add(email_obj)
        await db.commit()
        await db.refresh(email_obj)
        return email_obj.to_dict()
    except Exception as e:
        logger.error(f"Email gen error: {e}")
        raise HTTPException(status_code=500, detail=f"Email generation failed: {str(e)}")


@api_router.get("/outreach/emails")
async def get_all_emails(limit: int = 50, db: AsyncSession = Depends(get_db)):
    emails = (await db.execute(
        select(OutreachEmail).order_by(OutreachEmail.generated_at.desc()).limit(limit)
    )).scalars().all()
    return [e.to_dict() for e in emails]


@api_router.get("/outreach/{lead_id}/emails")
async def get_lead_emails(lead_id: str, db: AsyncSession = Depends(get_db)):
    emails = (await db.execute(
        select(OutreachEmail).where(OutreachEmail.lead_id == lead_id)
        .order_by(OutreachEmail.generated_at.desc()).limit(20)
    )).scalars().all()
    return [e.to_dict() for e in emails]


@api_router.put("/outreach/{email_id}/mark-sent")
async def mark_email_sent(email_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(
        sql_update(OutreachEmail).where(OutreachEmail.id == email_id)
        .values(status="sent", sent_at=datetime.now(timezone.utc))
    )
    await db.commit()
    email = (await db.execute(select(OutreachEmail).where(OutreachEmail.id == email_id))).scalar_one_or_none()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email.to_dict()


@api_router.post("/seed-mock-data")
async def seed_mock_data(db: AsyncSession = Depends(get_db)):
    count = await db.scalar(select(func.count()).select_from(Lead))
    if count and count > 0:
        return {"message": f"Already has {count} leads", "count": count}

    mock_leads = [
        {"business_name": "The Taj Mahal Palace", "segment": "Hotel", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Apollo Bunder, Colaba, Mumbai", "phone": "+91-22-6665-3366", "email": "fbprocurement@tajhotels.com", "website": "www.tajhotels.com", "rating": 4.8, "num_outlets": 12, "decision_maker_name": "Rakesh Nair", "decision_maker_role": "F&B Procurement Director", "decision_maker_linkedin": "linkedin.com/in/rakesh-nair-taj", "has_dessert_menu": True, "hotel_category": "5-star", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "800-1200 kg"},
        {"business_name": "Grand Hyatt Mumbai", "segment": "Hotel", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Santacruz East, Mumbai", "phone": "+91-22-6676-1234", "email": "procurement@grandhyattmumbai.com", "website": "www.grandhyatt.com", "rating": 4.6, "num_outlets": 2, "decision_maker_name": "Priya Sharma", "decision_maker_role": "Purchase Manager", "decision_maker_linkedin": "linkedin.com/in/priya-sharma-hyatt", "has_dessert_menu": True, "hotel_category": "5-star", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "600-800 kg"},
        {"business_name": "Monginis Cake Shop Chain", "segment": "Bakery", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Multiple locations, Mumbai", "phone": "+91-22-2376-5678", "email": "procurement@monginis.net", "website": "www.monginis.net", "rating": 4.2, "num_outlets": 230, "decision_maker_name": "Suhail Khorakiwala", "decision_maker_role": "Procurement Head", "decision_maker_linkedin": "linkedin.com/in/khorakiwala-monginis", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "5000-8000 kg"},
        {"business_name": "La Folie Patisserie", "segment": "Bakery", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Khar West, Mumbai", "phone": "+91-22-6503-4567", "email": "hello@lafolie.in", "website": "www.lafolie.in", "rating": 4.7, "num_outlets": 6, "decision_maker_name": "Sanjana Patel", "decision_maker_role": "Owner & Head Pastry Chef", "decision_maker_linkedin": "linkedin.com/in/sanjana-lafolie", "has_dessert_menu": True, "hotel_category": "", "is_chain": False, "source": "mock_data", "monthly_volume_estimate": "300-500 kg"},
        {"business_name": "Natural Ice Cream", "segment": "IceCream", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Juhu, Mumbai", "phone": "+91-22-2618-3456", "email": "supply@naturals.in", "website": "www.naturals.in", "rating": 4.5, "num_outlets": 135, "decision_maker_name": "Raghunandan Kamath", "decision_maker_role": "Owner", "decision_maker_linkedin": "linkedin.com/in/naturals-kamath", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "3000-5000 kg"},
        {"business_name": "Kailash Parbat Mithai", "segment": "Mithai", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Colaba, Mumbai", "phone": "+91-22-2202-9456", "email": "orders@kailashparbat.com", "website": "www.kailashparbat.in", "rating": 4.3, "num_outlets": 22, "decision_maker_name": "Vijay Gidwani", "decision_maker_role": "Purchase Manager", "decision_maker_linkedin": "linkedin.com/in/kailash-parbat", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "1500-2500 kg"},
        {"business_name": "Smoke House Deli Mumbai", "segment": "Restaurant", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Bandra West, Mumbai", "phone": "+91-22-6520-3456", "email": "procurement@smokehousedeli.com", "website": "www.smokehousedeli.com", "rating": 4.3, "num_outlets": 8, "decision_maker_name": "Manish Mehrotra", "decision_maker_role": "F&B Director", "decision_maker_linkedin": "linkedin.com/in/smokehouse-procurement", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "200-400 kg"},
        {"business_name": "BOX8 Cloud Kitchen", "segment": "CloudKitchen", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Andheri East, Mumbai", "phone": "+91-22-7123-8901", "email": "supply@box8.in", "website": "www.box8.in", "rating": 4.0, "num_outlets": 45, "decision_maker_name": "Anshul Gupta", "decision_maker_role": "Supply Chain Manager", "decision_maker_linkedin": "linkedin.com/in/box8-supply-chain", "has_dessert_menu": False, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "500-800 kg"},
        {"business_name": "The Leela Palace Delhi", "segment": "Hotel", "city": "Delhi", "state": "Delhi", "tier": 1, "address": "Diplomatic Enclave, Chanakyapuri", "phone": "+91-11-3933-1234", "email": "procurement@theleela.com", "website": "www.theleela.com", "rating": 4.8, "num_outlets": 8, "decision_maker_name": "Vikram Nair", "decision_maker_role": "F&B Procurement Head", "decision_maker_linkedin": "linkedin.com/in/vikram-nair-leela", "has_dessert_menu": True, "hotel_category": "5-star", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "700-1000 kg"},
        {"business_name": "The Baker's Dozen Delhi", "segment": "Bakery", "city": "Delhi", "state": "Delhi", "tier": 1, "address": "Khan Market, Delhi", "phone": "+91-11-4150-7890", "email": "procurement@bakersdozen.in", "website": "www.thebakersdozen.in", "rating": 4.5, "num_outlets": 28, "decision_maker_name": "Aditi Handa", "decision_maker_role": "CEO & Founder", "decision_maker_linkedin": "linkedin.com/in/aditi-handa-bakers", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "800-1200 kg"},
        {"business_name": "Haldiram's Delhi", "segment": "Mithai", "city": "Delhi", "state": "Delhi", "tier": 1, "address": "Lajpat Nagar, Delhi", "phone": "+91-11-2921-5678", "email": "supply@haldirams.com", "website": "www.haldirams.com", "rating": 4.4, "num_outlets": 150, "decision_maker_name": "Procurement Director", "decision_maker_role": "Procurement Director", "decision_maker_linkedin": "linkedin.com/in/haldirams-procurement", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "10000-20000 kg"},
        {"business_name": "Blue Tokai Coffee Roasters", "segment": "Cafe", "city": "Delhi", "state": "Delhi", "tier": 1, "address": "Saket, Delhi", "phone": "+91-11-4200-5678", "email": "wholesale@bluetokaicoffee.com", "website": "www.bluetokaicoffee.com", "rating": 4.5, "num_outlets": 30, "decision_maker_name": "Matt Chitharanjan", "decision_maker_role": "Founder", "decision_maker_linkedin": "linkedin.com/in/matt-bluetokai", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "200-400 kg"},
        {"business_name": "Punjab Grill Delhi", "segment": "Restaurant", "city": "Delhi", "state": "Delhi", "tier": 1, "address": "Select Citywalk, Saket, Delhi", "phone": "+91-11-4100-7890", "email": "procurement@punjabgrill.in", "website": "www.punjabgrill.in", "rating": 4.2, "num_outlets": 15, "decision_maker_name": "Sanjeev Nanda", "decision_maker_role": "Director Operations", "decision_maker_linkedin": "linkedin.com/in/punjab-grill-ops", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "400-700 kg"},
        {"business_name": "ITC Windsor Bengaluru", "segment": "Hotel", "city": "Bangalore", "state": "Karnataka", "tier": 1, "address": "Windsor Square, Golf Course Road, Bangalore", "phone": "+91-80-2226-9898", "email": "windsor.procurement@itchotels.in", "website": "www.itchotels.in", "rating": 4.7, "num_outlets": 4, "decision_maker_name": "Sanjay Menon", "decision_maker_role": "F&B Manager", "decision_maker_linkedin": "linkedin.com/in/sanjay-itcwindsor", "has_dessert_menu": True, "hotel_category": "5-star", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "500-800 kg"},
        {"business_name": "Third Wave Coffee", "segment": "Cafe", "city": "Bangalore", "state": "Karnataka", "tier": 1, "address": "Indiranagar, Bangalore", "phone": "+91-80-4123-5678", "email": "procurement@thirdwavecoffee.in", "website": "www.thirdwavecoffee.in", "rating": 4.4, "num_outlets": 65, "decision_maker_name": "Sushant Goel", "decision_maker_role": "Co-founder", "decision_maker_linkedin": "linkedin.com/in/sushant-thirdwave", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "400-700 kg"},
        {"business_name": "Barbeque Nation Bangalore", "segment": "Restaurant", "city": "Bangalore", "state": "Karnataka", "tier": 1, "address": "Residency Road, Bangalore", "phone": "+91-80-4000-1234", "email": "supply@barbequenation.com", "website": "www.barbequenation.com", "rating": 4.1, "num_outlets": 180, "decision_maker_name": "Kayum Dhanani", "decision_maker_role": "CEO", "decision_maker_linkedin": "linkedin.com/in/barbequenation-india", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "5000-8000 kg"},
        {"business_name": "MTR Foods Restaurant", "segment": "Restaurant", "city": "Bangalore", "state": "Karnataka", "tier": 1, "address": "Lalbagh Road, Bangalore", "phone": "+91-80-2222-0022", "email": "supply@mtrfoods.com", "website": "www.mtrfoods.com", "rating": 4.3, "num_outlets": 40, "decision_maker_name": "Sadananda Maiya", "decision_maker_role": "Procurement Head", "decision_maker_linkedin": "linkedin.com/in/mtr-procurement", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "800-1200 kg"},
        {"business_name": "Taj Falaknuma Palace", "segment": "Hotel", "city": "Hyderabad", "state": "Telangana", "tier": 1, "address": "Falaknuma, Hyderabad", "phone": "+91-40-6629-8585", "email": "falaknuma@tajhotels.com", "website": "www.tajhotels.com", "rating": 4.9, "num_outlets": 1, "decision_maker_name": "Zahir Hussain", "decision_maker_role": "Procurement Head", "decision_maker_linkedin": "linkedin.com/in/taj-falaknuma-procurement", "has_dessert_menu": True, "hotel_category": "5-star", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "400-600 kg"},
        {"business_name": "Paradise Restaurant Hyderabad", "segment": "Restaurant", "city": "Hyderabad", "state": "Telangana", "tier": 1, "address": "SD Road, Secunderabad", "phone": "+91-40-2784-7000", "email": "orders@paradiserestaurant.in", "website": "www.paradiserestaurant.in", "rating": 4.4, "num_outlets": 25, "decision_maker_name": "Mohammed Mateen", "decision_maker_role": "Purchase Manager", "decision_maker_linkedin": "", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "600-1000 kg"},
        {"business_name": "ITC Grand Chola Chennai", "segment": "Hotel", "city": "Chennai", "state": "Tamil Nadu", "tier": 1, "address": "63 Mount Road, Guindy, Chennai", "phone": "+91-44-2220-0000", "email": "grandchola.procurement@itchotels.in", "website": "www.itchotels.in", "rating": 4.8, "num_outlets": 3, "decision_maker_name": "Karthik Rajan", "decision_maker_role": "F&B Procurement Director", "decision_maker_linkedin": "linkedin.com/in/karthik-itcchola", "has_dessert_menu": True, "hotel_category": "5-star", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "600-900 kg"},
        {"business_name": "JW Marriott Pune", "segment": "Hotel", "city": "Pune", "state": "Maharashtra", "tier": 1, "address": "Senapati Bapat Road, Pune", "phone": "+91-20-6683-3333", "email": "procurement@marriottpune.com", "website": "www.marriott.com", "rating": 4.6, "num_outlets": 2, "decision_maker_name": "Rohan Desai", "decision_maker_role": "Purchase Manager", "decision_maker_linkedin": "linkedin.com/in/jwmarriott-pune", "has_dessert_menu": True, "hotel_category": "5-star", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "500-700 kg"},
        {"business_name": "Rebel Foods Pune", "segment": "CloudKitchen", "city": "Pune", "state": "Maharashtra", "tier": 1, "address": "Baner, Pune", "phone": "+91-20-6720-1234", "email": "supply@rebelfoods.com", "website": "www.rebelfoods.com", "rating": 3.9, "num_outlets": 120, "decision_maker_name": "Jaydeep Barman", "decision_maker_role": "Co-founder", "decision_maker_linkedin": "linkedin.com/in/jaydeep-rebelfoods", "has_dessert_menu": False, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "1000-2000 kg"},
        {"business_name": "ITC Royal Bengal Kolkata", "segment": "Hotel", "city": "Kolkata", "state": "West Bengal", "tier": 1, "address": "JBS Haldane Avenue, Kolkata", "phone": "+91-33-4455-8000", "email": "royalbengal.procurement@itchotels.in", "website": "www.itchotels.in", "rating": 4.7, "num_outlets": 2, "decision_maker_name": "Debashis Bose", "decision_maker_role": "Procurement Manager", "decision_maker_linkedin": "linkedin.com/in/itc-kolkata-procurement", "has_dessert_menu": True, "hotel_category": "5-star", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "500-800 kg"},
        {"business_name": "Radisson Blu Jaipur", "segment": "Hotel", "city": "Jaipur", "state": "Rajasthan", "tier": 2, "address": "Outer Ring Road, Jaipur", "phone": "+91-141-5100-100", "email": "procurement@radissonblu-jpr.com", "website": "www.radissonblu.com", "rating": 4.3, "num_outlets": 1, "decision_maker_name": "Suresh Sharma", "decision_maker_role": "F&B Manager", "decision_maker_linkedin": "", "has_dessert_menu": True, "hotel_category": "4-star", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "200-400 kg"},
        {"business_name": "LMB Mithai & Restaurant", "segment": "Mithai", "city": "Jaipur", "state": "Rajasthan", "tier": 2, "address": "Johari Bazaar, Jaipur", "phone": "+91-141-2565-844", "email": "orders@lmbhotel.com", "website": "www.lmbhotel.com", "rating": 4.2, "num_outlets": 5, "decision_maker_name": "Rahul Gupta", "decision_maker_role": "Owner", "decision_maker_linkedin": "", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "300-600 kg"},
        {"business_name": "Havmor Ice Cream", "segment": "IceCream", "city": "Ahmedabad", "state": "Gujarat", "tier": 2, "address": "CG Road, Ahmedabad", "phone": "+91-79-2640-1234", "email": "supply@havmor.com", "website": "www.havmor.com", "rating": 4.2, "num_outlets": 200, "decision_maker_name": "Ankit Chona", "decision_maker_role": "MD & CEO", "decision_maker_linkedin": "linkedin.com/in/ankit-chona-havmor", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "4000-7000 kg"},
        {"business_name": "Tunday Kababi Lucknow", "segment": "Restaurant", "city": "Lucknow", "state": "Uttar Pradesh", "tier": 2, "address": "Aminabad, Lucknow", "phone": "+91-522-2610-3456", "email": "procurement@tundaykababi.com", "website": "www.tundaykababi.com", "rating": 4.4, "num_outlets": 8, "decision_maker_name": "Mohammed Usman", "decision_maker_role": "Owner", "decision_maker_linkedin": "", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "150-300 kg"},
        {"business_name": "Royal Catering Lucknow", "segment": "Catering", "city": "Lucknow", "state": "Uttar Pradesh", "tier": 2, "address": "Gomti Nagar, Lucknow", "phone": "+91-522-4012-5678", "email": "info@royalcateringlko.com", "website": "www.royalcateringlko.com", "rating": 4.1, "num_outlets": 1, "decision_maker_name": "Avinash Tripathi", "decision_maker_role": "Owner", "decision_maker_linkedin": "", "has_dessert_menu": True, "hotel_category": "", "is_chain": False, "source": "mock_data", "monthly_volume_estimate": "200-500 kg"},
        {"business_name": "Ratnasagar Sweets Surat", "segment": "Mithai", "city": "Surat", "state": "Gujarat", "tier": 2, "address": "Ring Road, Surat", "phone": "+91-261-2567-890", "email": "procurement@ratnasagar.com", "website": "www.ratnasagarsweets.com", "rating": 4.3, "num_outlets": 12, "decision_maker_name": "Ashish Patel", "decision_maker_role": "Owner", "decision_maker_linkedin": "", "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "400-700 kg"},
        {"business_name": "Pal Dhaba Chandigarh", "segment": "Restaurant", "city": "Chandigarh", "state": "Punjab", "tier": 2, "address": "Sector 28, Chandigarh", "phone": "+91-172-2706-7890", "email": "orders@paldhaba.com", "website": "www.paldhaba.com", "rating": 4.4, "num_outlets": 3, "decision_maker_name": "Kulwant Singh", "decision_maker_role": "Owner", "decision_maker_linkedin": "", "has_dessert_menu": True, "hotel_category": "", "is_chain": False, "source": "mock_data", "monthly_volume_estimate": "150-250 kg"},
    ]

    statuses = ["new", "new", "new", "new", "contacted", "contacted", "qualified", "converted", "lost"]
    created = 0
    for i, data in enumerate(mock_leads):
        score, priority, reasoning = calculate_lead_score(data)
        days_ago = random.randint(0, 45)
        ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
        obj = Lead(
            id=str(uuid.uuid4()), **data,
            ai_score=score, ai_reasoning=reasoning, priority=priority,
            status=statuses[i % len(statuses)],
            created_at=ts, updated_at=ts
        )
        db.add(obj)
        created += 1

    await db.commit()
    return {"message": f"Seeded {created} HORECA leads into PostgreSQL", "count": created}


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
