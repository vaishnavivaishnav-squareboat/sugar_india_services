"""
app/agents/pipeline.py
─────────────────────────────────────────────────────────────────────────────
Main entry point — demonstrates all 3 AI pipeline stages.

  Stage 2 → Business Intelligence Agent  (classifies businesses)
  Stage 5 → Contact Discovery Agent      (finds decision-makers)
  Stage 7 → Email Generator Agent        (writes outreach emails)

Also shows the full orchestrated flow via the Pipeline Orchestrator Agent.

Mirrors: agents/src/pipeline.js

Run:  python -m app.agents.pipeline
─────────────────────────────────────────────────────────────────────────────
"""
import asyncio
import json
import logging

from agents import Runner

# ── CRITICAL: register OpenAI client before any agent imports ─────────────────
import app.services.openai_client  # noqa: F401

from app.agents.agents.business_intelligence import business_intelligence_agent
from app.agents.agents.contact_discovery import contact_discovery_agent
from app.agents.agents.email_generator import email_generator_agent
from app.agents.agents.pipeline_orchestrator import pipeline_orchestrator_agent
from app.utils.agent_flow import extract_agent_chain, log_agent_flow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — Business Intelligence Analysis
# Mirrors: pipeline_stages.py → ai_process_business_data()
# ─────────────────────────────────────────────────────────────────────────────
async def run_stage2_business_intelligence() -> str:
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🏭  STAGE 2: Business Intelligence Analysis")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    prompt = (
        "Analyze this HORECA business for sugar intelligence:\n\n"
        "Business Name  : La Folie Patisserie\n"
        "Segment        : Bakery\n"
        "City           : Mumbai\n"
        "Website        : www.lafolie.in\n"
        "Rating         : 4.7/5\n"
        "Types          : Patisserie, Cafe, Bakery\n"
        "Description    : French-style patisserie offering premium pastries, cakes and desserts\n"
        "Highlights     : Great dessert, Great coffee, Award-winning pastries, Cakes\n"
        "Business Tags  : Premium artisanal bakery, Imported ingredients"
    )

    result = await Runner.run(business_intelligence_agent, prompt)
    log_agent_flow(result.new_items)

    print("\n✅  Stage 2 Result:")
    print("Agent chain:", " → ".join(extract_agent_chain(result.new_items)))
    print("Output:", result.final_output)
    return result.final_output


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 5 — Contact Discovery
# Mirrors: pipeline_stages.py → _ai_extract_contact() inside enrich_contacts()
# ─────────────────────────────────────────────────────────────────────────────
async def run_stage5_contact_discovery() -> str:
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🔍  STAGE 5: Contact Discovery")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    serp_snippets = [
        {
            "title":   "La Folie Patisserie – About Us",
            "snippet": "La Folie was founded by Sanjana Patel, head pastry chef and owner. "
                       "For procurement enquiries contact procurement@lafolie.in",
        },
        {
            "title":   "LinkedIn – Sanjana Patel | La Folie Patisserie",
            "snippet": "Sanjana Patel – Owner & Head Pastry Chef at La Folie Patisserie, Mumbai. "
                       "linkedin.com/in/sanjana-patel-lafolie",
        },
        {
            "title":   "YourStory: La Folie, the patisserie that changed Mumbai's dessert scene",
            "snippet": "Sanjana Patel, who oversees all ingredient sourcing and supplier relationships, "
                       "built La Folie from a single outlet to six across Mumbai.",
        },
    ]

    snippets_text = "\n".join(f"- {r['title']}: {r['snippet']}" for r in serp_snippets)
    prompt = (
        "Find the procurement decision-maker for this HORECA business:\n\n"
        "Business : La Folie Patisserie\n"
        "City     : Mumbai\n"
        "Segment  : Bakery\n\n"
        f"Web search results:\n{snippets_text}"
    )

    result = await Runner.run(contact_discovery_agent, prompt)
    log_agent_flow(result.new_items)

    print("\n✅  Stage 5 Result:")
    print("Agent chain:", " → ".join(extract_agent_chain(result.new_items)))
    print("Output:", result.final_output)
    return result.final_output


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 7 — Personalized Email Generation
# Mirrors: pipeline_stages.py → generate_personalized_emails()
# ─────────────────────────────────────────────────────────────────────────────
async def run_stage7_email_generation() -> str:
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("✉️   STAGE 7: Personalized Email Generation")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    prompt = (
        "Generate a personalized B2B outreach email for this HORECA lead:\n\n"
        "Business      : La Folie Patisserie\n"
        "City          : Mumbai\n"
        "Segment       : Bakery\n"
        "Contact       : Sanjana Patel (Owner & Head Pastry Chef)\n"
        "Dessert Menu  : Yes\n"
        "Monthly Sugar : ~400 kg estimated\n"
        "Rating        : 4.7/5\n"
        "AI Insight    : Premium artisanal bakery with strong dessert focus; "
        "highlights confirm award-winning pastries and cakes — high sugar dependency across all product lines."
    )

    result = await Runner.run(email_generator_agent, prompt)
    log_agent_flow(result.new_items)

    print("\n✅  Stage 7 Result:")
    print("Agent chain:", " → ".join(extract_agent_chain(result.new_items)))
    print("Output:", result.final_output)
    return result.final_output


# ─────────────────────────────────────────────────────────────────────────────
# FULL PIPELINE — Via Orchestrator (with handoffs)
# ─────────────────────────────────────────────────────────────────────────────
async def run_full_pipeline_via_orchestrator() -> str:
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🤖  FULL PIPELINE via Orchestrator (with handoffs)")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    prompt = (
        "I need to generate an outreach email for a new HORECA lead:\n\n"
        "Business      : Grand Hyatt Mumbai\n"
        "Segment       : Hotel (5-star)\n"
        "City          : Mumbai\n"
        "Decision Maker: Priya Sharma, Purchase Manager\n"
        "Dessert Menu  : Yes\n"
        "Monthly Sugar : ~700 kg estimated\n"
        "Rating        : 4.6/5\n"
        "AI Insight    : Premium 5-star hotel with multiple F&B outlets; "
        "high sugar consumption across restaurant, bar, and banquet operations."
    )

    result = await Runner.run(pipeline_orchestrator_agent, prompt)
    log_agent_flow(result.new_items)

    print("\n✅  Orchestrator Result:")
    print("Agent chain:", " → ".join(extract_agent_chain(result.new_items)))
    print("Output:", result.final_output)
    return result.final_output


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
async def main() -> None:
    await run_stage2_business_intelligence()
    await run_stage5_contact_discovery()
    await run_stage7_email_generation()
    await run_full_pipeline_via_orchestrator()

    print("\n🎉  All pipeline agent stages completed successfully!")
    print("📄  Generated emails saved to: generated_emails.jsonl\n")


if __name__ == "__main__":
    asyncio.run(main())
