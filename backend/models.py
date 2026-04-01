from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from database import Base
import uuid


def gen_uuid():
    return str(uuid.uuid4())


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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

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
