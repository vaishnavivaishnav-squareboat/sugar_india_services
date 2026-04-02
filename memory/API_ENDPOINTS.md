# API Endpoints — Dhampur Green HORECA Lead Intelligence

> **Stack:** FastAPI · PostgreSQL (asyncpg + SQLAlchemy async) · GPT-5.2 via `emergentintegrations`  
> **Base URL:** `http://localhost:8001/api`  
> **Auth:** None — internal tool only.  
> **DB tables:** `leads`, `outreach_emails`

---

## General

### `GET /`
Health check / welcome message.  
**Response:** `{ "message": "Dhampur Green HORECA Lead Intelligence API v1.0" }`

---

## Dashboard

### `GET /dashboard/stats`
Executes **7 separate async DB queries** in a single request and returns all KPI data needed to render the Dashboard page.

**What it queries:**

| Query | Logic |
|---|---|
| `total_leads` | `COUNT(*)` on `leads` table |
| `high_priority` | `COUNT(*)` where `priority = 'High'` |
| `new_this_week` | `COUNT(*)` where `created_at >= now - 7 days` (ISO string comparison) |
| `converted` | `COUNT(*)` where `status = 'converted'` |
| `conversion_rate` | `(converted / total_leads) * 100`, rounded to 1 decimal; 0 if no leads |
| `city_distribution` | `GROUP BY city ORDER BY count DESC LIMIT 8` → `[{ city, count }]` |
| `segment_distribution` | `GROUP BY segment ORDER BY count DESC` → `[{ segment, count }]` |
| `status_distribution` | `GROUP BY status` → `[{ status, count }]` |
| `recent_leads` | Last 6 leads by `created_at DESC` |
| `top_leads` | Top 5 leads by `ai_score DESC` |

**Response shape:**
```json
{
  "total_leads": 30,
  "high_priority": 12,
  "new_this_week": 5,
  "converted": 3,
  "conversion_rate": 10.0,
  "city_distribution": [{ "city": "Mumbai", "count": 8 }],
  "segment_distribution": [{ "segment": "Hotel", "count": 9 }],
  "status_distribution": [{ "status": "new", "count": 14 }],
  "recent_leads": [...],
  "top_leads": [...]
}
```

---

## Leads

### `GET /leads`
Returns a filtered, paginated list of leads sorted by `ai_score` descending. Runs two queries — one for the filtered results, one for the total count.

**Query params:**
| Param | Type | Filter logic |
|---|---|---|
| `city` | string | `ILIKE %city%` (partial, case-insensitive) |
| `segment` | string | Exact match |
| `priority` | string | Exact match: `High` / `Medium` / `Low` |
| `status` | string | Exact match: `new` / `contacted` / `qualified` / `converted` / `lost` |
| `min_score` | int | `ai_score >= min_score` |
| `search` | string | `ILIKE` across `business_name`, `city`, `decision_maker_name` (OR) |
| `limit` | int | Default `100` |
| `skip` | int | Offset for pagination, default `0` |

**Response:** `{ "leads": [...], "total": <int> }`

---

### `POST /leads`
Creates a single lead manually. The scoring engine (`calculate_lead_score`) runs automatically inside `make_lead_doc()` — **never send** `ai_score`, `priority`, or `ai_reasoning` from the frontend.

**Body — `LeadCreate` schema:**
| Field | Type | Default |
|---|---|---|
| `business_name` | string | *(required)* |
| `city` | string | *(required)* |
| `segment` | string | `"Restaurant"` |
| `state` | string | `""` |
| `tier` | int | `1` |
| `address` | string | `""` |
| `phone` | string | `""` |
| `email` | string | `""` |
| `website` | string | `""` |
| `rating` | float | `0.0` |
| `num_outlets` | int | `1` |
| `decision_maker_name` | string | `""` |
| `decision_maker_role` | string | `""` |
| `decision_maker_linkedin` | string | `""` |
| `has_dessert_menu` | bool | `false` |
| `hotel_category` | string | `""` — accepts `"3-star"` / `"4-star"` / `"5-star"` |
| `is_chain` | bool | `false` |
| `source` | string | `"manual"` |
| `monthly_volume_estimate` | string | `""` |

