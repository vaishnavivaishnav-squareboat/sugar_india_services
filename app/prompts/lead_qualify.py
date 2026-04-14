"""
app/prompts/lead_qualify.py
─────────────────────────────────────────────────────────────────────────────
Prompt — API POST /leads/{id}/qualify-ai: score and qualify a saved lead.

Caller : app/api/lead.py  →  qualify_lead_ai()
Model  : Gemini (call_genai)
Output : JSON — ai_score, monthly_volume_kg, qualification_summary,
                sugar_use_cases, key_insight, priority, best_contact_time
─────────────────────────────────────────────────────────────────────────────
"""


def lead_qualify_prompt(
    business_name: str,
    segment: str,
    city: str,
    state: str,
    rating: float,
    num_outlets: int,
    hotel_category: str,
    has_dessert_menu: bool,
    is_chain: bool,
) -> str:
    return f"""Qualify this HORECA business for Dhampur Green (sugar/jaggery supplier):
Business: {business_name}, Segment: {segment}
Location: {city}, {state or 'India'} | Rating: {rating}/5 | Outlets: {num_outlets}
Hotel Category: {hotel_category or 'N/A'} | Dessert Menu: {has_dessert_menu} | Chain: {is_chain}

Respond ONLY with valid JSON:
{{"ai_score":<0-100>,"monthly_volume_kg":"<range>","qualification_summary":"<2-3 sentences>","sugar_use_cases":["<uc1>","<uc2>","<uc3>"],"key_insight":"<sales insight>","priority":"<High/Medium/Low>","best_contact_time":"<recommendation>"}}"""
