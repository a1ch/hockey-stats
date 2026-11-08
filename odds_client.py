"""The Odds API client for NHL betting odds."""
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

from config import DATA_DIR, ODDS_API_BASE, ODDS_API_KEY

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


# Last known quota from response headers (The Odds API sends these on every call)
QUOTA: dict = {"remaining": None, "used": None, "last_cost": None}
CACHE_FILE = DATA_DIR / "odds_cache.json"


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
    key = ((api_key or "").strip() or (ODDS_API_KEY or "").strip()) or ""
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
        for h, k in (("x-requests-remaining", "remaining"), ("x-requests-used", "used"), ("x-requests-last", "last_cost")):
            if r.headers.get(h) is not None:
                QUOTA[k] = r.headers.get(h)
    except requests.RequestException as e:
        logger.warning("Odds API request failed: %s", e)
        return [], str(e)

    return parse_games(data), None


def parse_games(data: list) -> list[GameOdds]:
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
    return games


def fetch_nhl_odds_cached(
    regions: str = "us",
    markets: str = "h2h,spreads,totals",
    api_key: Optional[str] = None,
    max_age_s: int = 600,
    force: bool = False,
) -> tuple[list[GameOdds], Optional[str], float]:
    """
    Same as fetch_nhl_odds but reuses a saved copy for max_age_s seconds, so clicking
    around the app doesn't burn your monthly quota. Every fresh pull is also saved
    as a snapshot for line-movement history. Returns (games, error, fetched_at epoch).
    Each fresh pull costs (number of markets x number of regions) credits.
    """
    cache_key = f"{regions}|{markets}"
    cache: dict = {}
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
    hit = cache.get(cache_key)
    if hit and not force and time.time() - hit.get("at", 0) < max_age_s:
        QUOTA.update(hit.get("quota") or {})
        return parse_games(hit["data"]), None, hit["at"]

    key = ((api_key or "").strip() or (ODDS_API_KEY or "").strip()) or ""
    if not key:
        if hit:  # no key but we have old data: show it
            return parse_games(hit["data"]), "No API key set; showing the last saved odds.", hit["at"]
        return [], "Set your Odds API key in the sidebar or in .env (get a free key at https://the-odds-api.com/)", 0.0
    try:
        r = requests.get(
            f"{ODDS_API_BASE}/sports/icehockey_nhl/odds",
            params={"apiKey": key, "regions": regions, "markets": markets, "oddsFormat": "decimal"},
            timeout=20,
        )
        if r.status_code == 401:
            return [], "Invalid ODDS_API_KEY. Check your key at the-odds-api.com.", 0.0
        if r.status_code == 429 or (r.status_code == 422 and "quota" in r.text.lower()):
            if hit:
                return parse_games(hit["data"]), "Out of Odds API credits this month; showing the last saved odds.", hit["at"]
            return [], "Odds API quota used up for this month.", 0.0
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        logger.warning("Odds API request failed: %s", e)
        if hit:
            return parse_games(hit["data"]), f"Odds API unreachable ({e}); showing the last saved odds.", hit["at"]
        return [], str(e), 0.0
    for h, k in (("x-requests-remaining", "remaining"), ("x-requests-used", "used"), ("x-requests-last", "last_cost")):
        if r.headers.get(h) is not None:
            QUOTA[k] = r.headers.get(h)
    now = time.time()
    cache[cache_key] = {"at": now, "data": data, "quota": dict(QUOTA)}
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
        from history import save_snapshot
        save_snapshot(data, now)
    except OSError as e:
        logger.warning("Could not save odds cache: %s", e)
    return parse_games(data), None, now


def _norm(name: Optional[str]) -> str:
    """Lowercase, strip accents and dots so 'Montréal Canadiens' matches 'Montreal Canadiens'."""
    import unicodedata
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return n.lower().replace(".", "").strip()


