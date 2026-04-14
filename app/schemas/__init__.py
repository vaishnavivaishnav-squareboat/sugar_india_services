"""
app/schemas/__init__.py
─────────────────────────────────────────────────────────────────────────────
Re-exports all Pydantic schemas for convenience.
─────────────────────────────────────────────────────────────────────────────
"""
from app.schemas.lead import LeadCreate, LeadStatusUpdate, BulkCreateRequest, DiscoverRequest
from app.schemas.city import CityCreate, CityPriorityUpdate
from app.schemas.segment import SegmentCreate, SegmentPriorityUpdate
from app.schemas.contact import ContactCreate

__all__ = [
    "LeadCreate", "LeadStatusUpdate", "BulkCreateRequest", "DiscoverRequest",
    "CityCreate", "CityPriorityUpdate",
    "SegmentCreate", "SegmentPriorityUpdate",
    "ContactCreate",
]
