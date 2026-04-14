"""
app/api/routes/segment.py
─────────────────────────────────────────────────────────────────────────────
All /segments/* endpoints for the HORECA Lead Intelligence API.
─────────────────────────────────────────────────────────────────────────────
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.db.orm import Segment
from app.schemas.segment import SEGMENT_CATALOG, SegmentCreate, SegmentPriorityUpdate

segment_router = APIRouter(prefix="/segments")


@segment_router.get("")
async def list_segments():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Segment).order_by(Segment.priority.asc(), Segment.label.asc())
        )
        return [s.to_dict() for s in result.scalars().all()]


@segment_router.post("/seed", status_code=201)
async def seed_segments():
    """Idempotent seed — inserts catalog entries that do not yet exist."""
    async with AsyncSessionLocal() as session:
        created = []
        for i, entry in enumerate(SEGMENT_CATALOG, start=1):
            existing = await session.execute(
                select(Segment).where(func.lower(Segment.key) == entry["key"].lower())
            )
            if existing.scalar_one_or_none():
                continue
            seg = Segment(
                key=entry["key"], label=entry["label"], cluster=entry["cluster"],
                description=entry["description"], color=entry["color"],
                is_active=True, priority=i,
            )
            session.add(seg)
            created.append(entry["key"])
        await session.commit()
        return {"seeded": created, "total": len(created)}


@segment_router.post("", status_code=201)
async def create_segment(body: SegmentCreate):
    async with AsyncSessionLocal() as session:
        existing = await session.execute(
            select(Segment).where(func.lower(Segment.key) == body.key.strip().lower())
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"Segment key '{body.key}' already exists")
        max_priority = (await session.execute(select(func.max(Segment.priority)))).scalar() or 0
        seg = Segment(
            key=body.key.strip(), label=body.label.strip() or body.key.strip(),
            cluster=body.cluster.strip(), description=body.description.strip(),
            color=body.color, is_active=True, priority=max_priority + 1,
        )
        session.add(seg)
        await session.commit()
        await session.refresh(seg)
        return seg.to_dict()


@segment_router.delete("/{seg_id}", status_code=204)
async def delete_segment(seg_id: int):
    async with AsyncSessionLocal() as session:
        seg = await session.get(Segment, seg_id)
        if not seg:
            raise HTTPException(status_code=404, detail="Segment not found")
        await session.delete(seg)
        await session.commit()
    return Response(status_code=204)


@segment_router.put("/{seg_id}/toggle")
async def toggle_segment(seg_id: int):
    async with AsyncSessionLocal() as session:
        seg = await session.get(Segment, seg_id)
        if not seg:
            raise HTTPException(status_code=404, detail="Segment not found")
        seg.is_active = not seg.is_active
        await session.commit()
        await session.refresh(seg)
        return seg.to_dict()


@segment_router.put("/{seg_id}/priority")
async def update_segment_priority(seg_id: int, body: SegmentPriorityUpdate):
    async with AsyncSessionLocal() as session:
        seg = await session.get(Segment, seg_id)
        if not seg:
            raise HTTPException(status_code=404, detail="Segment not found")
        seg.priority = max(1, body.priority)
        await session.commit()
        await session.refresh(seg)
        return seg.to_dict()
