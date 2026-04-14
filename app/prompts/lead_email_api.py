"""
app/prompts/lead_email_api.py
─────────────────────────────────────────────────────────────────────────────
Prompt — API POST /leads/{id}/generate-email: quick outreach email from a
saved lead record (used by the frontend "Generate Email" button).

Caller : app/api/lead.py  →  generate_email()
Model  : OpenAI (chat completions)
Output : Plain text — "SUBJECT: ...\n\nDear {first_name},\n{body}"
─────────────────────────────────────────────────────────────────────────────
"""


def lead_email_api_prompt(
    business_name: str,
    segment: str,
    city: str,
    dm: str,
    first_name: str,
    role: str,
    rating: float,
    num_outlets: int,
    has_dessert_menu: bool,
    monthly_volume_estimate: str,
    reasoning: str = "",
) -> str:
    return f"""
    
You are a B2B sales executive at Dhampur Green, India's premium quality sugar brand. Dhampur Green Products: 
Premium refined sugar (M30/S30), sulphur-free jaggery, brown sugar, organic cane sugar, khandsari, icing sugar.
Write a personalized outreach email to the following HORECA business.

Business Name  : {business_name}
City           : {city}
Segment        : {segment}
Contact        : {dm or 'Procurement Team'}
Role           : {role}
Rating         : {rating}/5 | Outlets: {num_outlets} | Dessert Menu: {'Yes' if has_dessert_menu else 'No'}
Monthly Sugar  : ~{monthly_volume_estimate} estimated
AI Insight     : {reasoning or 'N/A'}

Guidelines:
  - 150-200 words, concise and professional.
  - Personalise based on segment / sugar usage.
  - Highlight Dhampur Green: quality, sulphur-free sugar, reliable supply.
  - Include a clear CTA (sample request or 15-min call).
  - Sign off from "Arjun Mehta | Regional Sales Manager, Dhampur Green | +91-98765-43210"

Format EXACTLY:
SUBJECT: [subject]

Dear {first_name},
[body]"""
