"""
app/api/routes/city.py
─────────────────────────────────────────────────────────────────────────────
All /cities/* endpoints for the HORECA Lead Intelligence API.
─────────────────────────────────────────────────────────────────────────────
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.db.orm import City
from app.schemas.city import CityCreate, CityPriorityUpdate

city_router = APIRouter(prefix="/cities")


@city_router.get("")
async def list_cities():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(City).order_by(City.priority.asc(), City.name.asc()))
        return [c.to_dict() for c in result.scalars().all()]


@city_router.post("", status_code=201)
async def add_city(body: CityCreate):
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(City).where(func.lower(City.name) == body.name.strip().lower())
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"City '{body.name}' already exists")
        city = City(
            name=body.name.strip(), state=body.state.strip(),
            country=body.country, priority=body.priority, is_active=True,
        )
        session.add(city)
        await session.commit()
        await session.refresh(city)
        return city.to_dict()


@city_router.put("/{city_id}/toggle")
async def toggle_city(city_id: int):
    async with AsyncSessionLocal() as session:
        city = await session.get(City, city_id)
        if not city:
            raise HTTPException(status_code=404, detail="City not found")
        city.is_active = not city.is_active
        await session.commit()
        await session.refresh(city)
        return city.to_dict()


@city_router.put("/{city_id}/priority")
async def update_city_priority(city_id: int, body: CityPriorityUpdate):
    async with AsyncSessionLocal() as session:
        city = await session.get(City, city_id)
        if not city:
            raise HTTPException(status_code=404, detail="City not found")
        city.priority = max(1, body.priority)
        await session.commit()
        await session.refresh(city)
        return city.to_dict()


@city_router.delete("/{city_id}", status_code=204)
async def delete_city(city_id: int):
    async with AsyncSessionLocal() as session:
        city = await session.get(City, city_id)
        if not city:
            raise HTTPException(status_code=404, detail="City not found")
        await session.delete(city)
        await session.commit()
    return Response(status_code=204)
