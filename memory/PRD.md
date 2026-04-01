# Dhampur Green HORECA Lead Intelligence — PRD

## Original Problem Statement
Build an AI tool that generates qualified HORECA leads (Hotels, Restaurants, Cafés) for Dhampur Green. The system needs to identify buyers, filter them based on buying potential, enrich contact data, score/prioritize them, and automate outreach.

## Product Requirements
- Search sources: Google Maps, Zomato, LinkedIn
- Target segments: Premium restaurants, Cafe chains, 3-5 star hotels, cloud kitchens
- AI Qualification: GPT-based filtering/scoring (consumption prediction, menu analysis)
- Contact Enrichment: Fetching emails and phone numbers
- Automated Outreach: Generating personalized sales emails

## User Choices
- Database: PostgreSQL (migrated from MongoDB)
- Google Maps API: Key provided (AIzaSyCTezHN6pNhF7oE6uHyJisG5dxZh7BngAY) — billing not enabled on GCP project, falls back to AI simulation
- Zomato: Skip for now, use AI-generated simulation instead
- LLM: OpenAI gpt-5.2 via Emergent LLM Key

## Tech Stack
- Frontend: React, TailwindCSS, Shadcn UI, Recharts
- Backend: FastAPI, PostgreSQL (asyncpg + SQLAlchemy async)
- AI: OpenAI GPT-5.2 via Emergent LLM Key (sk-emergent-dB4291cA8D13c5641F)
- Design: Forest green (#143628) + terracotta (#B85C38) palette

## Architecture
```
/app/
├── backend/
│   ├── .env (MONGO_URL, DB_NAME, DATABASE_URL, EMERGENT_LLM_KEY, GOOGLE_MAPS_API_KEY, CORS_ORIGINS)
│   ├── requirements.txt
│   ├── server.py (FastAPI main router - all routes)
│   ├── database.py (PostgreSQL SQLAlchemy async connection)
│   └── models.py (SQLAlchemy ORM models: Lead, OutreachEmail)
├── frontend/
│   ├── .env (REACT_APP_BACKEND_URL)
│   ├── package.json
│   └── src/
│       ├── App.js & App.css
│       ├── components/ (Sidebar, Layout, ui/)
│       └── pages/ (Dashboard, LeadDiscovery, LeadDatabase, LeadDetail, OutreachCenter)
```

## DB Schema
- **Lead**: id, business_name, segment, city, state, tier, address, phone, email, website, rating, num_outlets, decision_maker_name, decision_maker_role, decision_maker_linkedin, has_dessert_menu, hotel_category, is_chain, ai_score, ai_reasoning, priority, status, source, monthly_volume_estimate, created_at, updated_at
- **OutreachEmail**: id, lead_id, lead_name, lead_city, lead_segment, subject, body, status, generated_at, sent_at

## Key API Endpoints
- GET /api/dashboard/stats
- GET /api/leads (with filters: city, segment, priority, status, min_score, search)
- POST /api/leads (manual create)
- POST /api/leads/discover (AI-powered discovery: Google Maps + simulation)
- POST /api/leads/bulk-create
- POST /api/leads/upload-csv
- GET /api/leads/csv-template
- GET /api/leads/{id}
- PUT /api/leads/{id}/status
- DELETE /api/leads/{id}
- POST /api/leads/{id}/qualify-ai (GPT AI qualification)
- POST /api/leads/{id}/generate-email (GPT email generation)
- GET /api/outreach/emails
- GET /api/outreach/{lead_id}/emails
- PUT /api/outreach/{email_id}/mark-sent
- POST /api/seed-mock-data

## What's Been Implemented

### Session 1 (Initial Build)
- React frontend with 5 pages: Dashboard, LeadDiscovery, LeadDatabase, LeadDetail, OutreachCenter
- FastAPI backend with MongoDB
- 100% E2E tests passing on MongoDB version
- Deployment readiness check passed

### Session 2 (PostgreSQL Migration + Enhancement) — Feb 2026
- Migrated from MongoDB to PostgreSQL (local postgres, asyncpg, SQLAlchemy async)
- Fixed PostgreSQL auth error (set postgres user password in .env)
- Google Maps API integrated (legacy Places API attempted, falls back to AI simulation due to billing not enabled)
- Enhanced lead discovery simulation: 8 varied results per search across 8 segment types (up from 2-3)
- Added monthly volume estimates to simulated leads
- Updated source badge from "Swiggy" to "AI Generated"
- 30 realistic mock HORECA leads seeded across major Indian cities
- AI Qualification (GPT-5.2) via Emergent LLM Key — live on Lead Detail page
- AI Email Generation (GPT-5.2) — live on Lead Detail + Outreach Center
- Backend tests: 16/16 passing
- Frontend tests: 100% all flows working

## Scoring Engine
- 5-star hotel: +30, 4-star: +20, 3-star: +10
- Segment scores: Bakery +25, Mithai +22, IceCream +20, Cafe +20, CloudKitchen/Catering +18, Restaurant +15, Hotel +12
- Chain: +15, Outlets 10+: +15, Outlets 3+: +10
- Rating 4.5+: +10, 4.0+: +7
- Metro city: +10, Tier 2: +5
- Dessert menu: +15, LinkedIn decision maker: +10
- High priority ≥70, Medium ≥40, Low <40

## Prioritized Backlog

### P0 — Critical
- None (all P0 items resolved)

### P1 — High Priority
- Contact Enrichment: Fetch verified emails/phone numbers for discovered leads
- LinkedIn decision maker enrichment (profile scraping or manual)

### P2 — Medium Priority
- Consumption Prediction Model (estimate monthly sugar kg based on segment/outlets/rating)
- Smart Territory Mapping (cluster leads by city on map view)
- Competitor Detection (scan menus for organic sugar, brown sugar competitors)
- Bulk AI Qualification (qualify all leads in DB at once)

### P3 — Future/Backlog
- Real Google Maps data (requires user to enable billing + Places API on GCP)
- Zomato scraping integration
- LinkedIn API integration
- Email sending integration (SMTP/SendGrid)
- WhatsApp/SMS outreach templates
- Lead scoring v2 with more signals
- Export leads to CRM (Salesforce/HubSpot)

## Test Infrastructure
- Backend tests: /app/backend/tests/test_horeca_leads.py
- Test reports: /app/test_reports/iteration_*.json
- No authentication required for any endpoint
