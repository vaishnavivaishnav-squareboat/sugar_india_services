"""
app/agents/tools/extract_contact.py
─────────────────────────────────────────────────────────────────────────────
Tool: extract_contact — Stage 5 (Contact Discovery)

Mirrors: agents/src/tools/extractContact.js
The Contact Discovery Agent calls this after reasoning over SERP snippets
to identify the best procurement decision-maker for a HORECA business.
─────────────────────────────────────────────────────────────────────────────
"""
import json
import logging
from typing import Annotated

from agents import function_tool

logger = logging.getLogger(__name__)


@function_tool
def extract_contact(
    name: Annotated[
        str,
        "Full name of the decision-maker, or empty string if not found",
    ],
    role: Annotated[
        str,
        (
            "Job role — e.g. F&B Manager, Procurement Manager, Operations Manager, "
            "Store Manager, General Manager, Owner, Founder — or empty string"
        ),
    ],
    linkedin_url: Annotated[str, "Full LinkedIn profile URL or empty string"],
    confidence_score: Annotated[
        float,
        "How confident you are this is a real, reachable contact (0.0–1.0)",
    ],
    reasoning: Annotated[
        str,
        "Brief explanation of why this person handles sugar/ingredient procurement",
    ],
) -> str:
    """
    Records the identified procurement decision-maker for a HORECA business.
    Call this with the best contact you found after analyzing the web search results.
    If no real contact is identifiable, return empty strings and confidence_score 0.0.
    """
    contact = {
        "name":             name,
        "role":             role,
        "linkedin_url":     linkedin_url,
        "confidence_score": confidence_score,
        "reasoning":        reasoning,
    }
    if name and confidence_score >= 0.5:
        logger.info(
            f"[TOOL: extract_contact] 👤 Found: {name} ({role}) — "
            f"confidence {confidence_score * 100:.0f}%"
        )
    else:
        logger.info("[TOOL: extract_contact] ⚠️  No confident contact identified")
    return json.dumps(contact)