**Response:** The newly created lead document (all fields including computed `ai_score`, `priority`, `ai_reasoning`, `id`, `created_at`, `updated_at`).

---

### `GET /leads/{lead_id}`
Fetches a single lead by UUID.  
**Response:** Full lead document or `404`.

---

### `PUT /leads/{lead_id}/status`
Updates only the pipeline status of a lead and sets `updated_at` to now.

**Body:** `{ "status": "<new_status>" }`  
**Pipeline flow:** `new` → `contacted` → `qualified` → `converted` or `lost`  
**Response:** Full updated lead document or `404`.

---

### `DELETE /leads/{lead_id}`
Permanently removes a lead from the DB.  
**Response:** `{ "message": "Lead deleted" }` or `404`.

---

### `GET /leads/csv-template`
Returns a downloadable CSV file with the correct column headers and one pre-filled sample row. Use this before attempting a CSV upload to get the expected format.

**Response:** `text/csv` file download (`horeca_leads_template.csv`).

---

### `POST /leads/upload-csv`
Accepts a `multipart/form-data` CSV upload. Processes each row sequentially:

1. Decodes file as UTF-8 (with BOM stripping) — falls back to Latin-1.
2. Parses each row into a `lead_data` dict, coercing types (`int`, `float`, `bool`).
3. Skips rows missing `business_name` or `city` — records them in `errors`.
4. Calls `make_lead_doc()` on valid rows → runs scoring engine → saves to DB.
5. Commits all valid rows in a single transaction.

**Response:** `{ "created": <int>, "errors": ["Row N: reason", ...] }`

---

### `POST /leads/discover`
**Step 1 of 2 — Discovery (simulated, not persisted).**

> ⚠️ This endpoint does **not** call Google Maps, Zomato, or any external API. It generates plausible candidate leads from hardcoded templates.

**How it works:**
1. Receives `{ city, segment, state }`.
2. Determines `tier` (1 if the city is one of 8 metros, else 2).
3. Looks up a `templates_map[segment]` — a hardcoded list of attribute dicts per segment (hotel_category, rating, num_outlets, is_chain, has_dessert_menu).
4. Looks up `names_map[segment]` — hardcoded business name options.
5. For each template, assembles a full lead object: combines the template attributes with the user-supplied city/state/tier, a randomly generated phone number, fake email/website, and a randomly picked decision maker name + role.
6. Runs `calculate_lead_score()` on each → attaches `ai_score`, `priority`, `ai_reasoning`.
7. **Returns the array without saving anything.**

**Number of results returned = number of templates for the segment:**
| Segment | Results |
|---|---|
| Hotel | 3 |
| Restaurant | 3 |
| Bakery | 3 |
| Cafe | 2 |
| CloudKitchen | 2 |
| Catering | 2 |
| Mithai | 2 |
| IceCream | 2 |

**Body:** `{ "city": "Mumbai", "segment": "Bakery", "state": "Maharashtra" }`  
**Response:** Array of lead-shaped objects with pre-computed scores (not yet in DB).

---

### `POST /leads/bulk-create`
**Step 2 of 2 — Persist selected discovery results.**

Takes leads selected by the user from `/discover` and saves them to the DB. For each lead:
1. Strips `ai_score`, `ai_reasoning`, `priority` from the incoming dict (prevents client-side score manipulation).
2. Calls `make_lead_doc()` → re-runs the scoring engine fresh.
3. Saves to DB. All rows committed in a single transaction.

**Body:** `{ "leads": [ ...lead objects... ] }`  
**Response:** `{ "created": <int>, "leads": [...saved docs with new UUIDs] }`

---

## AI Actions

### `POST /leads/{lead_id}/qualify-ai`
Runs GPT-5.2 via `emergentintegrations.llm.chat.LlmChat` to deeply qualify a lead.

**Flow:**
1. Fetches the lead from DB.
2. Checks `EMERGENT_LLM_KEY` env var — returns `500` if missing.
3. Creates a unique LLM session (`qualify-{lead_id}-{uuid4}`).
4. Sends a structured prompt asking for raw JSON only (no markdown fences).
5. Strips any accidental ` ```json ``` ` wrapping, then `json.loads()`.
6. Updates the lead in DB: `ai_score`, `ai_reasoning` (from `qualification_summary`), `priority`, `monthly_volume_estimate`, `updated_at`.

