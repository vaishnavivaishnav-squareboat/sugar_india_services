"""
app/schemas/contact.py
─────────────────────────────────────────────────────────────────────────────
Pydantic schemas for Contact-related request bodies.
─────────────────────────────────────────────────────────────────────────────
"""
from typing import Optional
from pydantic import BaseModel


class ContactCreate(BaseModel):
    lead_id: str
    name: str
    role: str = ""
    phone: str = ""
    email: str = ""
    linkedin: str = ""
    source: str = "manual"
    notes: Optional[str] = None
