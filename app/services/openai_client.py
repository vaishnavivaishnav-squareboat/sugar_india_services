"""
app/services/openai_client.py
─────────────────────────────────────────────────────────────────────────────
Shared OpenAI async client — created once and registered as the default
client for the openai-agents SDK.

Mirrors: agents/src/config/openai.js
─────────────────────────────────────────────────────────────────────────────
"""
from openai import AsyncOpenAI
from agents import set_default_openai_client, set_tracing_disabled

from app.core.config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL

if not OPENAI_API_KEY:
    raise ValueError("[config] Missing required environment variable: OPENAI_API_KEY")

# Build client kwargs — only pass base_url if explicitly configured
_client_kwargs: dict = {"api_key": OPENAI_API_KEY}
if OPENAI_BASE_URL:
    _client_kwargs["base_url"] = OPENAI_BASE_URL

client = AsyncOpenAI(**_client_kwargs)

# Register as the default client for all agents in this process
set_default_openai_client(client)

# Suppress 401 / tracing noise when using non-OpenAI compatible endpoints
set_tracing_disabled(True)


async def call_openai(prompt: str, force_json: bool = False) -> str:
    """
    Drop-in async replacement for the old Gemini helper.

    Args:
        prompt:     The user prompt to send.
        force_json: If True, sets response_format={"type": "json_object"}
                    so the model always returns valid JSON.

    Returns:
        The model's response text as a plain string.
    """
    kwargs: dict = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful HORECA business intelligence assistant for Dhampur Green, an Indian sugar supplier. Always follow the output format exactly as requested."},
            {"role": "user",   "content": prompt},
        ],
    }
    if force_json:
        kwargs["response_format"] = {"type": "json_object"}

    completion = await client.chat.completions.create(**kwargs)
    return completion.choices[0].message.content


__all__ = ["client", "call_openai"]
