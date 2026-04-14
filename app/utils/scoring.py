"""
app/services/scoring.py
─────────────────────────────────────────────────────────────────────────────
Lead scoring engine and lead object factory.
─────────────────────────────────────────────────────────────────────────────
"""
import uuid
from app.db.orm import Lead


def calculate_lead_score(data: dict):
    """
    Compute a 0-100 AI score, assign priority (High/Medium/Low), and produce
    a human-readable reasoning string for the given lead data dict.
    """
    score, reasons = 0, []

    hotel_cat = data.get("hotel_category", "")
    if hotel_cat == "5-star":
        score += 30; reasons.append("5-star hotel (+30)")
    elif hotel_cat == "4-star":
        score += 20; reasons.append("4-star hotel (+20)")
    elif hotel_cat == "3-star":
        score += 10; reasons.append("3-star hotel (+10)")

    segment = data.get("segment", "")
    seg_pts = {
        # High-volume daily consumers
        "Mithai": 30, "Bakery": 28, "FoodProcessing": 26,
        "IceCream": 24, "Beverage": 22,
        # Medium-volume
        "Catering": 20, "Cafe": 20, "Organic": 18,
        "CloudKitchen": 18, "Brewery": 16,
        # Lower per-unit
        "Restaurant": 15, "Hotel": 12,
    }
    if segment in seg_pts:
        pts = seg_pts[segment]
        score += pts
        reasons.append(f"{segment} segment (+{pts})")

    if data.get("is_chain"):
        score += 15
        reasons.append("Chain business (+15)")

    outlets = int(data.get("num_outlets", 1) or 1)
    if outlets >= 10:
        score += 15; reasons.append(f"{outlets} outlets (+15)")
    elif outlets >= 3:
        score += 10; reasons.append(f"{outlets} outlets (+10)")

    rating = float(data.get("rating", 0) or 0)
    if rating >= 4.5:
        score += 10; reasons.append("Rating 4.5+ (+10)")
    elif rating >= 4.0:
        score += 7; reasons.append("Rating 4.0+ (+7)")

    tier = int(data.get("tier", 3) or 3)
    if tier == 1:
        score += 10; reasons.append("Metro city (+10)")
    elif tier == 2:
        score += 5; reasons.append("Tier 2 city (+5)")

    if data.get("has_dessert_menu"):
        score += 15; reasons.append("Has dessert/sweet menu (+15)")
    if data.get("decision_maker_name") or data.get("contact_has_linkedin"):
        score += 10; reasons.append("Decision maker identified (+10)")

    score = min(score, 100)
    priority = "High" if score >= 70 else ("Medium" if score >= 40 else "Low")
    reasoning = " | ".join(reasons) if reasons else "Insufficient data for scoring"
    return score, priority, reasoning


def make_lead_obj(data: dict, status: str = "new") -> Lead:
    """Create and return a Lead ORM instance from a raw data dict."""
    score, priority, reasoning = calculate_lead_score(data)
    return Lead(
        id=str(uuid.uuid4()),
        business_name=data.get("business_name", ""),
        segment=data.get("segment", "Restaurant"),
        city=data.get("city", ""),
        state=data.get("state", ""),
        country=data.get("country", "India"),
        tier=int(data.get("tier", 1) or 1),
        address=data.get("address", ""),
        phone=data.get("phone", ""),
        email=data.get("email", ""),
        website=data.get("website", ""),
        description=data.get("description", ""),
        rating=float(data.get("rating", 0) or 0),
        num_outlets=int(data.get("num_outlets", 1) or 1),
        has_dessert_menu=bool(data.get("has_dessert_menu", False)),
        hotel_category=data.get("hotel_category", ""),
        is_chain=bool(data.get("is_chain", False)),
        source=data.get("source", "manual"),
        monthly_volume_estimate=data.get("monthly_volume_estimate", ""),
        ai_score=score,
        ai_reasoning=reasoning,
        priority=priority,
        status=status,
    )