**AI output fields used:**
| Field | Saved to DB? |
|---|---|
| `ai_score` | ✅ → `leads.ai_score` |
| `qualification_summary` | ✅ → `leads.ai_reasoning` |
| `priority` | ✅ → `leads.priority` |
| `monthly_volume_kg` | ✅ → `leads.monthly_volume_estimate` |
| `sugar_use_cases` | ❌ returned in response only |
| `key_insight` | ❌ returned in response only |
| `best_contact_time` | ❌ returned in response only |

**Response:** `{ "lead": <full updated lead>, "ai_analysis": { ...all AI fields... } }`  
**Errors:** `500` if LLM key missing or AI call/JSON parse fails.

---

### `POST /leads/{lead_id}/generate-email`
Generates a personalized B2B outreach email using GPT-5.2 and saves it as a draft.

**Flow:**
1. Fetches the lead from DB.
2. Checks `EMERGENT_LLM_KEY`.
3. Creates a unique LLM session (`email-{lead_id}-{uuid4}`).
4. Builds a prompt with business name, segment, city, decision maker, rating, outlets, dessert menu flag, hotel category, and monthly volume estimate.
5. Instructs the model to format the response with `SUBJECT:` on the first line, body below.
6. Parses the response: first `SUBJECT:` line → `subject`, remaining lines → `body`.
7. Saves email document to `outreach_emails` table with `status = "draft"`.

**Sign-off hardcoded in prompt:**  
`Arjun Mehta | Regional Sales Manager, Dhampur Green | +91-98765-43210 | arjun.mehta@dhampurgreen.com`

**Response:**
```json
{
  "id": "uuid",
  "lead_id": "uuid",
  "lead_name": "...",
  "lead_city": "...",
  "lead_segment": "...",
  "subject": "...",
  "body": "...",
  "status": "draft",
  "generated_at": "ISO timestamp"
}
```
**Errors:** `500` if LLM key missing or AI call fails.

---

## Outreach / Email History

### `GET /outreach/emails`
Returns the 50 most recently generated emails across **all leads**, sorted by `generated_at DESC`.  
**Response:** Array of `OutreachEmail` documents.

---

### `GET /outreach/{lead_id}/emails`
Returns up to 20 emails generated for a **specific lead**, sorted by `generated_at DESC`.  
**Response:** Array of `OutreachEmail` documents.

---

### `PUT /outreach/{email_id}/mark-sent`
Marks a draft email as sent. Sets `status = "sent"` and records `sent_at` as the current UTC timestamp.  
**Response:** Updated email document or `404`.

---

## Utilities

### `POST /seed-mock-data`
Seeds the database with **30 realistic HORECA leads** across 12 Indian cities and all 8 segments. **Idempotent** — if any leads already exist, it returns immediately without inserting anything.

**Cities covered:** Mumbai, Delhi, Bangalore, Hyderabad, Chennai, Pune, Kolkata, Jaipur, Ahmedabad, Lucknow, Surat, Chandigarh

**Segments covered:** Hotel, Bakery, IceCream, Mithai, Restaurant, CloudKitchen, Cafe, Catering

**What it does per lead:**
- Runs `calculate_lead_score()` to compute `ai_score`, `priority`, `ai_reasoning`.
- Assigns a status cycling through `["new", "new", "new", "new", "contacted", "contacted", "qualified", "converted", "lost"]`.
- Sets `created_at` / `updated_at` to a random time within the last 45 days.

**Response:** `{ "message": "Seeded 30 HORECA leads", "count": 30 }` or `{ "message": "Already has N leads", "count": N }`

---

## DB Schema Reference

