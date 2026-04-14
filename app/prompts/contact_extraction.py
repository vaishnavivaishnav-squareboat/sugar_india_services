"""
app/prompts/contact_extraction.py
─────────────────────────────────────────────────────────────────────────────
Prompt — Stage 5 (Gemini fallback): procurement decision-maker extraction
from SerpAPI web snippets.

Caller : app/pipelines/stages.py  →  _ai_extract_contact()
Model  : Gemini (call_genai)
Output : JSON — name, role, linkedin_url, confidence_score
─────────────────────────────────────────────────────────────────────────────
"""


def contact_extraction_prompt(
    biz_name: str,
    city: str,
    segment: str,
    snippets_text: str,
) -> str:
    return f"""
You are helping find the procurement decision-maker for a HORECA business in India.

Business : {biz_name}
City     : {city}
Segment  : {segment}

Web search results:
{snippets_text}

Return ONLY a JSON object:
{{
  "name"             : "<full name or empty string>",
  "role"             : "<F&B Manager | Procurement Manager | Operations Manager | Owner | empty>",
  "linkedin_url"     : "<LinkedIn URL or empty string>",
  "confidence_score" : <0.0-1.0>
}}
"""
