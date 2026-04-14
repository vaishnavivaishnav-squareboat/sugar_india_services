"""
app/services/genai.py
─────────────────────────────────────────────────────────────────────────────
Google Gemini AI helper — thread-safe API key rotation across multiple keys.
─────────────────────────────────────────────────────────────────────────────
"""
import itertools
from google import genai

# Import GENAI_API_KEYS from centralized config
from app.core.config import GENAI_API_KEYS

# Thread-safe API key rotation
raw_keys = GENAI_API_KEYS

if not raw_keys:
    raise ValueError("GENAI_API_KEYS is not set in environment")

api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

if not api_keys:
    raise ValueError("No valid GENAI API keys found")

api_key_cycle = itertools.cycle(api_keys)


def call_genai(prompt: str, force_json: bool = False) -> str:
    """Call Gemini with the next API key in the rotation cycle."""
    client = genai.Client(api_key=next(api_key_cycle))

    config = {}
    if force_json:
        config["response_mime_type"] = "application/json"

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=config if config else None,
    )

    return response.text
