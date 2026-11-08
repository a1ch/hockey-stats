"""Shared sidebar settings and the odds loader used by every page."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from config import DATA_DIR, ODDS_API_KEY
from odds_client import QUOTA, fetch_nhl_odds_cached, parse_games

SETTINGS_FILE = DATA_DIR / "settings.json"
SAMPLE_FILE = Path(__file__).resolve().parent / "tests" / "fixtures" / "sample_odds.json"
REGION_HELP = {
    "us": "US books (DraftKings, FanDuel, BetMGM, Caesars...)",
    "us2": "More US books (ESPN BET, Fanatics, Hard Rock...)",
    "eu": "Europe, includes Pinnacle (the sharp reference price)",
    "uk": "UK books (bet365, William Hill...)",
    "au": "Australia",
}
DEFAULTS = {
    "regions": ["us", "eu"], "markets": ["h2h", "totals", "spreads"], "refresh_min": 10,
    "my_books": [], "bankroll": 500.0, "kelly": 0.25, "min_ev": 2.0, "max_price": 6.0,
    "tz": "America/Edmonton", "sample": False,
}


def load_settings() -> dict:
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s: dict) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(s, indent=1), encoding="utf-8")
    except OSError:
        pass  # read-only host (Streamlit Cloud): settings last for the session


def settings() -> dict:
    if "cfg" not in st.session_state:
        st.session_state["cfg"] = load_settings()
    return st.session_state["cfg"]


def api_key() -> str:
    return (st.session_state.get("odds_api_key") or ODDS_API_KEY or "").strip()


def render_settings_sidebar(books_seen: list[str]) -> dict:
    cfg = settings()
    with st.sidebar.expander("⚙️ Odds & bankroll settings", expanded=False):
        key = st.text_input("Odds API key", value=api_key(), type="password",
                            help="Free key at the-odds-api.com. Or put ODDS_API_KEY in .env.")
        st.session_state["odds_api_key"] = key.strip()
        cfg["sample"] = st.toggle("Use sample odds (no key, no credits)", value=cfg["sample"])
        cfg["regions"] = st.multiselect("Book regions", list(REGION_HELP), default=cfg["regions"],
                                        format_func=lambda r: f"{r}: {REGION_HELP[r]}") or ["us"]
        cfg["markets"] = st.multiselect("Markets", ["h2h", "totals", "spreads"], default=cfg["markets"],
                                        format_func=lambda m: {"h2h": "Moneyline", "totals": "Totals", "spreads": "Puck line"}[m]) or ["h2h"]
        cost = len(cfg["regions"]) * len(cfg["markets"])
        cfg["refresh_min"] = st.slider("Reuse odds for (minutes)", 1, 120, int(cfg["refresh_min"]),
                                       help="Clicking around reuses saved odds instead of spending credits.")
        st.caption(f"Each refresh costs **{cost} credits**. Free tier: 500/month ≈ {500 // cost} refreshes.")
        options = sorted(set(books_seen) | set(cfg["my_books"]))
        cfg["my_books"] = st.multiselect("My books (where you can actually bet)", options, default=cfg["my_books"],
                                         help="Leave empty to show every book.")
        cfg["bankroll"] = st.number_input("Bankroll ($)", min_value=0.0, value=float(cfg["bankroll"]), step=50.0)
        cfg["kelly"] = st.select_slider("Kelly fraction", [0.1, 0.25, 0.5, 1.0], value=cfg["kelly"],
                                        help="Quarter Kelly is the usual safe choice; full Kelly swings hard.")
        cfg["min_ev"] = st.slider("Min edge to show (%)", 0.0, 10.0, float(cfg["min_ev"]), 0.5)
        cfg["max_price"] = st.slider("Skip long shots above (decimal)", 2.0, 15.0, float(cfg["max_price"]), 0.5)
        cfg["tz"] = st.text_input("Time zone", cfg["tz"])
    save_settings(cfg)
    return cfg


def load_odds(force: bool = False):
    """Returns (games, error, fetched_at). Respects sample mode and the reuse window."""
    cfg = settings()
    if cfg["sample"]:
        data = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
        # slide the sample slate to tonight so times look real
        base = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        for i, g in enumerate(data):
            g["commence_time"] = (base + timedelta(minutes=30 * i)).isoformat().replace("+00:00", "Z")
        return parse_games(data), None, time.time()
    return fetch_nhl_odds_cached(
        regions=",".join(cfg["regions"]), markets=",".join(cfg["markets"]), api_key=api_key() or None,
        max_age_s=int(cfg["refresh_min"]) * 60, force=force,
    )


def quota_text() -> str:
    if settings()["sample"]:
        return "sample odds"
    r = QUOTA.get("remaining")
    return f"{r} credits left" if r is not None else "credits: unknown until first pull"


def local_time(iso: str, fmt: str = "%a %-I:%M %p") -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        tz = ZoneInfo(settings()["tz"])
    except Exception:
        return iso
    out = dt.astimezone(tz)
    try:
        return out.strftime(fmt)
    except ValueError:  # Windows has no %-I
        return out.strftime(fmt.replace("%-", "%#"))


def ago(ts: float) -> str:
    if not ts:
        return "never"
    m = int((time.time() - ts) // 60)
    return "just now" if m < 1 else f"{m} min ago" if m < 90 else f"{m // 60} h ago"
