"""
app/prompts/
─────────────────────────────────────────────────────────────────────────────
Centralised prompt templates for all AI/LLM calls in the pipeline and API.

Each module exposes a single builder function that accepts the required
variables and returns a fully-rendered prompt string.

Modules:
  business_intelligence  – Stage 2 (Gemini): sugar consumption analysis
  contact_extraction     – Stage 5 (Gemini): decision-maker extraction
  email_generation       – Stage 7 (Gemini): personalised outreach email
  lead_qualify           – API /qualify-ai  : lead qualification + scoring
  lead_email_api         – API /generate-email: quick email from lead record
─────────────────────────────────────────────────────────────────────────────
"""
from app.agents.prompts.business_intelligence import business_intelligence_prompt
from app.agents.prompts.contact_extraction    import contact_extraction_prompt
from app.agents.prompts.lead_qualify          import lead_qualify_prompt
from app.agents.prompts.lead_email_api        import lead_email_api_prompt

__all__ = [
    "business_intelligence_prompt",
    "contact_extraction_prompt",
    "lead_qualify_prompt",
    "lead_email_api_prompt",
]
