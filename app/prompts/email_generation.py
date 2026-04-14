"""
app/prompts/email_generation.py
─────────────────────────────────────────────────────────────────────────────
Prompt — Stage 7 (Gemini fallback): personalised B2B outreach email.

Caller : app/pipelines/stages.py  →  generate_personalized_emails()
Model  : Gemini (call_genai)
Output : JSON — subject, body
─────────────────────────────────────────────────────────────────────────────
"""


def email_generation_prompt(
    name: str,
    city: str,
    segment: str,
    contact_name: str,
    contact_role: str,
    has_dessert: bool,
    sugar_kg: int,
    rating: float,
    hotel_cat: str,
    reasoning: str,
) -> str:
    return f"""
You are a B2B sales executive at Dhampur Green, India's premium quality sugar brand.
Write a personalized outreach email to the following HORECA business.

Business Name  : {name}
City           : {city}
Segment        : {segment}
Contact        : {contact_name or 'Procurement Team'}
Role           : {contact_role}
Dessert Menu   : {'Yes' if has_dessert else 'No'}
Monthly Sugar  : ~{sugar_kg} kg estimated
Rating         : {rating}/5
Hotel Category : {hotel_cat or 'N/A'}
AI Insight     : {reasoning}

Guidelines:
  - 150-200 words, concise and professional.
  - Personalise based on segment / sugar usage.
  - Highlight Dhampur Green: quality, sulphur-free sugar, reliable supply.
  - Include a clear CTA (sample request or 15-min call).
  - Sign off from "Arjun Mehta | Regional Sales Manager, Dhampur Green | +91-98765-43210"

Return ONLY a JSON object:
{{
  "subject" : "<email subject line>",
  "body"    : "<full email body with greeting, value prop, and CTA>"
}}
"""
