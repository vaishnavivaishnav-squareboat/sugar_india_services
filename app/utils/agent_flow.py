"""
app/agents/utils/agent_flow.py
─────────────────────────────────────────────────────────────────────────────
Agent execution flow helpers.

Provides two utilities:
  log_agent_flow(new_items)     : pretty-prints each step of agent execution
  extract_agent_chain(new_items): returns ordered list of agents that participated

Mirrors: agents/src/utils/agentFlow.js
─────────────────────────────────────────────────────────────────────────────
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def log_agent_flow(new_items: list[Any]) -> None:
    """
    Pretty-prints every step of an agent run for debugging.

    Args:
        new_items: result.new_items from Runner.run()
    """
    logger.debug("\n[FLOW] ── Agent execution flow ──")
    for i, item in enumerate(new_items, start=1):
        step      = f"[FLOW] Step {i}"
        item_type = getattr(item, "type", "") or type(item).__name__

        if "handoff_call" in item_type:
            agent_name  = getattr(getattr(item, "agent", None), "name", "?")
            raw         = getattr(item, "raw_item", None)
            target_name = getattr(raw, "name", "?") if raw else "?"
            logger.debug(f"{step}: 🔀 {agent_name} triggered handoff → {target_name}")

        elif "handoff_output" in item_type:
            src = getattr(getattr(item, "source_agent", None), "name", "?")
            tgt = getattr(getattr(item, "target_agent", None), "name", "?")
            logger.debug(f"{step}: ✅ Handoff complete  {src} → {tgt}")

        elif "tool_call_item" == item_type or "tool_call" in item_type and "output" not in item_type:
            agent_name = getattr(getattr(item, "agent", None), "name", "?")
            raw        = getattr(item, "raw_item", None)
            tool_name  = getattr(raw, "name", "?") if raw else "?"
            args       = getattr(raw, "arguments", "{}") if raw else "{}"
            logger.debug(f"{step}: 🔧 {agent_name} called tool '{tool_name}' with {args[:120]}")

        elif "tool_call_output" in item_type:
            agent_name = getattr(getattr(item, "agent", None), "name", "?")
            raw        = getattr(item, "raw_item", None)
            out        = ""
            if raw:
                output = getattr(raw, "output", None)
                if isinstance(output, str):
                    out = output[:80]
                elif hasattr(output, "text"):
                    out = (output.text or "")[:80]
            logger.debug(f"{step}: 📦 {agent_name} got tool result → '{out}'")

        elif "message_output" in item_type:
            agent_name = getattr(getattr(item, "agent", None), "name", "?")
            raw        = getattr(item, "raw_item", None)
            text       = ""
            if raw:
                content = getattr(raw, "content", None)
                if isinstance(content, list) and content:
                    text = getattr(content[0], "text", "")[:80]
                elif isinstance(content, str):
                    text = content[:80]
            logger.debug(f"{step}: 💬 {agent_name} responded → '{text}...'")

        else:
            agent_name = getattr(getattr(item, "agent", None), "name", "unknown")
            logger.debug(f"{step}: ❓ {item_type} (agent: {agent_name})")

    logger.debug("[FLOW] ────────────────────────")


def extract_agent_chain(new_items: list[Any]) -> list[str]:
    """
    Extracts an ordered list of unique agent names from result.new_items.
    Reflects the actual call order: source → target.

    Args:
        new_items: result.new_items from Runner.run()

    Returns:
        Ordered list of unique agent names.
    """
    seen: list[str] = []
    for item in new_items:
        for attr in ("agent", "source_agent", "target_agent"):
            agent_obj = getattr(item, attr, None)
            name = getattr(agent_obj, "name", None) if agent_obj else None
            if name and name not in seen:
                seen.append(name)
    return seen
