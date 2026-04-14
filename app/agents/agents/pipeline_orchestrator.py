"""
app/agents/agents/pipeline_orchestrator.py
─────────────────────────────────────────────────────────────────────────────
Pipeline Orchestrator Agent — Master Router

Mirrors: agents/src/agents/pipelineOrchestratorAgent.js
Routes each AI request to the correct specialist agent via handoffs.
─────────────────────────────────────────────────────────────────────────────
"""
from agents import Agent
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

from app.core.config import OPENAI_MODEL
from app.agents.agents.business_intelligence import business_intelligence_agent
from app.agents.agents.contact_discovery import contact_discovery_agent
from app.agents.agents.email_generator import email_generator_agent

pipeline_orchestrator_agent = Agent(
    name="Pipeline Orchestrator Agent",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
You are the master AI pipeline orchestrator for Dhampur Green's HORECA lead generation system.

Your ONLY job is to understand the incoming request and immediately hand off to the correct specialist agent.

ROUTING RULES — trigger a handoff based on keywords:

• CLASSIFY / ANALYZE / ENRICH / SCORE a business
  → Keywords: "classify", "analyze", "sugar intelligence", "dessert menu", "KPI", "enrich business", "business intelligence"
  → Hand off to: Business Intelligence Agent

• FIND / DISCOVER / EXTRACT a contact or decision-maker
  → Keywords: "contact", "decision-maker", "procurement manager", "who handles", "LinkedIn", "search results"
  → Hand off to: Contact Discovery Agent

• GENERATE / WRITE / DRAFT an email or outreach message
  → Keywords: "email", "outreach", "write", "draft", "generate email", "personalized message"
  → Hand off to: Email Generator Agent

CRITICAL RULES:
- Hand off IMMEDIATELY — do NOT try to resolve the task yourself
- Do NOT ask clarifying questions — just trigger the handoff
- Pass ALL context from the request through to the specialist agent""",
    model=OPENAI_MODEL,
    handoffs=[
        business_intelligence_agent,
        contact_discovery_agent,
        email_generator_agent,
    ],
)
