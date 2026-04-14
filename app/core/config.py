"""
app/core/config.py
─────────────────────────────────────────────────────────────────────────────
Central configuration — reads all env vars from .env and exposes them as
typed module-level constants.
─────────────────────────────────────────────────────────────────────────────
"""
from pathlib import Path
from dotenv import load_dotenv
import os

# sugar_india_services/ (3 levels up from app/core/config.py)
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

# ── Database ──────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

# ── AI / LLM ─────────────────────────────────────────────────────────────
GENAI_API_KEYS: str        = os.getenv("GENAI_API_KEYS", "")
GOOGLE_PLACES_API_KEY: str = os.getenv("GOOGLE_PLACES_API_KEY", "")

# ── Pipeline APIs ─────────────────────────────────────────────────────────
SERP_API_KEY: str   = os.getenv("SERP_API_KEY", "")
HUNTER_API_KEY: str = os.getenv("HUNTER_API_KEY", "")
APOLLO_API_KEY: str = os.getenv("APOLLO_API_KEY", "")

# ── Agents / OpenAI ───────────────────────────────────────────────────────
OPENAI_API_KEY: str  = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "")   # optional; empty = default OpenAI
OPENAI_MODEL: str    = os.getenv("OPENAI_MODEL", "gpt-4o") # override via env if needed

# ── Server ────────────────────────────────────────────────────────────────
CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")
