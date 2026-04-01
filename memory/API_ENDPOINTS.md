# API Endpoints — Dhampur Green HORECA Lead Intelligence

Base URL: `http://localhost:8001/api`

---

## General

### `GET /`
Health check / welcome message.  
**Response:** `{ "message": "Dhampur Green HORECA Lead Intelligence API v1.0" }`

---

## Dashboard

### `GET /dashboard/stats`
Returns all KPI data needed to render the Dashboard page in one call.

| Field | Description |
|---|---|
| `total_leads` | Total number of leads in the database |
| `high_priority` | Count of leads with priority = "High" (score ≥ 70) |
| `new_this_week` | Leads created in the last 7 days |
| `converted` | Count of leads with status = "converted" |
| `conversion_rate` | `(converted / total) * 100`, rounded to 1 decimal |
| `city_distribution` | Top 8 cities by lead count `[{ city, count }]` |
| `segment_distribution` | All segments by lead count `[{ segment, count }]` |
| `status_distribution` | All statuses by count `[{ status, count }]` |
| `recent_leads` | Last 6 leads added (sorted by `created_at` desc) |
| `top_leads` | Top 5 leads by `ai_score` |

---

## Leads

### `GET /leads`
Returns a filtered, paginated list of leads sorted by `ai_score` descending.

**Query params:**
| Param | Type | Description |
|---|---|---|
| `city` | string | Partial match on city name |
| `segment` | string | Exact match (e.g. `Hotel`, `Bakery`) |
| `priority` | string | `High` / `Medium` / `Low` |
| `status` | string | `new` / `contacted` / `qualified` / `converted` / `lost` |
| `min_score` | int | Minimum `ai_score` |
| `search` | string | Searches `business_name`, `city`, `decision_maker_name` |
| `limit` | int | Max results (default 100) |
| `skip` | int | Offset for pagination (default 0) |

**Response:** `{ "leads": [...], "total": <int> }`

---

### `POST /leads`
Creates a single lead manually. Automatically runs the scoring engine on creation — `ai_score`, `priority`, and `ai_reasoning` are computed server-side and must not be sent in the request.

**Body:** `LeadCreate` schema (see below).  
**Response:** The newly created lead document.

#### LeadCreate fields
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
| `hotel_category` | string | `""` (`"3-star"` / `"4-star"` / `"5-star"`) |
| `is_chain` | bool | `false` |
| `source` | string | `"manual"` |
| `monthly_volume_estimate` | string | `""` |

---

### `GET /leads/{lead_id}`
Fetches a single lead by its UUID `id`.  
**Response:** Full lead document or `404`.

---

### `PUT /leads/{lead_id}/status`
Updates the pipeline status of a lead.

**Body:** `{ "status": "<new_status>" }`  
**Valid values:** `new` → `contacted` → `qualified` → `converted` or `lost`  
**Response:** Updated lead document.

---

### `DELETE /leads/{lead_id}`
Permanently deletes a lead by its UUID.  
**Response:** `{ "message": "Lead deleted" }` or `404`.

---

### `GET /leads/csv-template`
Downloads a pre-filled CSV template file that shows the correct column headers and one sample row, so users know the expected format for CSV uploads.  
**Response:** `text/csv` file attachment.

---

### `POST /leads/upload-csv`
Accepts a multipart CSV file upload. Each row is parsed, validated, and saved as a new lead. The scoring engine runs on every row automatically.

- Skips rows missing `business_name` or `city` and records them as errors.
- Supports UTF-8 and Latin-1 encoded files.

**Response:** `{ "created": <int>, "errors": ["Row N: reason", ...] }`

---

### `POST /leads/discover`
**Step 1 of 2** in the discovery flow. Returns a list of *simulated* candidate leads for a given city + segment combination. Results are **not saved** to the database — they are returned to the frontend for the user to review and select.

**Body:**
```json
{ "city": "Mumbai", "segment": "Bakery", "state": "Maharashtra" }
```
**Response:** Array of lead-shaped objects with pre-computed `ai_score`, `priority`, and `ai_reasoning`.

---

### `POST /leads/bulk-create`
**Step 2 of 2** in the discovery flow. Takes the user-selected candidates from `/discover` and persists them to the database. Strips any incoming `ai_score` / `ai_reasoning` / `priority` and re-runs the scoring engine from scratch on each lead.

**Body:** `{ "leads": [ ...lead objects... ] }`  
**Response:** `{ "created": <int>, "leads": [...saved docs] }`

---

## AI Actions

### `POST /leads/{lead_id}/qualify-ai`
Runs GPT-5.2 (via `emergentintegrations`) to deeply qualify a lead. The AI analyzes the business profile and estimates:
- Revised `ai_score` (0–100)
- Monthly sugar volume estimate (e.g. `"200-500 kg"`)
- 2–3 sentence qualification summary
- Sugar use cases specific to the segment
- One actionable sales insight
- Best time to contact

After the AI responds, the lead's `ai_score`, `ai_reasoning`, `priority`, and `monthly_volume_estimate` are **updated in the database**.

**Response:** `{ "lead": <updated lead>, "ai_analysis": { ...full AI output... } }`

---

### `POST /leads/{lead_id}/generate-email`
Generates a personalized B2B outreach email for a lead using GPT-5.2. The prompt includes business name, segment, decision maker name/role, rating, and volume estimate. The email is saved to the `outreach_emails` table as a `"draft"`.

**Response:** The saved email document:
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

---

## Outreach / Email History

### `GET /outreach/emails`
Returns up to 50 most recently generated emails across **all leads**, sorted newest first.  
**Response:** Array of email documents.

---

### `GET /outreach/{lead_id}/emails`
Returns up to 20 most recent emails generated for a **specific lead**, sorted newest first.  
**Response:** Array of email documents.

---

### `PUT /outreach/{email_id}/mark-sent`
Marks a draft email as sent. Sets `status = "sent"` and records `sent_at` timestamp.  
**Response:** Updated email document or `404`.

---

## Utilities

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
