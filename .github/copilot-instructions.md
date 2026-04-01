# Copilot Instructions — Dhampur Green HORECA Lead Intelligence Tool

## Project Overview
An internal B2B sales tool for Dhampur Green (premium Indian sugar/sweetener brand) to discover, score, qualify, and reach out to HORECA (Hotels, Restaurants, Cafés) buyers across India. See [`memory/PRD.md`](../memory/PRD.md) for the full product spec.

---

## Architecture

### Backend — `backend/server.py` (single-file FastAPI)
- **All** API routes, the scoring engine, and AI integration live in one file (`server.py`).
- **Database:** MongoDB (`dhampur_horeca` db, `leads` + `outreach_emails` collections) via `motor` (async).
- **AI:** `emergentintegrations.llm.chat.LlmChat` with model `openai/gpt-5.2`, keyed by `EMERGENT_LLM_KEY`. Each AI call uses a unique `session_id` (e.g. `f"qualify-{lead_id}-{uuid.uuid4()}"`).
- **Port:** 8001. CORS is configured via `CORS_ORIGINS` env var (default `*`).
- **No authentication** — internal tool only.

### Frontend — `frontend/src/`
- CRA + craco (`frontend/craco.config.js`). Start with `yarn start`.
- Routing: React Router v7, all routes defined in [`App.js`](../frontend/src/App.js). Layout shell is `components/Layout.jsx` (fixed sidebar + `<Outlet />`).
- Pages: `Dashboard`, `LeadDiscovery`, `LeadDatabase`, `LeadDetail`, `OutreachCenter`.
- UI: shadcn/ui (Radix UI primitives, pre-generated in `src/components/ui/`). Do **not** re-implement these components — use what's there.
- Charts: Recharts. API calls: axios.

---

## Critical Patterns

### Lead Documents (MongoDB)
- Use custom string `id` field (UUID), **not** MongoDB's `_id`. All queries filter on `{"id": lead_id}` and always project out `_id` with `{"_id": 0}`.
- `ai_score`, `ai_reasoning`, and `priority` are **computed automatically** by `calculate_lead_score()` in `make_lead_doc()` on every create. Never set these manually in the frontend.

### Scoring Engine (`calculate_lead_score` in `server.py`)
Priority tiers: **High** ≥70, **Medium** 40–69, **Low** <40. Key point weights:
- 5-star hotel: +30, Bakery: +25, Mithai: +22, IceCream/Cafe: +20
- Chain: +15, 10+ outlets: +15, has dessert menu: +15, decision maker on LinkedIn: +10
- Tier 1 city: +10, rating ≥4.5: +10

### Lead Discovery Flow (two-step, not one)
`POST /api/leads/discover` returns **simulated** candidates (not persisted). The user must then call `POST /api/leads/bulk-create` with selected leads to save them to the DB. Never combine these steps.

### AI Prompt Pattern
AI endpoints (`qualify-ai`, `generate-email`) always:
1. Fetch the lead from MongoDB first.
2. Construct a prompt that instructs the LLM to respond with **raw JSON only** (no markdown fences).
3. Strip any accidental ` ```json ``` ` wrapping before `json.loads()`.

### Lead Status Pipeline
`new → contacted → qualified → converted` or `lost`. Updated via `PUT /api/leads/{id}/status`.

---

## Dev Workflows

### Start Backend
```bash
cd backend
uvicorn server:app --reload --port 8001
```
Required env vars in `backend/.env`: `MONGO_URL`, `DB_NAME`, `EMERGENT_LLM_KEY`, `CORS_ORIGINS`.

### Start Frontend
```bash
cd frontend
yarn start   # runs on port 3000 via CRA/craco
```
Set `REACT_APP_BACKEND_URL=http://localhost:8001` in `frontend/.env`.

### Seed Mock Data (30 realistic HORECA leads)
```
POST http://localhost:8001/api/seed-mock-data
```
Idempotent — does nothing if leads already exist.

### Run Tests
```bash
cd backend
REACT_APP_BACKEND_URL=http://localhost:8001 pytest tests/ -v
```
Tests are HTTP integration tests (not unit tests) — the backend must be running with seeded data.

---

## Design System (do not deviate)
Source of truth: [`design_guidelines.json`](../design_guidelines.json).

| Token | Value |
|---|---|
| Primary (sidebar, buttons) | `#143628` (forest green) |
| Accent (high-priority CTAs) | `#B85C38` (terracotta/jaggery) |
| Background | `#F8F9F6` (off-white) |
| Heading font | Cabinet Grotesk / Plus Jakarta Sans |
| Body font | Figtree |
| Mono font | JetBrains Mono (email editor) |

- Cards: flat, `1px solid border-border`, no shadows by default; `shadow-sm` only on hover.
- Labels/overlines: `uppercase text-xs tracking-[0.2em]`.
- Never use blue/purple in charts — use `#143628`, `#8FA39A` (sage), `#B85C38` for data series.
- Sidebar is always dark green (`#143628`), fixed at 260px.

---

## Key Files Reference
| File | Purpose |
|---|---|
| `backend/server.py` | Entire backend: routes, scoring, AI, DB, seed data |
| `frontend/src/App.js` | All React routes |
| `frontend/src/components/Sidebar.jsx` | Navigation + brand identity |
| `frontend/src/components/Layout.jsx` | App shell (sidebar + outlet) |
| `frontend/src/pages/LeadDetail.jsx` | Bento-grid lead view + AI actions |
| `memory/PRD.md` | Full product spec, scoring algorithm, backlog |
| `design_guidelines.json` | Authoritative design tokens and rules |
| `backend/tests/test_horeca_leads.py` | Integration test suite |
