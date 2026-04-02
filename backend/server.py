from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, or_, and_, update as sql_update, delete as sql_delete
import os, logging, csv, io, json, uuid, random, httpx
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy import String, Float, Integer, Boolean, Text, select, func, desc, or_
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from emergentintegrations.llm.chat import LlmChat, UserMessage
from database import engine, get_db, Base
from models import Lead, OutreachEmail

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

METRO_CITIES = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad"]

# ─── ORM MODELS ──────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class LeadModel(Base):
    __tablename__ = "leads"

    id = mapped_column(String, primary_key=True)
    business_name = mapped_column(String, nullable=False, default="")
    segment = mapped_column(String, default="Restaurant")
    city = mapped_column(String, nullable=False, default="")
    state = mapped_column(String, default="")
    tier = mapped_column(Integer, default=1)
    address = mapped_column(String, default="")
    phone = mapped_column(String, default="")
    email = mapped_column(String, default="")
    website = mapped_column(String, default="")
    rating = mapped_column(Float, default=0.0)
    num_outlets = mapped_column(Integer, default=1)
    decision_maker_name = mapped_column(String, default="")
    decision_maker_role = mapped_column(String, default="")
    decision_maker_linkedin = mapped_column(String, default="")
    has_dessert_menu = mapped_column(Boolean, default=False)
    hotel_category = mapped_column(String, default="")
    is_chain = mapped_column(Boolean, default=False)
    source = mapped_column(String, default="manual")
    monthly_volume_estimate = mapped_column(String, default="")
    ai_score = mapped_column(Integer, default=0)
    ai_reasoning = mapped_column(Text, default="")
    priority = mapped_column(String, default="Low")
    status = mapped_column(String, default="new")
    created_at = mapped_column(String, default="")
    updated_at = mapped_column(String, default="")


class OutreachEmailModel(Base):
    __tablename__ = "outreach_emails"

    id = mapped_column(String, primary_key=True)
    lead_id = mapped_column(String, nullable=False, default="")
    lead_name = mapped_column(String, default="")
    lead_city = mapped_column(String, default="")
    lead_segment = mapped_column(String, default="")
    subject = mapped_column(String, default="")
    body = mapped_column(Text, default="")
    status = mapped_column(String, default="draft")
    generated_at = mapped_column(String, default="")
    sent_at = mapped_column(String, nullable=True)


def model_to_dict(obj) -> dict:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


# ─── LIFESPAN ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


# ─── APP ─────────────────────────────────────────────────────────────────────

app = FastAPI(lifespan=lifespan)
api_router = APIRouter(prefix="/api")


# ─── SCORING ENGINE ──────────────────────────────────────────────────────────

def calculate_lead_score(data: dict):
    score, reasons = 0, []
    hotel_cat = data.get('hotel_category', '')
    if hotel_cat == '5-star':   score += 30; reasons.append('5-star hotel (+30)')
    elif hotel_cat == '4-star': score += 20; reasons.append('4-star hotel (+20)')
    elif hotel_cat == '3-star': score += 10; reasons.append('3-star hotel (+10)')

    segment = data.get('segment', '')
    seg_pts = {
        # 'Bakery': 25, 'Mithai': 22, 'IceCream': 20, 'CloudKitchen': 18, 'Catering': 18,
                 'Cafe': 20,'Restaurant': 15, 'Hotel': 12}
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


# ─── NOMINATIM (OpenStreetMap) INTEGRATION ───────────────────────────────────

HOTEL_LUXURY = ["taj ", "oberoi", "leela", "four seasons", "jw marriott", "grand hyatt",
                "ritz-carlton", "aman", "raffles", "st. regis", "the imperial", "trident"]
HOTEL_UPSCALE = ["marriott", "hilton", "sheraton", "radisson", "novotel", "crowne plaza",
                 "holiday inn", "hyatt regency", "courtyard", "westin", "renaissance", "le meridien"]

# Query strings sent to Nominatim — {city} and {state} are interpolated at runtime
SEGMENT_QUERIES = {
    "Hotel":        "hotel {city} in {state} India",
    "Restaurant":   "restaurant in {city} in {state} India",
    "Cafe":         "cafe in {city} in {state} India",
    # "Bakery":       "bakery shop in {city} in {state} India",
    # "CloudKitchen": "cloud kitchen in {city} in {state} India",
    # "Catering":     "catering services in {city} in {state} India",
    # "Mithai":       "sweet shop mithai in {city} in {state} India",
    # "IceCream":     "ice cream parlor in {city} in {state} India",
}


