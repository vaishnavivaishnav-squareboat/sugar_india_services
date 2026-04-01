# PRD: Dhampur Green HORECA Lead Intelligence Tool

## Overview
An AI-powered internal B2B sales tool for Dhampur Green (premium sugar/sweetener brand) that identifies, qualifies, scores, and enables outreach to HORECA (Hotels, Restaurants, Cafés) buyers across India.

## Problem Statement
Dhampur Green's sales team needs a systematic way to:
1. Discover HORECA businesses that consume sugar/jaggery at scale
2. Qualify and score them by buying potential
3. Enrich contact data for decision makers
4. Generate personalized AI sales emails
5. Track lead pipeline status

## Architecture

### Backend (FastAPI + MongoDB)
- `server.py` — All API routes, scoring engine, AI integration
- DB: `dhampur_horeca` (MongoDB)
- AI: OpenAI GPT-5.2 via emergentintegrations + EMERGENT_LLM_KEY
- Port: 8001

### Frontend (React + Tailwind + shadcn)
- `App.js` — React Router v7 routing
- `pages/Dashboard.jsx` — KPI cards + recharts bar/donut charts
- `pages/LeadDiscovery.jsx` — 3-tab discovery (API/CSV/Manual)
- `pages/LeadDatabase.jsx` — Filterable sortable leads table
- `pages/LeadDetail.jsx` — Bento grid, AI score gauge, email gen
- `pages/OutreachCenter.jsx` — Email generation + history center
- `components/Sidebar.jsx` — Dark green fixed navigation

### Design
- Theme: Earthy/Organic — Primary #143628 (forest green), Accent #B85C38 (jaggery/terracotta)
- Fonts: Plus Jakarta Sans (headings), Figtree (body), JetBrains Mono (email editor)
- Light background: #F8F9F6

## User Personas
- **Arjun Mehta** — Regional Sales Manager (primary user)
- **Sales Team** — Field reps who use lead database and send emails

## Core Requirements (Static)
1. HORECA lead discovery (simulated API + CSV upload + manual)
2. Rule-based + AI lead scoring (0-100)
3. Priority tiers: High (≥70), Medium (40-69), Low (<40)
4. AI lead qualification with GPT-5.2 (sugar use cases, volume estimate)
5. AI-personalized email generation per lead
6. Lead status pipeline tracking (new → contacted → qualified → converted/lost)
7. Dashboard with KPIs and charts
8. Pan-India coverage (Tier 1 + Tier 2 cities)

## Scoring Algorithm
- 5-star hotel: +30, 4-star: +20, 3-star: +10
- Bakery: +25, Mithai: +22, IceCream: +20, Cafe: +20
- CloudKitchen/Catering: +18, Restaurant: +15, Hotel: +12
- Chain: +15, 10+ outlets: +15, 3+ outlets: +10
- Rating ≥4.5: +10, ≥4.0: +7
- Tier 1 city: +10, Tier 2: +5
- Has dessert menu: +15
- Decision maker on LinkedIn: +10

## What's Been Implemented (Date: Feb 2026)
- [x] Full backend API (FastAPI) with 15+ endpoints
- [x] 30 realistic seeded mock HORECA leads across 12 Indian cities
- [x] Lead CRUD (create, read, update status, delete)
- [x] CSV upload & template download
- [x] Simulated API discovery (Google Maps/Zomato mock)
- [x] Bulk lead creation
- [x] AI lead qualification (GPT-5.2)
- [x] AI email generation (GPT-5.2)
- [x] Dashboard with KPI cards + recharts charts
- [x] Lead Database with full filtering & sorting
- [x] Lead Detail page with bento grid layout
- [x] Outreach Center with email history
- [x] Design: earthy green brand theme applied

## Mocked/Simulated
- Lead discovery API (/api/leads/discover) returns **simulated** results (not real Google Maps/Zomato)
- Real API integrations planned for Phase 2

## Backlog / Next Tasks

### P0 (Must-have next)
- [ ] Real Google Maps API integration for lead discovery
- [ ] Real Zomato/Swiggy API integration
- [ ] Export leads to CSV/Excel

### P1 (Important)
- [ ] LinkedIn scraping for decision maker enrichment
- [ ] Hunter.io/Apollo integration for email verification
- [ ] WhatsApp outreach draft generation
- [ ] Territory/region assignment to sales reps

### P2 (Nice to have)
- [ ] Consumption prediction model (hotel size × menu × reviews)
- [ ] Competitor detection (organic/imported sugar on menu)
- [ ] Region-wise map visualization (city clustering)
- [ ] Email sequence automation (drip campaigns)
- [ ] CRM push (Zoho/Salesforce integration)
- [ ] Duplicate lead detection
- [ ] Force re-seed option for fresh data
