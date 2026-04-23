"""
app/services/filtering/kpi_service.py
─────────────────────────────────────────────────────────────────────────────
Stage 3 — KPI Filtering.

Scores every AI-enriched business on a 100-point composite KPI and rejects
those below the minimum threshold (20).

KPI formula weights:
  sugar_consumption  0.20  | sweetness_dependency  0.15 | dessert_menu  0.15
  sugar_highlights   0.10  | segment_weight        0.10 | outlet_count  0.10
  rating             0.10  | review_strength       0.10 | hotel_cat     0.05
  is_chain           0.05

Note: This is a *pipeline* KPI score written to `kpi_score` / `priority` on
the business dict. It differs from `app/utils/scoring.calculate_lead_score`,
which is a simpler formula used for manual lead scoring in the API layer.

This is the clean, modular replacement for the inline apply_kpi_filtering()
and _compute_kpi_score() functions in stages.py. stages.py delegates to this
service.
─────────────────────────────────────────────────────────────────────────────
"""
import logging

from app.core.constants import SEGMENT_WEIGHTS

logger = logging.getLogger(__name__)

# Leads below this score are dropped from the pipeline.
MIN_KPI_SCORE = 20.0


def compute_kpi_score(biz: dict) -> tuple[float, str, str]:
    """
    Compute the composite KPI score for a single business dict.

    Args:
        biz: Business dict with AI-derived fields from Stage 2.

    Returns:
        (score, priority, reasoning) where:
          score     — float 0–100
          priority  — "High" | "Medium" | "Low"
          reasoning — human-readable string summarising the top signals
    """
    score, reasons = 0.0, []

    # ── Sugar consumption volume (20 %) ──────────────────────────────────────
    sugar_kg   = float(biz.get("monthly_sugar_estimate_kg", 0) or 0)
    sugar_norm = min(sugar_kg / 1000.0, 1.0) * 100
    score     += sugar_norm * 0.20
    reasons.append(f"Sugar ~{sugar_kg} kg/month")

    # ── Sweetness dependency (15 %) ───────────────────────────────────────────
    sweet  = float(biz.get("sweetness_dependency_pct", 0) or 0)
    score += sweet * 0.15
    if sweet > 50:
        reasons.append(f"Sweetness dependency {sweet}%")

    # ── Dessert menu (15 %) ───────────────────────────────────────────────────
    if biz.get("has_dessert_menu"):
        score += 15
        reasons.append("Has dessert menu")

    # ── Sugar highlight signals (10 %) ────────────────────────────────────────
    if biz.get("sugar_signal_from_highlights"):
        score += 10
        signals = biz.get("highlight_sugar_signals", [])
        reasons.append(f"Highlight sugar signals: {', '.join(signals[:3])}")

    # ── Segment weight (10 %) ─────────────────────────────────────────────────
    seg_w  = SEGMENT_WEIGHTS.get(biz.get("segment", "Restaurant"), 50)
    score += seg_w * 0.10
    reasons.append(f"Segment {biz.get('segment')} (w={seg_w})")

    # ── Outlet count (10 %) ───────────────────────────────────────────────────
    outlets    = int(biz.get("num_outlets", 1) or 1)
    outlet_scr = min(outlets * 5, 100)
    score     += outlet_scr * 0.10
    if outlets > 5:
        reasons.append(f"{outlets} outlets")

    # ── Rating (10 %) ────────────────────────────────────────────────────────
    rating = float(biz.get("rating", 0) or 0)
    score += min((rating / 5.0) * 100, 100) * 0.10

    # ── Review strength (10 %) ───────────────────────────────────────────────
    reviews = int(biz.get("reviews_count", 0) or 0)
    score  += min((reviews / 500.0) * 100, 100) * 0.10
    if reviews > 100:
        reasons.append(f"{reviews} reviews")

    # ── Hotel category (5 %) ─────────────────────────────────────────────────
    hotel_cat_scores = {"5-star": 100, "4-star": 75, "3-star": 50}
    score += hotel_cat_scores.get(biz.get("hotel_category", ""), 0) * 0.05

    # ── Chain bonus (5 %) ────────────────────────────────────────────────────
    if biz.get("is_chain"):
        score += 5
        reasons.append("Chain business")

    score    = round(min(score, 100), 2)
    priority = "High" if score >= 65 else ("Medium" if score >= 35 else "Low")
    return score, priority, " | ".join(reasons) or "Low data quality"



# ── START ────────────────────────────────────────────────────────
async def filter_by_kpi(ai_data: list[dict]) -> list[dict]:
    """
    Score every business, attach kpi_score / priority / ai_reasoning, and
    discard those below MIN_KPI_SCORE (pipeline wrapper).

    Args:
        ai_data: List of AI-enriched business dicts from Stage 2.

    Returns:
        Filtered list of businesses that passed the KPI threshold.
    """
    filtered = []

    for biz in ai_data:
        kpi, priority, reasoning = compute_kpi_score(biz)
        biz["kpi_score"]    = kpi
        biz["priority"]     = priority
        biz["ai_reasoning"] = reasoning

        if kpi < MIN_KPI_SCORE:
            logger.info(f"[KPI] Rejected '{biz.get('business_name')}' (score={kpi})")
            continue
        filtered.append(biz)

    logger.info(
        f"[KPI] {len(filtered)}/{len(ai_data)} passed KPI filter "
        f"(threshold={MIN_KPI_SCORE})"
    )
    return filtered
