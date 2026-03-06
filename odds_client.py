"""The Odds API client for NHL betting odds."""
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

from config import ODDS_API_BASE, ODDS_API_KEY

logger = logging.getLogger(__name__)


@dataclass
class OddsMarket:
    key: str  # h2h, spreads, totals
    last_update: str
    outcomes: list[dict] = field(default_factory=list)


@dataclass
class GameOdds:
    id: str
    home_team: str
    away_team: str
    commence_time: str
    bookmakers: list[dict] = field(default_factory=list)  # name + markets


def fetch_nhl_odds(
    regions: str = "us",
    markets: str = "h2h,spreads,totals",
    api_key: Optional[str] = None,
) -> tuple[list[GameOdds], Optional[str]]:
    """
    Fetch NHL odds from The Odds API.
    Returns (list of GameOdds, error_message).
    Free tier: 500 requests/month. Each call costs 1 request for odds.
    api_key: optional override; otherwise uses ODDS_API_KEY from config/.env.
    """
    key = (api_key or "").strip() or ODDS_API_KEY
    if not key:
        return [], "Set your Odds API key in the sidebar or in .env (get a free key at https://the-odds-api.com/)"

    url = f"{ODDS_API_BASE}/sports/icehockey_nhl/odds"
    params = {
        "apiKey": key,
        "regions": regions,
        "markets": markets,
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        # Odds API returns 401 for invalid key, 429 for over limit
        if r.status_code == 401:
            return [], "Invalid ODDS_API_KEY. Check your key at the-odds-api.com."
        if r.status_code == 429:
            return [], "Odds API rate limit reached (free tier: 500 req/month)."
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        logger.warning("Odds API request failed: %s", e)
        return [], str(e)

    games: list[GameOdds] = []
    for g in data:
        try:
            games.append(
                GameOdds(
                    id=g.get("id", ""),
                    home_team=g.get("home_team", ""),
                    away_team=g.get("away_team", ""),
                    commence_time=g.get("commence_time", ""),
                    bookmakers=g.get("bookmakers", []),
                )
            )
        except (KeyError, TypeError):
            continue
    return games, None


def match_odds_to_game(
    odds_list: list[GameOdds],
    home_team_name: str,
    away_team_name: str,
) -> Optional[GameOdds]:
    """Find odds for a matchup by team names (flexible match)."""
    home_lower = (home_team_name or "").lower()
    away_lower = (away_team_name or "").lower()
    # API often uses "Team Name" or "City Name" - match on partial
    for o in odds_list:
        o_h = (o.home_team or "").lower()
        o_a = (o.away_team or "").lower()
        if (home_lower in o_h or o_h in home_lower) and (
            away_lower in o_a or o_a in away_lower
        ):
            return o
        if (home_lower in o_a or o_a in home_lower) and (
            away_lower in o_h or o_h in away_lower
        ):
            return o
    return None