def detect_hotel_category(name: str) -> str:
    nl = name.lower()
    if any(b in nl for b in HOTEL_LUXURY): return "5-star"
    if any(b in nl for b in HOTEL_UPSCALE): return "4-star"
    return "3-star"


def nominatim_place_to_lead(place: dict, segment: str, city: str, state: str) -> dict:
    """Map a Nominatim OSM result to a lead dict."""
    name = place.get("name", "").strip()
    display_name = place.get("display_name", "")
    tier = 1 if city in METRO_CITIES else 2
    hotel_cat = detect_hotel_category(name) if segment == "Hotel" else ""

    lead = {
        "business_name": name,
        "segment": segment,
        "city": city, "state": state, "tier": tier,
        "address": display_name,
        "phone": "", "email": "", "website": "",
        "rating": 0.0,
        "num_outlets": 1,
        "decision_maker_name": "", "decision_maker_role": "", "decision_maker_linkedin": "",
        "has_dessert_menu": segment in ["Bakery", "Mithai", "IceCream", "Hotel", "Cafe"],
        "hotel_category": hotel_cat,
        "is_chain": False,
        "source": "openstreetmap",
        "monthly_volume_estimate": ""
    }
    score, priority, reasoning = calculate_lead_score(lead)
    lead["ai_score"] = score; lead["ai_reasoning"] = reasoning; lead["priority"] = priority
    return lead


