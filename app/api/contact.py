"""
app/api/routes/contact.py
─────────────────────────────────────────────────────────────────────────────
All /contacts/* endpoints for the HORECA Lead Intelligence API.
─────────────────────────────────────────────────────────────────────────────
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.db.orm import Contact
from app.schemas.contact import ContactCreate
from app.utils import model_to_dict

contact_router = APIRouter(prefix="/contacts")


@contact_router.get("")
async def list_contacts(lead_id: str | None = None):
    async with AsyncSessionLocal() as session:
        stmt = select(Contact)
        if lead_id:
            stmt = stmt.where(Contact.lead_id == lead_id)
        result = await session.execute(stmt)
        return [model_to_dict(c) for c in result.scalars().all()]


@contact_router.post("", status_code=201)
async def create_contact(body: ContactCreate):
    async with AsyncSessionLocal() as session:
        contact = Contact(**body.model_dump())
        session.add(contact)
        await session.commit()
        await session.refresh(contact)
        return model_to_dict(contact)


@contact_router.delete("/{contact_id}", status_code=204)
async def delete_contact(contact_id: str):
    async with AsyncSessionLocal() as session:
        contact = (await session.execute(
            select(Contact).where(Contact.id == contact_id)
        )).scalar_one_or_none()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        await session.delete(contact)
        await session.commit()
    return {"message": "Contact deleted"}
