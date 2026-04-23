"""
app/api/routes/dashboard.py
─────────────────────────────────────────────────────────────────────────────
Root, dashboard stats, and seed-mock-data endpoints.
─────────────────────────────────────────────────────────────────────────────
"""
import random
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter
from sqlalchemy import desc, func, select

from app.db.session import AsyncSessionLocal
from app.db.orm import Lead, Contact
from app.utils.scoring import calculate_lead_score
from app.utils import model_to_dict

dashboard_router = APIRouter()


@dashboard_router.get("/")
async def root():
    return {"message": "Dhampur Green HORECA Lead Intelligence API v2.0 (PostgreSQL)"}


@dashboard_router.get("/dashboard/stats")
async def get_dashboard_stats():
    async with AsyncSessionLocal() as session:
        total_leads = (await session.execute(
            select(func.count()).select_from(Lead)
        )).scalar() or 0

        high_priority = (await session.execute(
            select(func.count()).select_from(Lead).where(Lead.priority == "High")
        )).scalar() or 0

        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        new_this_week = (await session.execute(
            select(func.count()).select_from(Lead).where(Lead.created_at >= week_ago)
        )).scalar() or 0

        converted = (await session.execute(
            select(func.count()).select_from(Lead).where(Lead.status == "converted")
        )).scalar() or 0

        conversion_rate = round((converted / total_leads * 100), 1) if total_leads > 0 else 0

        city_result = await session.execute(
            select(Lead.city, func.count(Lead.id).label("count"))
            .group_by(Lead.city)
            .order_by(desc(func.count(Lead.id)))
            .limit(8)
        )
        city_dist = [{"city": row.city or "Unknown", "count": row.count} for row in city_result]

        seg_result = await session.execute(
            select(Lead.segment, func.count(Lead.id).label("count"))
            .group_by(Lead.segment)
            .order_by(desc(func.count(Lead.id)))
        )
        seg_dist = [{"segment": row.segment or "Unknown", "count": row.count} for row in seg_result]

        status_result = await session.execute(
            select(Lead.status, func.count(Lead.id).label("count"))
            .group_by(Lead.status)
        )
        status_dist = [{"status": row.status or "Unknown", "count": row.count} for row in status_result]

        recent = [model_to_dict(r) for r in (await session.execute(
            select(Lead).order_by(desc(Lead.created_at)).limit(6)
        )).scalars()]

        top_leads = [model_to_dict(r) for r in (await session.execute(
            select(Lead).order_by(desc(Lead.ai_score)).limit(5)
        )).scalars()]

    return {
        "total_leads":          total_leads or 0,
        "high_priority":        high_priority or 0,
        "new_this_week":        new_this_week or 0,
        "converted":            converted or 0,
        "conversion_rate":      conversion_rate,
        "city_distribution":    city_dist,
        "segment_distribution": seg_dist,
        "status_distribution":  status_dist,
        "recent_leads":         recent,
        "top_leads":            top_leads,
    }


@dashboard_router.post("/seed-mock-data")
async def seed_mock_data():
    """No-op stub — mock data seeding is disabled. Returns success for frontend compatibility."""
    return {"message": "Seed skipped (disabled)", "count": 0}


# @dashboard_router.post("/seed-mock-data")
# async def seed_mock_data():
#     async with AsyncSessionLocal() as session:
#         count = (await session.execute(select(func.count()).select_from(Lead))).scalar() or 0
#     if count > 0:
#         return {"message": f"Already has {count} leads", "count": count}