def match_odds_to_game(
    odds_list: list[GameOdds],
    home_team_name: str,
    away_team_name: str,
) -> Optional[GameOdds]:
    """Find odds for a matchup by team names (flexible match)."""
    home_lower = _norm(home_team_name)
    away_lower = _norm(away_team_name)
    # API often uses "Team Name" or "City Name" - match on partial
    for o in odds_list:
        o_h = _norm(o.home_team)
        o_a = _norm(o.away_team)
        if (home_lower in o_h or o_h in home_lower) and (
            away_lower in o_a or o_a in away_lower
        ):
            return o
        if (home_lower in o_a or o_a in home_lower) and (
            away_lower in o_h or o_h in away_lower
        ):
            return o
    return None


def find_hedge_opportunities(game_odds: Optional[GameOdds]) -> list[dict]:
    """
    Find moneyline hedges: bet home at one book and away at another so you profit either way.
    Returns list of {book_home, book_away, home_odds, away_odds, stake_pct_home, stake_pct_away, profit_pct}.
    Decimal odds: implied prob = 1/odds. Hedge exists when 1/O_h + 1/O_a < 1.
    """
    if not game_odds or not game_odds.bookmakers:
        return []
    home_name = (game_odds.home_team or "").strip()
    away_name = (game_odds.away_team or "").strip()
    # Per book: get h2h home and away decimal price
    book_prices: list[tuple[str, float, float]] = []  # (book_title, home_price, away_price)
    for bm in game_odds.bookmakers:
        h2h = next((m for m in bm.get("markets", []) if m.get("key") == "h2h"), None)
        if not h2h:
            continue
        outcomes = h2h.get("outcomes", [])
        home_price = away_price = None
        for o in outcomes:
            try:
                price = float(o.get("price") or 0)
            except (TypeError, ValueError):
                continue
            name = (o.get("name") or "").strip()
            if name == home_name or (home_name and home_name in name):
                home_price = price
            if name == away_name or (away_name and away_name in name):
                away_price = price
        if home_price and away_price and home_price > 0 and away_price > 0:
            book_prices.append((bm.get("title", "Unknown"), home_price, away_price))

    hedges: list[dict] = []
    for i, (book_a, h_a, a_a) in enumerate(book_prices):
        for j, (book_b, h_b, a_b) in enumerate(book_prices):
            # Bet home at book_a, away at book_b
            o_h, o_a = h_a, a_b
            implied = 1 / o_h + 1 / o_a
            if implied >= 1:
                continue
            # Stake split: stake home = (1/o_h) / (1/o_h + 1/o_a), stake away = (1/o_a) / (...)
            total_inv = 1 / o_h + 1 / o_a
            stake_home = (1 / o_h) / total_inv
            stake_away = (1 / o_a) / total_inv
            # Return per unit staked = 1/total_inv (same either outcome)
            profit_pct = (1 / total_inv - 1) * 100
            hedges.append({
                "book_home": book_a,
                "book_away": book_b,
                "home_odds": o_h,
                "away_odds": o_a,
                "stake_pct_home": stake_home * 100,
                "stake_pct_away": stake_away * 100,
                "profit_pct": profit_pct,
            })
            # Also check: bet away at book_a, home at book_b
            if i != j:
                o_h2, o_a2 = h_b, a_a
                implied2 = 1 / o_h2 + 1 / o_a2
                if implied2 < 1:
                    total_inv2 = 1 / o_h2 + 1 / o_a2
                    stake_home2 = (1 / o_h2) / total_inv2
                    stake_away2 = (1 / o_a2) / total_inv2
                    profit_pct2 = (1 / total_inv2 - 1) * 100
                    hedges.append({
                        "book_home": book_b,
                        "book_away": book_a,
                        "home_odds": o_h2,
                        "away_odds": o_a2,
                        "stake_pct_home": stake_home2 * 100,
                        "stake_pct_away": stake_away2 * 100,
                        "profit_pct": profit_pct2,
                    })
    # Dedupe and sort by profit desc
    seen = set()
    unique = []
    for h in hedges:
        key = (h["book_home"], h["book_away"], round(h["home_odds"], 4), round(h["away_odds"], 4))
        if key not in seen:
            seen.add(key)
            unique.append(h)
    unique.sort(key=lambda x: -x["profit_pct"])
    return unique
