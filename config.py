"""App configuration and API keys."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

# NHL API (free, no key required). New API at api-web.nhle.com; legacy statsapi.web.nhl.com may not resolve.
NHL_API_BASE = "https://api-web.nhle.com/v1"
# NHL Stats REST (PP/PK, etc.) - different host
NHL_STATS_REST_BASE = "https://api.nhle.com/stats/rest/en"

DATA_DIR = Path(__file__).resolve().parent / "data"


def _secret(name: str) -> str:
    """Env var / .env first, then Streamlit Cloud secrets."""
    val = (os.getenv(name) or "").strip()
    if val:
        return val
    try:
        import streamlit as st
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


# The Odds API - https://the-odds-api.com/
ODDS_API_KEY = _secret("ODDS_API_KEY")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# NHL news RSS (team-agnostic and team-specific available)
NHL_NEWS_RSS = "https://www.to-rss.xyz/nhl/"


def current_season_id(today=None) -> str:
    """NHL season id like 20262027. Seasons start in October."""
    from datetime import date
    d = today or date.today()
    start = d.year if d.month >= 9 else d.year - 1
    return f"{start}{start + 1}"
