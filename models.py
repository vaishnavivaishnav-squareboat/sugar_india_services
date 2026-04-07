from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from database import Base
import uuid
from ulid import ULID


def gen_uuid():
    return str(uuid.uuid4())


def gen_ulid():
    return str(ULID())


class Lead(Base):
    __tablename__ = "leads"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    business_name = Column(String(255), nullable=False, index=True)
    segment = Column(String(50), index=True, default="Restaurant")
    city = Column(String(100), index=True, default="")
    state = Column(String(100), default="")
    tier = Column(Integer, default=1)
    address = Column(Text, default="")
    phone = Column(String(50), default="")
    email = Column(String(255), default="")
    website = Column(String(500), default="")
    rating = Column(Float, default=0.0)
    num_outlets = Column(Integer, default=1)
    decision_maker_name = Column(String(255), default="")
    decision_maker_role = Column(String(255), default="")
    decision_maker_linkedin = Column(String(500), default="")
    has_dessert_menu = Column(Boolean, default=False)
    hotel_category = Column(String(50), default="")
    is_chain = Column(Boolean, default=False)
    ai_score = Column(Integer, default=0, index=True)
    ai_reasoning = Column(Text, default="")
    priority = Column(String(20), default="Low", index=True)
    status = Column(String(50), default="new", index=True)
    source = Column(String(50), default="manual")
    monthly_volume_estimate = Column(String(100), default="")
    highlights = Column(JSON, default=list)                          # e.g. ["Great dessert", "Great coffee"]
    offerings = Column(JSON, default=list)                           # e.g. ["Coffee", "Wine", "Vegan options"]
    dining_options = Column(JSON, default=list)                      # e.g. ["Breakfast", "Dessert", "Dinner"]
    sugar_signal_from_highlights = Column(Boolean, default=False)    # AI-detected sugar signal
    highlight_sugar_signals = Column(JSON, default=list)             # specific highlight keywords
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "business_name": self.business_name,
            "segment": self.segment or "",
            "city": self.city or "",
            "state": self.state or "",
            "tier": self.tier or 1,
            "address": self.address or "",
            "phone": self.phone or "",
            "email": self.email or "",
            "website": self.website or "",
            "rating": self.rating or 0.0,
            "num_outlets": self.num_outlets or 1,
            "decision_maker_name": self.decision_maker_name or "",
            "decision_maker_role": self.decision_maker_role or "",
            "decision_maker_linkedin": self.decision_maker_linkedin or "",
            "has_dessert_menu": bool(self.has_dessert_menu),
            "hotel_category": self.hotel_category or "",
            "is_chain": bool(self.is_chain),
            "ai_score": self.ai_score or 0,
            "ai_reasoning": self.ai_reasoning or "",
            "priority": self.priority or "Low",
            "status": self.status or "new",
            "source": self.source or "manual",
            "monthly_volume_estimate": self.monthly_volume_estimate or "",
            "highlights": self.highlights or [],
            "offerings": self.offerings or [],
            "dining_options": self.dining_options or [],
            "sugar_signal_from_highlights": bool(self.sugar_signal_from_highlights),
            "highlight_sugar_signals": self.highlight_sugar_signals or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class OutreachEmail(Base):
    __tablename__ = "outreach_emails"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    lead_id = Column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    lead_name = Column(String(255), default="")
    lead_city = Column(String(100), default="")
    lead_segment = Column(String(50), default="")
    subject = Column(Text, default="")
    body = Column(Text, default="")
    status = Column(String(50), default="draft")
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "lead_name": self.lead_name or "",
            "lead_city": self.lead_city or "",
            "lead_segment": self.lead_segment or "",
            "subject": self.subject or "",
            "body": self.body or "",
            "status": self.status or "draft",
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
        }


# ─── HORECA PIPELINE TABLES ───────────────────────────────────────────────
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy import func as sa_func

class City(Base):
    __tablename__ = "cities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ulid = Column(String(26), unique=True, nullable=False, default=gen_ulid)
    name = Column(String(100), nullable=False, index=True)
    state = Column(String(100), default="")
    country = Column(String(100), default="India")
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=1)
    last_processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=sa_func.now())
    updated_at = Column(DateTime(timezone=True), server_default=sa_func.now(), onupdate=sa_func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "ulid": self.ulid,
            "name": self.name,
            "state": self.state or "",
            "country": self.country,
            "is_active": self.is_active,
            "priority": self.priority,
            "last_processed_at": self.last_processed_at.isoformat() if self.last_processed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ulid = Column(String(26), unique=True, nullable=False, default=gen_ulid)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=False, index=True)
    status = Column(String(20), default="pending", index=True)  # pending, running, completed, failed
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    logs = Column(MySQLJSON, default=dict)

    def to_dict(self):
        return {
            "id": self.id,
            "ulid": self.ulid,
            "city_id": self.city_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "logs": self.logs,
        }


# ─── CONTACTS TABLE ─────────────────────────────────────────────────────
class Segment(Base):
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ulid = Column(String(26), unique=True, nullable=False, default=gen_ulid)
    key = Column(String(50), nullable=False, unique=True, index=True)   # e.g. "Bakery"
    label = Column(String(100), nullable=False)                          # e.g. "Bakery"
    cluster = Column(String(100), default="")                            # e.g. "Bakery & Confectionery"
    description = Column(String(500), default="")
    color = Column(String(20), default="#5C736A")                        # hex colour used in UI
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=sa_func.now())
    updated_at = Column(DateTime(timezone=True), server_default=sa_func.now(), onupdate=sa_func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "ulid": self.ulid,
            "key": self.key,
            "label": self.label,
            "cluster": self.cluster,
            "description": self.description,
            "color": self.color,
            "is_active": self.is_active,
            "priority": self.priority,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    role = Column(String(100), nullable=False)
    email = Column(String(255), default="")
    linkedin_url = Column(String(500), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "name": self.name,
            "role": self.role,
            "email": self.email,
            "linkedin_url": self.linkedin_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
