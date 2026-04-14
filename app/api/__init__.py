"""
app/api/routes/__init__.py
─────────────────────────────────────────────────────────────────────────────
Aggregates all entity routers into a single api_router.
Import: from app.api.routes import api_router
─────────────────────────────────────────────────────────────────────────────
"""
from fastapi import APIRouter

from app.api.lead import lead_router
from app.api.city import city_router
from app.api.segment import segment_router
from app.api.contact import contact_router
from app.api.outreach import outreach_router
from app.api.dashboard import dashboard_router

api_router = APIRouter(prefix="/api")

api_router.include_router(dashboard_router)
api_router.include_router(lead_router)
api_router.include_router(city_router)
api_router.include_router(segment_router)
api_router.include_router(contact_router)
api_router.include_router(outreach_router)
