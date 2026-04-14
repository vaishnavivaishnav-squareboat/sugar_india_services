"""
app/prompts/follow_up_email.py
─────────────────────────────────────────────────────────────────────────────
Prompt — follow-up email sent 3 days after the initial outreach email
received no response.

Caller : app/api/outreach.py  →  _run_follow_up()
Model  : OpenAI (chat completions)
Output : Plain text — "SUBJECT: ...\n\nDear {first_name},\n{body}"
─────────────────────────────────────────────────────────────────────────────
"""


def follow_up_email_prompt(
    business_name: str,
    segment: str,
    city: str,
    dm: str,
    first_name: str,
    role: str,
    original_subject: str,
    days_since_sent: int = 3,
) -> str:
    return f"""
You are a B2B sales executive at Dhampur Green, India's premium quality sugar brand.
Dhampur Green Products: Premium refined sugar (M30/S30), sulphur-free jaggery, brown sugar, organic cane sugar, khandsari, icing sugar.

You sent an initial outreach email to the HORECA business below {days_since_sent} days ago and have not received a response.
Write a short, polite follow-up email to gently remind them and re-engage.

Business Name    : {business_name}
City             : {city}
Segment          : {segment}
Contact          : {dm or 'Procurement Team'}
Role             : {role}
Original Subject : {original_subject}

Guidelines:
  - Keep it brief — 80-120 words.
  - Reference that you sent an earlier email (subject: "{original_subject}").
  - Friendly and non-pushy tone; add value rather than just chasing.
  - Offer something concrete: a free sample, a quick 10-min call, or a product brochure.
  - Sign off from "Arjun Mehta | Regional Sales Manager, Dhampur Green | +91-98765-43210"

Format EXACTLY:
SUBJECT: [subject — typically "Re: {original_subject}" or a gentle variation]

Dear {first_name},
[body]"""
