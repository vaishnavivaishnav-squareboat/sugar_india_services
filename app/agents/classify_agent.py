"""
app/agents/classify_agent.py
─────────────────────────────────────────────────────────────────────────────
Stage 2 — Business Intelligence Agent (self-contained)

Single file for the full classify flow:
  • classify_business  — @function_tool: typed schema the agent must fill in
  • business_intelligence_agent — Agent with reasoning instructions
  • classify_business_runner(biz) → dict — async entry point for the pipeline

Usage:
    from app.agents.classify_agent import classify_business_runner
    analysis = await classify_business_runner(biz_dict)
─────────────────────────────────────────────────────────────────────────────
"""
import json
import logging
from typing import Annotated, Literal

from agents import Agent, Runner, function_tool
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

from app.core.config import OPENAI_MODEL
from app.core.constants import roles as ROLES
from app.utils.agent_flow import extract_agent_chain, log_agent_flow

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# TOOL — structured output schema the agent must call with its analysis
# ══════════════════════════════════════════════════════════════════════════════

@function_tool
def classify_business(
    has_dessert_menu: Annotated[
        bool,
        "Whether the business sells desserts, sweets, baked goods or any sugar-heavy items",
    ],
    sugar_items_count: Annotated[
        int,
        "Estimated number of distinct menu items that require sugar",
    ],
    menu_categories: Annotated[
        list[str],
        "Main menu categories this business offers (e.g. Cakes, Pastries, Ice Cream, Beverages)",
    ],
    avg_price_range: Annotated[
        Literal["budget", "mid-range", "premium"],
        "Overall price positioning of the establishment",
    ],
    business_classification: Annotated[
        Literal[
            "Hotel", "Restaurant", "Cafe", "Bakery", "Catering",
            "IceCream", "Mithai", "CloudKitchen", "Beverage",
            "FoodProcessing", "Organic", "Brewery",
        ],
        "Corrected HORECA segment for this business",
    ],
    is_chain: Annotated[bool, "Whether this business operates multiple outlets"],
    hotel_category: Annotated[
        str,
        "Star rating for hotels: '3-star', '4-star', '5-star', or empty string if not a hotel",
    ],
    monthly_sugar_estimate_kg: Annotated[
        int,
        "Estimated kilograms of sugar this business consumes per month",
    ],
    sweetness_dependency_pct: Annotated[
        int,
        "Percentage (0–100) of the menu that depends on sugar/sweeteners",
    ],
    sugar_signal_from_highlights: Annotated[
        bool,
        "Whether Google Maps highlights explicitly mention dessert / sugar-related keywords",
    ],
    highlight_sugar_signals: Annotated[
        list[str],
        "Exact highlight / description keywords that indicate sugar usage",
    ],
    ai_reasoning: Annotated[
        str,
        (
            "Detailed reasoning (4–6 sentences) that MUST cover: "
            "(a) which exact highlights, tags, or name signals triggered the dessert/sugar flag; "
            "(b) how scale signals (outlet count, reviews volume, chain status) informed the monthly volume estimate; "
            "(c) what segment cues (name, description, types) determined or corrected the classification; "
            "(d) any price-range or location signals factored into the estimate; "
            "(e) the confidence level in the estimate and any caveats."
        ),
    ],
) -> str:
    """
    Records the complete sugar-intelligence analysis for a HORECA business.
    Call this once you have evaluated all business details — highlights, description,
    segment, rating, etc. Provide your full assessment of the business's sugar
    consumption potential.
    """
    analysis = {
        "has_dessert_menu":             has_dessert_menu,
        "sugar_items_count":            sugar_items_count,
        "menu_categories":              menu_categories,
        "avg_price_range":              avg_price_range,
        "business_classification":      business_classification,
        "is_chain":                     is_chain,
        "hotel_category":               hotel_category,
        "monthly_sugar_estimate_kg":    monthly_sugar_estimate_kg,
        "sweetness_dependency_pct":     sweetness_dependency_pct,
        "sugar_signal_from_highlights": sugar_signal_from_highlights,
        "highlight_sugar_signals":      highlight_sugar_signals,
        "ai_reasoning":                 ai_reasoning,
    }
    logger.info(
        f"[classify_business] 🍬 '{business_classification}' — "
        f"sugar ~{monthly_sugar_estimate_kg} kg/mo, dessert={has_dessert_menu}"
    )
    return json.dumps(analysis)


# ══════════════════════════════════════════════════════════════════════════════
# AGENT — reasoning instructions + tool binding
# ══════════════════════════════════════════════════════════════════════════════

