"""
app/prompts/lead_email_api.py
─────────────────────────────────────────────────────────────────────────────
Prompt — API POST /leads/{id}/generate-email: quick outreach email from a
saved lead record (used by the frontend "Generate Email" button).

Caller : app/api/lead.py  →  generate_email()
Model  : Gemini (call_genai)
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
) -> str:
    return f"""Write a personalized B2B outreach email for Dhampur Green targeting:
Business: {business_name} ({segment}, {city})
Decision Maker: {dm} ({role or 'F&B Head'})
Rating: {rating}/5 | Outlets: {num_outlets} | Dessert Menu: {has_dessert_menu}
Monthly Volume Estimate: {monthly_volume_estimate or 'Unknown'}

Dhampur Green Products: Premium refined sugar (M30/S30), sulphur-free jaggery, brown sugar, organic cane sugar, khandsari, icing sugar.

Write a 5-7 line professional email. Sign off from "Arjun Mehta | Regional Sales Manager, Dhampur Green | +91-98765-43210"

Format EXACTLY:
SUBJECT: [subject]

Dear {first_name},
[body]"""
