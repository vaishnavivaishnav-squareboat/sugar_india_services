"""
app/agents/tools/classify_business.py
─────────────────────────────────────────────────────────────────────────────
Tool: classify_business — Stage 2 (Business Intelligence)

Mirrors: agents/src/tools/classifyBusiness.js
The Business Intelligence Agent calls this tool with its full
sugar-intelligence analysis after reasoning over the business details.
─────────────────────────────────────────────────────────────────────────────
"""
import json
import logging
from typing import Annotated, Literal

from agents import function_tool

logger = logging.getLogger(__name__)


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
        f"[TOOL: classify_business] 🍬 Classified '{business_classification}' — "
        f"entire analysis: {json.dumps(analysis, indent=2)}"
    )
    return json.dumps(analysis)