### `leads` table
| Column | Type | Notes |
|---|---|---|
| `id` | String (UUID) | Primary key |
| `business_name` | String | |
| `segment` | String | Hotel / Restaurant / Cafe / Bakery / CloudKitchen / Catering / Mithai / IceCream |
| `city` | String | |
| `state` | String | |
| `tier` | Integer | 1 = Metro, 2 = Tier 2 |
| `address` | String | |
| `phone` | String | |
| `email` | String | |
| `website` | String | |
| `rating` | Float | |
| `num_outlets` | Integer | |
| `decision_maker_name` | String | |
| `decision_maker_role` | String | |
| `decision_maker_linkedin` | String | |
| `has_dessert_menu` | Boolean | |
| `hotel_category` | String | `""` / `"3-star"` / `"4-star"` / `"5-star"` |
| `is_chain` | Boolean | |
| `source` | String | `manual` / `csv_upload` / `api_discovery` / `mock_data` |
| `monthly_volume_estimate` | String | e.g. `"200-500 kg"` |
| `ai_score` | Integer | 0–100, auto-computed |
| `ai_reasoning` | Text | Pipe-separated scoring reasons or AI summary |
| `priority` | String | `High` / `Medium` / `Low` |
| `status` | String | `new` / `contacted` / `qualified` / `converted` / `lost` |
| `created_at` | String | ISO 8601 UTC |
| `updated_at` | String | ISO 8601 UTC |

### `outreach_emails` table
| Column | Type | Notes |
|---|---|---|
| `id` | String (UUID) | Primary key |
| `lead_id` | String | FK reference to `leads.id` (not enforced at DB level) |
| `lead_name` | String | Denormalised for display |
| `lead_city` | String | Denormalised for display |
| `lead_segment` | String | Denormalised for display |
| `subject` | String | Email subject line |
| `body` | Text | Full email body |
| `status` | String | `draft` / `sent` |
| `generated_at` | String | ISO 8601 UTC |
| `sent_at` | String (nullable) | ISO 8601 UTC, set by `/mark-sent` |

---

## Scoring Engine (`calculate_lead_score`)

Runs server-side only — never called from the frontend. Score is capped at 100.

| Condition | Points |
|---|---|
| 5-star hotel | +30 |
| 4-star hotel | +20 |
| 3-star hotel | +10 |
| Bakery segment | +25 |
| Mithai segment | +22 |
| IceCream / Cafe | +20 each |
| CloudKitchen / Catering | +18 each |
| Restaurant | +15 |
| Hotel (segment) | +12 |
| Is a chain | +15 |
| ≥ 10 outlets | +15 |
| ≥ 3 outlets | +10 |
| Rating ≥ 4.5 | +10 |
| Rating ≥ 4.0 | +7 |
| Tier 1 city | +10 |
| Tier 2 city | +5 |
| Has dessert menu | +15 |
| Decision maker on LinkedIn | +10 |

**Priority tiers:** `High` ≥ 70 · `Medium` 40–69 · `Low` < 40

`ai_reasoning` is a pipe-separated string of all triggered conditions, e.g.:  
`5-star hotel (+30) | Hotel segment (+12) | Chain business (+15) | Metro city (+10) | Has dessert/sweet menu (+15)`

### `POST /seed-mock-data`
Seeds the database with 30 realistic HORECA leads spanning 12 Indian cities (Mumbai, Delhi, Bangalore, Hyderabad, Chennai, Pune, Kolkata, Jaipur, Ahmedabad, Lucknow, Surat, Chandigarh). Covers all 8 segments. Idempotent — does nothing if any leads already exist.  
**Response:** `{ "message": "Seeded 30 HORECA leads", "count": 30 }` or `{ "message": "Already has N leads", "count": N }`.

---

## Scoring Engine (server-side only)

The `calculate_lead_score()` function runs automatically on every lead creation or bulk import. It is **never called from the frontend**. Score is capped at 100.

| Condition | Points |
|---|---|
| 5-star hotel | +30 |
| 4-star hotel | +20 |
| 3-star hotel | +10 |
| Bakery segment | +25 |
| Mithai segment | +22 |
| IceCream / Cafe | +20 each |
| CloudKitchen / Catering | +18 each |
| Restaurant | +15 |
| Hotel | +12 |
| Is a chain | +15 |
| ≥10 outlets | +15 |
| ≥3 outlets | +10 |
| Rating ≥4.5 | +10 |
| Rating ≥4.0 | +7 |
| Tier 1 city | +10 |
| Tier 2 city | +5 |
| Has dessert menu | +15 |
| Decision maker on LinkedIn | +10 |

**Priority tiers:** High ≥ 70 · Medium 40–69 · Low < 40
