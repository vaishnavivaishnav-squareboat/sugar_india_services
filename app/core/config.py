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

# ── SMTP / Email Sending ──────────────────────────────────────────────────
SMTP_HOST: str     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM: str     = os.getenv("SMTP_FROM", "")  # "Dhampur Green <you@gmail.com>"

# ── Snov.io (Stage 6 tertiary email enrichment) ───────────────────────────
SNOV_CLIENT_ID:     str = os.getenv("SNOV_CLIENT_ID", "")
SNOV_CLIENT_SECRET: str = os.getenv("SNOV_CLIENT_SECRET", "")

# ── API URLS ───────────────────────────────────────────────────────────────
APOLLO_PEOPLE_MATCH_URL: str = os.getenv("APOLLO_PEOPLE_MATCH_URL")
SERP_ENDPOINT: str = os.getenv("SERP_ENDPOINT", "https://www.searchapi.io/api/v1/search")
SNOV_TOKEN_URL: str  = os.getenv("SNOV_TOKEN_URL")
SNOV_SEARCH_URL: str = os.getenv("SNOV_SEARCH_URL")
SNOV_EMAIL_URL: str  = os.getenv("SNOV_EMAIL_URL")