business_intelligence_agent = Agent(
    name="Business Intelligence Agent",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
You are a senior HORECA business intelligence analyst for Dhampur Green, India's premium sugar brand.
Your role is to produce a thorough, evidence-backed sugar consumption analysis for each business.

When given business details, reason through ALL of the following dimensions before calling the tool:

1. DESSERT / SUGAR MENU DETECTION
   - Scan every field: business name, segment, description, highlights, business tags, types.
   - STRONG signals: "Great dessert", "Award-winning cakes", "Bakery items", "Sweets", "Pastries",
     "Ice cream", "Mithai", "Confectionery", "Patisserie", "Dessert bar"
   - MODERATE signals: "Great coffee" (suggests cafe menu with sweet drinks), "Breakfast" (baked goods),
     "Cocktails" / "Bar" (syrups, mixers)
   - SEGMENT defaults: Bakery, Mithai, IceCream, Patisserie → dessert_menu = true always.
     Cafe → true if any sugar signal present. Restaurant → only if explicitly mentioned.
   - Name signals: Words like "Cakes", "Sweets", "Bakers", "Mithai", "Candies", "Creamery" in the
     business name are strong dessert indicators regardless of other fields.

2. SCALE SIGNALS (critical for volume estimation)
   - Outlet count / is_chain: A chain with 5+ outlets multiplies single-outlet estimate by outlet count.
   - Reviews count: >2,000 reviews → high footfall; 500–2,000 → moderate; <500 → low.
   - Rating ≥ 4.5 with high reviews → established, consistent-volume business.
   - Cross-multiply: a 10-outlet bakery chain uses 10× the sugar of a single independent shop.

3. MONTHLY SUGAR ESTIMATE (kg) — use segment × scale:
   - Mithai (independent)          :  300–600 kg
   - Mithai (chain, 3+ outlets)    : 1,000–5,000 kg
   - Bakery (independent)          :  100–400 kg
   - Bakery (chain, 5+ outlets)    : 1,000–5,000 kg
   - Patisserie / Cake shop        :  150–500 kg
   - Restaurant (no desserts)      :   50–150 kg
   - Restaurant (dessert menu)     :  150–350 kg
   - Cafe (independent)            :   80–200 kg
   - Cafe (chain)                  :  500–2,000 kg
   - Hotel (3-star)                :  200–500 kg
   - Hotel (5-star / luxury)       :  600–2,000 kg
   - IceCream (independent)        :  200–600 kg
   - IceCream (chain)              : 1,000–5,000 kg
   - FoodProcessing plant          : 5,000–20,000 kg

4. SWEETNESS DEPENDENCY % — fraction of output/menu using sugar:
   - Mithai: 95–100% | Patisserie/Cake shop: 80–95% | Bakery: 70–90% | IceCream: 80–90%
   - Cafe: 30–60% | Restaurant: 20–40% | Hotel: 25–50% | CloudKitchen: depends on menu

5. SEGMENT CORRECTION — correct the segment if evidence contradicts the provided one:
   - If a "Restaurant" sells primarily cakes → reclassify as Bakery or Patisserie.
   - If a "Hotel" name includes "Inn" or "Lodge" with low rating → may be a budget property.
   - Always prefer evidence from name + description + tags over the raw segment label.

6. PRICE RANGE SIGNALS
   - Premium localities (e.g. Connaught Place, Bandra, Jubilee Hills, BKC, Golf Course Road,
     Lutyens Delhi, Indiranagar) → likely premium pricing.
   - Rating ≥ 4.5 + high review count + upscale area → premium.
   - Low rating (<3.5) or "budget" in description → budget.

7. CHAIN / OUTLET DETECTION
   - Explicit "chain" tags, franchise mentions, or num_outlets > 1 → is_chain = true.
   - Names with city-suffix patterns (e.g. "Haldiram's Delhi", "Bikanervala Noida") are chains.

8. HOTEL CATEGORY — only for hotels:
   - Look for star ratings in name, description, or tags.
   - Luxury keywords ("five star", "5-star", "luxury", "heritage", "palace") → 5-star.
   - "three star", "budget hotel", "inn" → 3-star.
   - Leave empty for all non-hotel segments.

AFTER reasoning through all 8 dimensions, call the classify_business tool with your complete
evidence-backed analysis. Your ai_reasoning must cite SPECIFIC fields (exact highlights, tags,
name signals, outlet count, review volume) that drove each key decision.""",
    model=OPENAI_MODEL,
    tools=[classify_business],
)


# ══════════════════════════════════════════════════════════════════════════════
# RUNNER — execute the agent and extract the tool's JSON output
# ══════════════════════════════════════════════════════════════════════════════

async def classify_business_runner(biz: dict) -> dict:
    """
    Classify a single HORECA business using the Business Intelligence Agent.

    Args:
        biz: Raw business dict (Stage 1 output shape).

    Returns:
        Parsed analysis dict with sugar-intelligence fields, or a fallback
        dict with safe defaults if the agent or JSON parsing fails.
    """
    prompt = (
        f"Analyze this HORECA business for sugar intelligence:\n\n"
        f"Business Name  : {biz.get('business_name', '')}\n"
        f"Segment        : {biz.get('segment', 'Restaurant')}\n"
        f"City           : {biz.get('city', '')}\n"
        f"Address        : {biz.get('address', 'Not available')}\n"
        f"Website        : {biz.get('website', 'Not available')}\n"
        f"Rating         : {biz.get('rating', 0)}/5  ({biz.get('reviews_count', 0):,} reviews)\n"
        f"Outlets        : {biz.get('num_outlets', 1)}  |  Chain: {biz.get('is_chain', False)}\n"
        f"Types          : {', '.join(biz.get('types', [])) or 'Not available'}\n"
        f"Description    : {biz.get('description', 'Not available')}\n"
        f"Highlights     : {', '.join(biz.get('highlights', [])) or 'Not available'}\n"
        f"Business Tags  : {', '.join(biz.get('from_the_business', [])) or 'Not available'}\n"
        f"Dining Options : {', '.join(biz.get('dining_options', [])) or 'Not available'}\n"
        f"Offerings      : {', '.join(biz.get('offerings', [])) or 'Not available'}"
    )

    result = await Runner.run(business_intelligence_agent, prompt)
    log_agent_flow(result.new_items)
    logger.info(f"Agent chain: {' → '.join(extract_agent_chain(result.new_items))}")

    # The real output is in new_items as tool_call_output_item, not final_output prose
    for item in result.new_items:
        if getattr(item, "type", None) == "tool_call_output_item":
            try:
                parsed = json.loads(item.output)
                if isinstance(parsed, dict) and "has_dessert_menu" in parsed:
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

    try:
        return json.loads(result.final_output)
    except (json.JSONDecodeError, TypeError):
        return {"raw": result.final_output}
