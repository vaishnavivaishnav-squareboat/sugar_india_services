"""
app/prompts/business_intelligence.py
─────────────────────────────────────────────────────────────────────────────
Prompt — Stage 2: HORECA business sugar-intelligence analysis.

Caller : app/pipelines/stages.py  →  ai_process_business_data()
Model  : OpenAI (call_openai, force_json=True)
Output : JSON — has_dessert_menu, monthly_sugar_estimate_kg, segment, etc.
─────────────────────────────────────────────────────────────────────────────
"""


def business_intelligence_prompt(
    name: str,
    segment: str,
    city: str,
    website: str,
    rating: float,
    types: str,
    description_text: str,
    highlights_text: str,
    identity_text: str,
) -> str:
    return f"""
You are a HORECA business intelligence analyst for a sugar supplier in India.

Analyze this business and return intelligence for sugar sales targeting:

Business Name  : {name}
Segment        : {segment}
City           : {city}
Website        : {website or 'Not available'}
Rating         : {rating}/5
Types          : {types}
Description    : {description_text}
Highlights     : {highlights_text}
Business Tags  : {identity_text}

IMPORTANT: Pay close attention to the Highlights field and Description field.
Keywords like "Great dessert", "Great coffee", "Great tea selection", "Bakery items",
"Sweets", "Pastries", "Cakes", "Ice cream" are STRONG indicators of sugar consumption.

Return ONLY a JSON object with these exact fields:
{{
  "has_dessert_menu"              : true or false,
  "sugar_items_count"             : <integer>,
  "menu_categories"               : ["list", "of", "menu", "categories"],
  "avg_price_range"               : "<budget | mid-range | premium>",
  "business_classification"       : "<Hotel | Restaurant | Cafe | Bakery | Catering>",
  "is_chain"                      : true or false,
  "hotel_category"                : "<3-star | 4-star | 5-star | empty string if not hotel>",
  "monthly_sugar_estimate_kg"     : <integer>,
  "sweetness_dependency_pct"      : <integer 0-100>,
  "sugar_signal_from_highlights"  : true or false,
  "highlight_sugar_signals"       : ["list of highlight keywords"],
  "ai_reasoning"                  : "<1-2 sentence justification>"
}}
"""
