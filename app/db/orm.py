"""
app/models/orm.py
─────────────────────────────────────────────────────────────────────────────
SQLAlchemy ORM models for the Dhampur Green HORECA lead intelligence system.
All models inherit from app.db.session.Base.
─────────────────────────────────────────────────────────────────────────────
"""
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.dialects.mysql import JSON as MySQLJSON

from app.db.session import Base

import uuid
from ulid import ULID
from ulid import base32


def gen_uuid():
    return str(uuid.uuid4())


def gen_ulid():
    try:
        # Encode ULID bytes explicitly to a 26-char base32 string
        return base32.encode(ULID().bytes)
    except Exception:
        # Fallback to a 26-char base32-encoded value derived from UUID4 bytes
        try:
            return base32.encode(uuid.uuid4().bytes)
        except Exception:
            # As a last resort, return a truncated UUID without dashes to fit 26 chars
            return uuid.uuid4().hex[:26]


# ─── LEAD ────────────────────────────────────────────────────────────────────

class Lead(Base):
    __tablename__ = "leads"

    # ── Identity ──────────────────────────────────────────────────────────────
    id            = Column(String(36), primary_key=True, default=gen_uuid)
    business_name = Column(String(255), nullable=False, index=True)
    segment       = Column(String(50),  index=True, default="Restaurant")
    source        = Column(String(50),  default="manual")

    # ── Location ──────────────────────────────────────────────────────────────
    city    = Column(String(100), index=True, default="")
    state   = Column(String(100), default="")
    country = Column(String(100), default="India")
    tier    = Column(Integer,     default=1)
    address = Column(Text,        default="")

    # ── Business contact (from Stage 1 / public info) ────────────────────────
    phone   = Column(String(50),  default="")   # business phone from SerpAPI
    email   = Column(String(255), default="")   # business email from SerpAPI
    website = Column(String(500), default="")

    # ── Profile ───────────────────────────────────────────────────────────────
    description  = Column(Text,    default="")
    rating       = Column(Float,   default=0.0)
    num_outlets  = Column(Integer, default=1)
    hotel_category = Column(String(50),  default="")
    is_chain       = Column(Boolean,     default=False)
    has_dessert_menu = Column(Boolean,   default=False)

    # ── AI enrichment ─────────────────────────────────────────────────────────
    ai_score       = Column(Integer, default=0, index=True)
    ai_reasoning   = Column(Text,    default="")
    priority       = Column(String(20), default="Low", index=True)
    status         = Column(String(50), default="new", index=True)
    monthly_volume_estimate = Column(String(100), default="")

    # ── Signals (from Stage 2) ────────────────────────────────────────────────
    highlights                   = Column(JSON, default=list)
    offerings                    = Column(JSON, default=list)
    dining_options               = Column(JSON, default=list)
    sugar_signal_from_highlights = Column(Boolean, default=False)
    highlight_sugar_signals      = Column(JSON, default=list)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id":            self.id,
            "business_name": self.business_name,
            "segment":       self.segment or "",
            "source":        self.source or "manual",
            "city":          self.city or "",
            "state":         self.state or "",
            "country":       self.country or "India",
            "tier":          self.tier or 1,
            "address":       self.address or "",
            "phone":         self.phone or "",
            "email":         self.email or "",
            "website":       self.website or "",
            "description":   self.description or "",
            "rating":        self.rating or 0.0,
            "num_outlets":   self.num_outlets or 1,
            "hotel_category":    self.hotel_category or "",
            "is_chain":          bool(self.is_chain),
            "has_dessert_menu":  bool(self.has_dessert_menu),
            "ai_score":          self.ai_score or 0,
            "ai_reasoning":      self.ai_reasoning or "",
            "priority":          self.priority or "Low",
            "status":            self.status or "new",
            "monthly_volume_estimate": self.monthly_volume_estimate or "",
            "highlights":                   self.highlights or [],
            "offerings":                    self.offerings or [],
            "dining_options":               self.dining_options or [],
            "sugar_signal_from_highlights": bool(self.sugar_signal_from_highlights),
            "highlight_sugar_signals":      self.highlight_sugar_signals or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ─── OUTREACH EMAIL ───────────────────────────────────────────────────────────

class OutreachEmail(Base):
    __tablename__ = "outreach_emails"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    lead_id = Column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    lead_name = Column(String(255), default="")
    lead_city = Column(String(100), default="")
    lead_segment = Column(String(50), default="")
    subject = Column(Text, default="")
    body = Column(Text, default="")
    status = Column(String(50), default="draft")  # use EmailStatus constants
    email_type = Column(String(20), default="initial")  # "initial" | "follow_up"
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)
    sent_to_email = Column(String(255), nullable=True)

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
            "email_type": self.email_type or "initial",
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "sent_to_email": self.sent_to_email or "",
        }


# ─── CITIES ──────────────────────────────────────────────────────────────────

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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

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


# ─── PIPELINE RUNS ────────────────────────────────────────────────────────────

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


# ─── SEGMENTS ─────────────────────────────────────────────────────────────────

class Segment(Base):
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ulid = Column(String(26), unique=True, nullable=False, default=gen_ulid)
    key = Column(String(50), nullable=False, unique=True, index=True)
    label = Column(String(100), nullable=False)
    cluster = Column(String(100), default="")
    description = Column(String(500), default="")
    color = Column(String(20), default="#5C736A")
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

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


# ─── CONTACTS ─────────────────────────────────────────────────────────────────

class Contact(Base):
    __tablename__ = "contacts"

    id      = Column(Integer,     primary_key=True, autoincrement=True)
    lead_id = Column(String(36),  ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)

    # ── Person identity ───────────────────────────────────────────────────────
    name       = Column(String(255), nullable=False)
    role       = Column(String(255), default="")   # job title / role
    department = Column(String(100), default="")
    seniority  = Column(String(50),  default="")   # senior / executive / etc.
    is_primary = Column(Boolean,     default=False) # true = promoted decision-maker

    # ── Contact details ───────────────────────────────────────────────────────
    email        = Column(String(255), default="")
    email_2      = Column(String(255), default="")  # secondary / work email 2
    phone        = Column(String(50),  default="")
    phone_2      = Column(String(50),  default="")  # secondary mobile
    linkedin_url = Column(String(500), default="")

    # ── Enrichment metadata ───────────────────────────────────────────────────
    confidence_score = Column(Float,       default=0.0)  # 0.0 – 1.0
    verified         = Column(String(50),  default="")   # valid / accept_all / unknown
    source           = Column(String(50),  default="")   # csv_upload / hunter_domain_search / serp+gemini / etc.

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id":               self.id,
            "lead_id":          self.lead_id,
            "name":             self.name or "",
            "role":             self.role or "",
            "department":       self.department or "",
            "seniority":        self.seniority or "",
            "is_primary":       bool(self.is_primary),
            "email":            self.email or "",
            "email_2":          self.email_2 or "",
            "phone":            self.phone or "",
            "phone_2":          self.phone_2 or "",
            "linkedin_url":     self.linkedin_url or "",
            "confidence_score": self.confidence_score or 0.0,
            "verified":         self.verified or "",
            "source":           self.source or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
