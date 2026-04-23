"""
app/prompts/contact_extraction.py
─────────────────────────────────────────────────────────────────────────────
Prompt — Stage 5: procurement decision-maker extraction
from SerpAPI web snippets.

Caller : app/pipelines/stages.py  →  _ai_extract_contact()
Model  : OpenAI (call_openai, force_json=True)
Output : JSON — name, role, linkedin_url, confidence_score
─────────────────────────────────────────────────────────────────────────────
"""
from app.core.constants import roles

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
  "role"             : "Job role — e.g. {', '.join(roles)} — or empty string",
  "linkedin_url"     : "<LinkedIn URL copied VERBATIM from the snippet, including any alphanumeric suffix e.g. /in/john-doe-03136b1b/ — never shorten it. Empty string if not found>",
  "confidence_score" : <0.0-1.0>
}}
"""