#     mock_leads = [
#         {"business_name": "The Taj Mahal Palace", "segment": "Hotel", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Apollo Bunder, Colaba, Mumbai", "phone": "+91-22-6665-3366", "email": "fbprocurement@tajhotels.com", "website": "www.tajhotels.com", "rating": 4.8, "num_outlets": 12, "has_dessert_menu": True, "hotel_category": "5-star", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "800-1200 kg", "_dm": {"name": "Rakesh Nair", "role": "F&B Procurement Director", "linkedin_url": "linkedin.com/in/rakesh-nair-taj"}},
#         {"business_name": "Grand Hyatt Mumbai", "segment": "Hotel", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Santacruz East, Mumbai", "phone": "+91-22-6676-1234", "email": "procurement@grandhyattmumbai.com", "website": "www.grandhyatt.com", "rating": 4.6, "num_outlets": 2, "has_dessert_menu": True, "hotel_category": "5-star", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "600-800 kg", "_dm": {"name": "Priya Sharma", "role": "Purchase Manager", "linkedin_url": "linkedin.com/in/priya-sharma-hyatt"}},
#         {"business_name": "Monginis Cake Shop Chain", "segment": "Bakery", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Multiple locations, Mumbai", "phone": "+91-22-2376-5678", "email": "procurement@monginis.net", "website": "www.monginis.net", "rating": 4.2, "num_outlets": 230, "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "5000-8000 kg", "_dm": {"name": "Suhail Khorakiwala", "role": "Procurement Head", "linkedin_url": "linkedin.com/in/khorakiwala-monginis"}},
#         {"business_name": "La Folie Patisserie", "segment": "Bakery", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Khar West, Mumbai", "phone": "+91-22-6503-4567", "email": "hello@lafolie.in", "website": "www.lafolie.in", "rating": 4.7, "num_outlets": 6, "has_dessert_menu": True, "hotel_category": "", "is_chain": False, "source": "mock_data", "monthly_volume_estimate": "300-500 kg", "_dm": {"name": "Sanjana Patel", "role": "Owner & Head Pastry Chef", "linkedin_url": "linkedin.com/in/sanjana-lafolie"}},
#         {"business_name": "Natural Ice Cream", "segment": "IceCream", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Juhu, Mumbai", "phone": "+91-22-2618-3456", "email": "supply@naturals.in", "website": "www.naturals.in", "rating": 4.5, "num_outlets": 135, "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "3000-5000 kg", "_dm": {"name": "Raghunandan Kamath", "role": "Owner", "linkedin_url": "linkedin.com/in/naturals-kamath"}},
#         {"business_name": "Kailash Parbat Mithai", "segment": "Mithai", "city": "Mumbai", "state": "Maharashtra", "tier": 1, "address": "Colaba, Mumbai", "phone": "+91-22-2202-9456", "email": "orders@kailashparbat.com", "website": "www.kailashparbat.in", "rating": 4.3, "num_outlets": 22, "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "1500-2500 kg", "_dm": {"name": "Vijay Gidwani", "role": "Purchase Manager", "linkedin_url": "linkedin.com/in/kailash-parbat"}},
#         {"business_name": "The Leela Palace Delhi", "segment": "Hotel", "city": "Delhi", "state": "Delhi", "tier": 1, "address": "Diplomatic Enclave, Chanakyapuri", "phone": "+91-11-3933-1234", "email": "procurement@theleela.com", "website": "www.theleela.com", "rating": 4.8, "num_outlets": 8, "has_dessert_menu": True, "hotel_category": "5-star", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "700-1000 kg", "_dm": {"name": "Vikram Nair", "role": "F&B Procurement Head", "linkedin_url": "linkedin.com/in/vikram-nair-leela"}},
#         {"business_name": "Haldiram's Delhi", "segment": "Mithai", "city": "Delhi", "state": "Delhi", "tier": 1, "address": "Lajpat Nagar, Delhi", "phone": "+91-11-2921-5678", "email": "supply@haldirams.com", "website": "www.haldirams.com", "rating": 4.4, "num_outlets": 150, "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "10000-20000 kg", "_dm": {"name": "Procurement Director", "role": "Procurement Director", "linkedin_url": ""}},
#         {"business_name": "ITC Windsor Bengaluru", "segment": "Hotel", "city": "Bangalore", "state": "Karnataka", "tier": 1, "address": "Windsor Square, Golf Course Road, Bangalore", "phone": "+91-80-2226-9898", "email": "windsor.procurement@itchotels.in", "website": "www.itchotels.in", "rating": 4.7, "num_outlets": 4, "has_dessert_menu": True, "hotel_category": "5-star", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "500-800 kg", "_dm": {"name": "Sanjay Menon", "role": "F&B Manager", "linkedin_url": "linkedin.com/in/sanjay-itcwindsor"}},
#         {"business_name": "Havmor Ice Cream", "segment": "IceCream", "city": "Ahmedabad", "state": "Gujarat", "tier": 2, "address": "CG Road, Ahmedabad", "phone": "+91-79-2640-1234", "email": "supply@havmor.com", "website": "www.havmor.com", "rating": 4.2, "num_outlets": 200, "has_dessert_menu": True, "hotel_category": "", "is_chain": True, "source": "mock_data", "monthly_volume_estimate": "4000-7000 kg", "_dm": {"name": "Ankit Chona", "role": "MD & CEO", "linkedin_url": "linkedin.com/in/ankit-chona-havmor"}},
#     ]

#     async with AsyncSessionLocal() as session:
#         statuses = ["new", "new", "new", "contacted", "contacted", "qualified", "converted", "lost"]
#         created  = 0
#         for i, lead_data in enumerate(mock_leads):
#             dm_data  = lead_data.pop("_dm", None)
#             score, priority, reasoning = calculate_lead_score(lead_data)
#             status   = statuses[i % len(statuses)]
#             days_ago = random.randint(0, 45)
#             ts       = datetime.now(timezone.utc) - timedelta(days=days_ago)
#             lead_id  = str(uuid.uuid4())
#             doc = {
#                 "id": lead_id, **lead_data,
#                 "ai_score": score, "ai_reasoning": reasoning,
#                 "priority": priority, "status": status,
#                 "created_at": ts, "updated_at": ts,
#             }
#             session.add(Lead(**doc))
#             if dm_data and dm_data.get("name"):
#                 session.add(Contact(
#                     lead_id      = lead_id,
#                     name         = dm_data["name"],
#                     role         = dm_data.get("role", ""),
#                     linkedin_url = dm_data.get("linkedin_url", ""),
#                     confidence_score = 1.0,
#                     source       = "mock_data",
#                     is_primary   = True,
#                 ))
#             created += 1
#         await session.commit()
#         return {"message": f"Seeded {created} HORECA leads", "count": created}
