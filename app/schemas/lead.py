"""
app/schemas/lead.py
─────────────────────────────────────────────────────────────────────────────
Pydantic schemas for Lead-related request bodies.
─────────────────────────────────────────────────────────────────────────────
"""
from typing import List
from pydantic import BaseModel


class LeadCreate(BaseModel):
    business_name: str
    segment: str = "Restaurant"
    city: str
    state: str = ""
    country: str = "India"
    tier: int = 1
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    description: str = ""
    rating: float = 0.0
    num_outlets: int = 1
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
