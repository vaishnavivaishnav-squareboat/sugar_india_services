import itertools
from google import genai
from dotenv import load_dotenv
from pathlib import Path
import os

# Load environment variables from .env file
load_dotenv(Path(__file__).parent / '.env')

# Thread-safe API key rotation
raw_keys = os.getenv("GENAI_API_KEYS")

if not raw_keys:
    raise ValueError("GENAI_API_KEYS is not set in environment")

api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

if not api_keys:
    raise ValueError("No valid GENAI API keys found")

api_key_cycle = itertools.cycle(api_keys)

def call_genai(prompt: str, force_json: bool = False) -> str:
    client = genai.Client(api_key=next(api_key_cycle))

    config = {}
    if force_json:
        config["response_mime_type"] = "application/json"

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=config if config else None
    )

    return response.text