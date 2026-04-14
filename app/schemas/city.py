"""
app/schemas/city.py
─────────────────────────────────────────────────────────────────────────────
Pydantic schemas for City-related request bodies.
─────────────────────────────────────────────────────────────────────────────
"""
from pydantic import BaseModel


class CityCreate(BaseModel):
    name: str
    state: str = ""
    country: str = "India"
    priority: int = 1


class CityPriorityUpdate(BaseModel):
    priority: int