async def search_nominatim(query: str) -> list:
    """Call the Nominatim OpenStreetMap search API (free, no API key required)."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "limit": 10, "addressdetails": 0}
    # Nominatim requires a descriptive User-Agent per usage policy
    headers = {"User-Agent": "DhampurGreen-HORECA-LeadTool/1.0 (internal B2B sales tool)"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 200:
                return resp.json()
            logger.error(f"Nominatim API {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"Nominatim request failed: {e}")
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
    # "Bakery": [
    #     {"sfx": "Artisan Bakery & Patisserie", "rating": 4.5, "outlets": 4, "has_dessert": True, "is_chain": False, "vol": "200-400 kg"},
    #     {"sfx": "Cake & Confectionery Shop", "rating": 4.3, "outlets": 12, "has_dessert": True, "is_chain": True, "vol": "500-900 kg"},
    #     {"sfx": "French Bakery & Boulangerie", "rating": 4.7, "outlets": 3, "has_dessert": True, "is_chain": False, "vol": "250-450 kg"},
    #     {"sfx": "Wedding Cake Studio", "rating": 4.6, "outlets": 2, "has_dessert": True, "is_chain": False, "vol": "150-300 kg"},
    #     {"sfx": "Sourdough & Bread House", "rating": 4.4, "outlets": 8, "has_dessert": True, "is_chain": True, "vol": "300-550 kg"},
    #     {"sfx": "Mithai & Pastry Shop", "rating": 4.2, "outlets": 15, "has_dessert": True, "is_chain": True, "vol": "600-1000 kg"},
    #     {"sfx": "Cupcake & Macaron Boutique", "rating": 4.6, "outlets": 5, "has_dessert": True, "is_chain": False, "vol": "100-200 kg"},
    #     {"sfx": "Industrial Bread Factory", "rating": 4.0, "outlets": 1, "has_dessert": True, "is_chain": False, "vol": "1000-2000 kg"},
    # ],
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
    # "CloudKitchen": [
    #     {"sfx": "Cloud Eats Kitchen", "rating": 4.0, "outlets": 15, "has_dessert": False, "is_chain": True, "vol": "300-500 kg"},
    #     {"sfx": "Dark Kitchen Hub", "rating": 3.9, "outlets": 8, "has_dessert": True, "is_chain": True, "vol": "200-350 kg"},
    #     {"sfx": "Multi-Brand Food Factory", "rating": 4.1, "outlets": 25, "has_dessert": True, "is_chain": True, "vol": "500-900 kg"},
    #     {"sfx": "Healthy Meal Prep Kitchen", "rating": 4.3, "outlets": 6, "has_dessert": False, "is_chain": True, "vol": "100-200 kg"},
    #     {"sfx": "Dessert Delivery Kitchen", "rating": 4.2, "outlets": 10, "has_dessert": True, "is_chain": True, "vol": "250-450 kg"},
    #     {"sfx": "Virtual Biryani House", "rating": 4.0, "outlets": 20, "has_dessert": True, "is_chain": True, "vol": "400-700 kg"},
    #     {"sfx": "Tiffin & Meal Box Kitchen", "rating": 3.8, "outlets": 5, "has_dessert": True, "is_chain": False, "vol": "150-280 kg"},
    # ],
    # "Catering": [
    #     {"sfx": "Events & Catering Co", "rating": 4.2, "outlets": 1, "has_dessert": True, "is_chain": False, "vol": "200-400 kg"},
    #     {"sfx": "Corporate Caterers", "rating": 4.0, "outlets": 3, "has_dessert": True, "is_chain": True, "vol": "300-600 kg"},
    #     {"sfx": "Wedding & Social Caterers", "rating": 4.4, "outlets": 2, "has_dessert": True, "is_chain": False, "vol": "500-1000 kg"},
    #     {"sfx": "Industrial & Hospital Catering", "rating": 3.9, "outlets": 8, "has_dessert": True, "is_chain": True, "vol": "800-1500 kg"},
    #     {"sfx": "School & College Canteen Mgmt", "rating": 4.0, "outlets": 15, "has_dessert": True, "is_chain": True, "vol": "400-800 kg"},
    #     {"sfx": "Outdoor Event Specialists", "rating": 4.3, "outlets": 1, "has_dessert": True, "is_chain": False, "vol": "600-1200 kg"},
    # ],
    # "Mithai": [
    #     {"sfx": "Traditional Sweets & Namkeen", "rating": 4.3, "outlets": 6, "has_dessert": True, "is_chain": True, "vol": "600-1000 kg"},
    #     {"sfx": "Mithai Bhandar", "rating": 4.4, "outlets": 2, "has_dessert": True, "is_chain": False, "vol": "200-400 kg"},
    #     {"sfx": "Premium Sweets & Gift Shop", "rating": 4.5, "outlets": 10, "has_dessert": True, "is_chain": True, "vol": "800-1500 kg"},
    #     {"sfx": "Kaju Katli & Barfi House", "rating": 4.3, "outlets": 4, "has_dessert": True, "is_chain": False, "vol": "300-600 kg"},
    #     {"sfx": "Halwai & Sweet Maker", "rating": 4.1, "outlets": 1, "has_dessert": True, "is_chain": False, "vol": "150-300 kg"},
    #     {"sfx": "Festive Sweets Emporium", "rating": 4.4, "outlets": 8, "has_dessert": True, "is_chain": True, "vol": "500-900 kg"},
    #     {"sfx": "Sugar-Free & Diet Sweets", "rating": 4.2, "outlets": 3, "has_dessert": True, "is_chain": False, "vol": "100-200 kg"},
    # ],
    # "IceCream": [
    #     {"sfx": "Artisan Creamery & Scoops", "rating": 4.5, "outlets": 10, "has_dessert": True, "is_chain": True, "vol": "400-700 kg"},
    #     {"sfx": "Artisan Gelato & Sorbet", "rating": 4.6, "outlets": 3, "has_dessert": True, "is_chain": False, "vol": "150-300 kg"},
    #     {"sfx": "Kulfi & Falooda Parlour", "rating": 4.2, "outlets": 5, "has_dessert": True, "is_chain": True, "vol": "200-400 kg"},
    #     {"sfx": "Shake & Sundae Bar", "rating": 4.4, "outlets": 15, "has_dessert": True, "is_chain": True, "vol": "300-600 kg"},
    #     {"sfx": "Premium Frozen Dessert Shop", "rating": 4.5, "outlets": 8, "has_dessert": True, "is_chain": True, "vol": "350-650 kg"},
    #     {"sfx": "Natural Fruit Ice Cream", "rating": 4.3, "outlets": 20, "has_dessert": True, "is_chain": True, "vol": "500-900 kg"},
    #     {"sfx": "Waffle & Ice Cream Studio", "rating": 4.6, "outlets": 6, "has_dessert": True, "is_chain": False, "vol": "250-450 kg"},
    # ],
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
async def get_dashboard_stats():
    async with AsyncSessionLocal() as session:
        total_leads = (await session.execute(
            select(func.count()).select_from(LeadModel)
        )).scalar() or 0

        high_priority = (await session.execute(
            select(func.count()).select_from(LeadModel).where(LeadModel.priority == "High")
        )).scalar() or 0

        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        new_this_week = (await session.execute(
            select(func.count()).select_from(LeadModel).where(LeadModel.created_at >= week_ago)
        )).scalar() or 0

        converted = (await session.execute(
            select(func.count()).select_from(LeadModel).where(LeadModel.status == "converted")
        )).scalar() or 0

        conversion_rate = round((converted / total_leads * 100), 1) if total_leads > 0 else 0

        city_result = await session.execute(
            select(LeadModel.city, func.count(LeadModel.id).label('count'))
            .group_by(LeadModel.city)
            .order_by(desc(func.count(LeadModel.id)))
            .limit(8)
        )
        city_dist = [{"city": row.city or "Unknown", "count": row.count} for row in city_result]

        seg_result = await session.execute(
            select(LeadModel.segment, func.count(LeadModel.id).label('count'))
            .group_by(LeadModel.segment)
            .order_by(desc(func.count(LeadModel.id)))
        )
        seg_dist = [{"segment": row.segment or "Unknown", "count": row.count} for row in seg_result]

        status_result = await session.execute(
            select(LeadModel.status, func.count(LeadModel.id).label('count'))
            .group_by(LeadModel.status)
        )
        status_dist = [{"status": row.status or "Unknown", "count": row.count} for row in status_result]

        recent_result = await session.execute(
            select(LeadModel).order_by(desc(LeadModel.created_at)).limit(6)
        )
        recent = [model_to_dict(r) for r in recent_result.scalars()]

        top_result = await session.execute(
            select(LeadModel).order_by(desc(LeadModel.ai_score)).limit(5)
        )
        top_leads = [model_to_dict(r) for r in top_result.scalars()]

    return {
        "total_leads": total_leads or 0,
        "high_priority": high_priority or 0,
        "new_this_week": new_this_week or 0,
        "converted": converted or 0,
        "conversion_rate": conversion_rate,
        "city_distribution": city_dist,
        "segment_distribution": seg_dist,
        "status_distribution": status_dist,
        "recent_leads": recent,
        "top_leads": top_leads
    }


@api_router.get("/leads")
async def get_leads(
    city: Optional[str] = None, segment: Optional[str] = None,
    priority: Optional[str] = None, status: Optional[str] = None,
    min_score: Optional[int] = None, search: Optional[str] = None,
    limit: int = 100, skip: int = 0,
    db: AsyncSession = Depends(get_db)
):
    async with AsyncSessionLocal() as session:
        stmt = select(LeadModel)
        count_stmt = select(func.count()).select_from(LeadModel)

        if city:
            stmt = stmt.where(LeadModel.city.ilike(f"%{city}%"))
            count_stmt = count_stmt.where(LeadModel.city.ilike(f"%{city}%"))
        if segment:
            stmt = stmt.where(LeadModel.segment == segment)
            count_stmt = count_stmt.where(LeadModel.segment == segment)
        if priority:
            stmt = stmt.where(LeadModel.priority == priority)
            count_stmt = count_stmt.where(LeadModel.priority == priority)
        if status:
            stmt = stmt.where(LeadModel.status == status)
            count_stmt = count_stmt.where(LeadModel.status == status)
        if min_score is not None:
            stmt = stmt.where(LeadModel.ai_score >= min_score)
            count_stmt = count_stmt.where(LeadModel.ai_score >= min_score)
        if search:
            search_filter = or_(
                LeadModel.business_name.ilike(f"%{search}%"),
                LeadModel.city.ilike(f"%{search}%"),
                LeadModel.decision_maker_name.ilike(f"%{search}%")
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        total = (await session.execute(count_stmt)).scalar() or 0
        result = await session.execute(
            stmt.order_by(desc(LeadModel.ai_score)).offset(skip).limit(limit)
        )
        leads = [model_to_dict(r) for r in result.scalars()]

    return {"leads": leads, "total": total}


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
    created = []
    errors = []

    async with AsyncSessionLocal() as session:
        for i, row in enumerate(reader):
            try:
                lead_data = {
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
                    "has_dessert_menu": str(row.get('has_dessert_menu', 'false')).lower().strip() in ('true', '1', 'yes'),
                    "hotel_category": str(row.get('hotel_category', '')).strip(),
                    "is_chain": str(row.get('is_chain', 'false')).lower().strip() in ('true', '1', 'yes'),
                    "source": "csv_upload",
                    "monthly_volume_estimate": str(row.get('monthly_volume_estimate', '')).strip()
                }
                if not lead_data['business_name'] or not lead_data['city']:
                    errors.append(f"Row {i + 2}: Missing business_name or city")
                    continue
                doc = make_lead_doc(lead_data)
                session.add(LeadModel(**doc))
                created.append(doc)
            except Exception as e:
                errors.append(f"Row {i + 2}: {str(e)}")
        await session.commit()

    await db.commit()
    return {"created": len(created), "errors": errors}


@api_router.post("/leads/discover")
async def discover_leads(req: DiscoverRequest):
    city = req.city.strip()
    segment = req.segment.strip()
    state = req.state.strip()
    results = []

    logger.info(f"[DISCOVER] Request — city={city!r}, segment={segment!r}, state={state!r}")

    query_tmpl = SEGMENT_QUERIES.get(segment, "restaurant {city} {state} India")
    query = query_tmpl.replace("{city}", city).replace("{state}", state)
    logger.info(f"[DISCOVER] Nominatim query: {query!r}")

    places = await search_nominatim(query)
    logger.info(f"[DISCOVER] Nominatim returned {len(places)} place(s)")

    for place in places:
        name = place.get("name", "").strip()
        if not name:
            logger.debug(f"[DISCOVER] Skipping place with no name: {place.get('display_name', '')[:60]}")
            continue
        lead = nominatim_place_to_lead(place, segment, city, state)
        logger.info(f"[DISCOVER] OSM lead: {lead['business_name']!r} (type={place.get('type','?')}) — score={lead['ai_score']}, priority={lead['priority']}")
        results.append(lead)

    logger.info(f"[DISCOVER] OSM leads added: {len(results)}")

    # Only supplement with simulation if OSM returned at least one result
    if results:
        simulated = generate_lead_simulation(city, segment, state)
        logger.info(f"[DISCOVER] Simulated leads generated: {len(simulated)}")
        for s in simulated:
            logger.debug(f"[DISCOVER] Simulated: {s['business_name']!r} — score={s['ai_score']}, priority={s['priority']}")
        results.extend(simulated)
        logger.info(f"[DISCOVER] Total leads returned: {len(results)} (OSM={len(results) - len(simulated)}, Simulated={len(simulated)})")
    else:
        logger.warning(f"[DISCOVER] Nominatim returned 0 usable places for city={city!r}, segment={segment!r} — skipping simulation")
        logger.info("[DISCOVER] Total leads returned: 0")

    return results


@api_router.post("/leads/bulk-create")
async def bulk_create_leads(req: BulkCreateRequest, db: AsyncSession = Depends(get_db)):
    created = []
    async with AsyncSessionLocal() as session:
        for lead_dict in req.leads:
            lead_dict.pop('ai_score', None)
            lead_dict.pop('ai_reasoning', None)
            lead_dict.pop('priority', None)
            doc = make_lead_doc(lead_dict)
            session.add(LeadModel(**doc))
            created.append(doc)
        await session.commit()
    return {"created": len(created), "leads": created}


@api_router.post("/leads")
async def create_lead(lead: LeadCreate):
    doc = make_lead_doc(lead.model_dump())
    async with AsyncSessionLocal() as session:
        session.add(LeadModel(**doc))
        await session.commit()
    return doc


@api_router.get("/leads/{lead_id}")
async def get_lead(lead_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(LeadModel).where(LeadModel.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        return model_to_dict(lead)


@api_router.put("/leads/{lead_id}/status")
async def update_lead_status(lead_id: str, body: LeadStatusUpdate):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(LeadModel).where(LeadModel.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        lead.status = body.status
        lead.updated_at = datetime.now(timezone.utc).isoformat()
        await session.commit()
        await session.refresh(lead)
        return model_to_dict(lead)


@api_router.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(LeadModel).where(LeadModel.id == lead_id))
        lead = result.scalar_one_or_none()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        await session.delete(lead)
        await session.commit()
    return {"message": "Lead deleted"}


@api_router.post("/leads/{lead_id}/qualify-ai")
async def qualify_lead_ai(lead_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(LeadModel).where(LeadModel.id == lead_id))
        lead_obj = result.scalar_one_or_none()
        if not lead_obj:
            raise HTTPException(status_code=404, detail="Lead not found")
        lead = model_to_dict(lead_obj)

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
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(LeadModel).where(LeadModel.id == lead_id))
            lead_obj = result.scalar_one_or_none()
            if lead_obj:
                lead_obj.ai_score = int(ai_data.get('ai_score', lead['ai_score']))
                lead_obj.ai_reasoning = ai_data.get('qualification_summary', lead['ai_reasoning'])
                lead_obj.priority = ai_data.get('priority', lead['priority'])
                lead_obj.monthly_volume_estimate = ai_data.get('monthly_volume_kg', '')
                lead_obj.updated_at = datetime.now(timezone.utc).isoformat()
                await session.commit()
                await session.refresh(lead_obj)
                updated = model_to_dict(lead_obj)
        return {"lead": updated, "ai_analysis": ai_data}
    except Exception as e:
        logger.error(f"AI qualify error: {e}")
        raise HTTPException(status_code=500, detail=f"AI qualification failed: {str(e)}")


@api_router.post("/leads/{lead_id}/generate-email")
async def generate_email(lead_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(LeadModel).where(LeadModel.id == lead_id))
        lead_obj = result.scalar_one_or_none()
        if not lead_obj:
            raise HTTPException(status_code=404, detail="Lead not found")
        lead = model_to_dict(lead_obj)

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

        now = datetime.now(timezone.utc)
        doc = {
            "id": str(uuid.uuid4()),
            "lead_id": lead_id,
            "lead_name": lead['business_name'],
            "lead_city": lead['city'],
            "lead_segment": lead['segment'],
            "subject": subject,
            "body": body,
            "status": "draft",
            "generated_at": now.isoformat(),
            "sent_at": None
        }
        async with AsyncSessionLocal() as session:
            session.add(OutreachEmailModel(**doc))
            await session.commit()
        doc.pop('sent_at', None)
        return doc
    except Exception as e:
        logger.error(f"Email gen error: {e}")
        raise HTTPException(status_code=500, detail=f"Email generation failed: {str(e)}")


@api_router.get("/outreach/emails")
async def get_all_emails(limit: int = 50):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OutreachEmailModel).order_by(desc(OutreachEmailModel.generated_at)).limit(limit)
        )
        return [model_to_dict(e) for e in result.scalars()]


@api_router.get("/outreach/{lead_id}/emails")
async def get_lead_emails(lead_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OutreachEmailModel)
            .where(OutreachEmailModel.lead_id == lead_id)
            .order_by(desc(OutreachEmailModel.generated_at))
            .limit(20)
        )
        return [model_to_dict(e) for e in result.scalars()]


@api_router.put("/outreach/{email_id}/mark-sent")
async def mark_email_sent(email_id: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OutreachEmailModel).where(OutreachEmailModel.id == email_id)
        )
        email = result.scalar_one_or_none()
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        email.status = "sent"
        email.sent_at = datetime.now(timezone.utc).isoformat()
        await session.commit()
        await session.refresh(email)
        return model_to_dict(email)


@api_router.post("/seed-mock-data")
async def seed_mock_data():
    async with AsyncSessionLocal() as session:
        count = (await session.execute(
            select(func.count()).select_from(LeadModel)
        )).scalar() or 0
    if count > 0:
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

    async with AsyncSessionLocal() as session:
        statuses = ["new", "new", "new", "new", "contacted", "contacted", "qualified", "converted", "lost"]
        created = 0
        for i, lead_data in enumerate(mock_leads):
            score, priority, reasoning = calculate_lead_score(lead_data)
            status = statuses[i % len(statuses)]
            days_ago = random.randint(0, 45)
            ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
            doc = {
                "id": str(uuid.uuid4()),
                **lead_data,
                "ai_score": score,
                "ai_reasoning": reasoning,
                "priority": priority,
                "status": status,
                "created_at": ts.isoformat(),
                "updated_at": ts.isoformat()
            }
            session.add(LeadModel(**doc))
            created += 1

        await session.commit()
        return {"message": f"Seeded {created} HORECA leads", "count": created}


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)



