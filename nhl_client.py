"""NHL API client (api-web.nhle.com): schedule, rosters, standings."""
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import requests

from config import NHL_API_BASE, NHL_STATS_REST_BASE

logger = logging.getLogger(__name__)


@dataclass
class Team:
    id: int
    name: str
    abbreviation: str
    venue_name: str


@dataclass
class Player:
    id: int
    name: str
    position: str
    jersey_number: Optional[str]
    roster_status: str  # Y = active, I = injured, etc.


@dataclass
class Game:
    id: int
    date: str
    home_team: Team
    away_team: Team
    state: str
    venue: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None


@dataclass
class MatchupRoster:
    team: Team
    players: list[Player] = field(default_factory=list)
    scratches: list[Player] = field(default_factory=list)


def _get(path: str) -> dict:
    url = f"{NHL_API_BASE}{path}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.warning("NHL API request failed: %s", e)
        return {}


def _team_from_api(t: dict) -> Team:
    """Build Team from new API team blob (placeName + commonName, abbrev)."""
    place = (t.get("placeName") or {}).get("default", "")
    common = (t.get("commonName") or {}).get("default", "")
    name = f"{place} {common}".strip() or "Unknown"
    abbrev = t.get("abbrev", "")
    return Team(
        id=t.get("id", 0),
        name=name,
        abbreviation=abbrev,
        venue_name="",
    )


def get_schedule(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    team_id: Optional[int] = None,
) -> list[Game]:
    """Fetch NHL schedule. Uses api-web.nhle.com/v1/schedule/{date} (one day per request)."""
    games: list[Game] = []
    start = start_date or date.today()
    end = end_date or start
    if team_id:
        # New API doesn't filter by team in URL; we could filter after
        pass
    current = start
    while current <= end:
        data = _get(f"/schedule/{current.isoformat()}")
        for week in data.get("gameWeek", []):
            day_date = week.get("date", current.isoformat())
            for g in week.get("games", []):
                try:
                    home = g.get("homeTeam", {})
                    away = g.get("awayTeam", {})
                    venue = g.get("venue") or {}
                    if isinstance(venue, dict):
                        venue_name = venue.get("default", "")
                    else:
                        venue_name = str(venue)
                    state = g.get("gameScheduleState", g.get("gameState", "Scheduled"))
                    if state == "OK" and g.get("gameState") == "OFF":
                        state = "Scheduled"
                    games.append(
                        Game(
                            id=g.get("id", 0),
                            date=day_date,
                            home_team=_team_from_api(home),
                            away_team=_team_from_api(away),
                            state=state,
                            venue=venue_name,
                            home_score=home.get("score"),
                            away_score=away.get("score"),
                        )
                    )
                except (KeyError, TypeError) as e:
                    logger.debug("Skip game parse: %s", e)
                    continue
        if current >= end:
            break
        current = current + timedelta(days=1)
    if team_id and games:
        games = [gm for gm in games if gm.home_team.id == team_id or gm.away_team.id == team_id]
    return games


def get_team_roster_by_abbrev(team_abbrev: str) -> list[Player]:
    """Get current roster for a team by abbreviation (e.g. VGK). All listed players treated as active."""
    if not team_abbrev:
        return []
    data = _get(f"/roster/{team_abbrev.upper()}/current")
    players: list[Player] = []
    for group in ("forwards", "defensemen", "goalies"):
        for entry in data.get(group, []):
            first = (entry.get("firstName") or {}).get("default", "")
            last = (entry.get("lastName") or {}).get("default", "")
            name = f"{first} {last}".strip() or "Unknown"
            players.append(
                Player(
                    id=entry.get("id", 0),
                    name=name,
                    position=entry.get("positionCode", "?"),
                    jersey_number=str(entry.get("sweaterNumber", "")) or None,
                    roster_status="Y",
                )
            )
    return players


def get_standings() -> dict[str, dict]:
    """Return teamAbbrev -> {wins, losses, points, ...}. Key is abbreviation for new API."""
    data = _get("/standings/now")
    out: dict[str, dict] = {}
    for row in data.get("standings", []):
        abbrev = (row.get("teamAbbrev") or {}).get("default")
        if not abbrev:
            continue
        out[abbrev] = {
            "wins": row.get("wins", 0),
            "losses": row.get("losses", 0),
            "ot": row.get("otLosses", 0),
            "points": row.get("points", 0),
            "divisionRank": row.get("divisionSequence"),
            "leagueRank": row.get("leagueSequence"),
            "goalsAgainst": row.get("goalAgainst"),
            "goalsScored": row.get("goalFor"),
        }
    return out


def get_rosters_for_matchup(
    home_team: Team,
    away_team: Team,
    season: Optional[str] = None,
) -> tuple[MatchupRoster, MatchupRoster]:
    """Get both teams' rosters. New API has no injury status; all roster players are active."""
    home_roster = get_team_roster_by_abbrev(home_team.abbreviation)
    away_roster = get_team_roster_by_abbrev(away_team.abbreviation)
    # New API only returns current roster; no scratches/injured list
    return (
        MatchupRoster(team=home_team, players=home_roster, scratches=[]),
        MatchupRoster(team=away_team, players=away_roster, scratches=[]),
    )


# Legacy helpers so callers using old API shape still work
def get_team_roster(team_id: int, season: Optional[str] = None) -> list[Player]:
    """Roster by team id not supported in new API; need abbrev. Returns [] unless you use get_rosters_for_matchup."""
    return []


def get_team(team_id: int) -> Optional[Team]:
    """Single-team lookup not in new API; build Team from schedule/standings instead."""
    return None


def get_game_boxscore(game_id: int) -> Optional[dict]:
    """Boxscore not used in new flow; return None."""
    return None


def get_team_pp_pk(season_id: str = "20252026") -> dict[int, dict]:
    """
    Fetch PP% and PK% for all teams from NHL Stats REST API.
    Returns dict[team_id, {"pp_pct": float, "pk_pct": float, "teamFullName": str}].
    """
    url = f"{NHL_STATS_REST_BASE}/team/summary"
    params = {
        "sort": "powerPlayPct",
        "dir": "DESC",
        "cayenneExp": f"gameTypeId=2 and seasonId={season_id}",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        logger.warning("NHL Stats REST request failed: %s", e)
        return {}
    out: dict[int, dict] = {}
    for row in data.get("data", []):
        tid = row.get("teamId")
        if tid is None:
            continue
        pp = row.get("powerPlayPct")
        pk = row.get("penaltyKillPct")
        out[tid] = {
            "pp_pct": float(pp) if pp is not None else None,
            "pk_pct": float(pk) if pk is not None else None,
            "teamFullName": row.get("teamFullName", ""),
        }
    return out


@dataclass
class RestContext:
    """Rest/travel context for one team going into a game."""
    days_rest: int
    last_game_date: Optional[str]
    last_venue: Optional[str]
    back_to_back: bool
    traveled_from: Optional[str]  # set if back-to-back and last game was away


def get_player_landing(player_id: int) -> Optional[dict]:
    """Fetch player landing page (info, featured stats, etc.)."""
    data = _get(f"/player/{player_id}/landing")
    return data if data else None


def get_player_game_log(player_id: int, season_id: int = 20242025, game_type_id: int = 2) -> list[dict]:
    """
    Fetch player game log for a season.
    Returns list of games with opponentAbbrev, goals, assists, points, etc.
    """
    data = _get(f"/player/{player_id}/game-log/{season_id}/{game_type_id}")
    return data.get("gameLog", []) if data else []


def get_player_stats_vs_opponents(
    player_id: int,
    opponent_abbrevs: list[str],
    seasons: Optional[list[int]] = None,
    game_type_id: int = 2,
) -> dict[str, dict]:
    """
    Aggregate player stats vs specific opponent teams from game logs.
    Returns {opponent_abbrev: {"games": N, "goals": N, "assists": N, "points": N, "season_id": last_season}}.
    Uses last 2 seasons by default.
    """
    if seasons is None:
        # Current and prior season (format: 20242025 = 2024-25)
        from datetime import date
        d = date.today()
        y = d.year
        current = (y - 1) * 10000 + y if d.month < 10 else y * 10000 + (y + 1)
        prior = current - 10001
        seasons = [current, prior]
    abbrevs = {a.upper() for a in opponent_abbrevs if a}
    out: dict[str, dict] = {abbrev: {"games": 0, "goals": 0, "assists": 0, "points": 0} for abbrev in abbrevs}
    for season_id in seasons:
        log = get_player_game_log(player_id, season_id, game_type_id)
        for g in log:
            opp = (g.get("opponentAbbrev") or "").upper()
            if opp not in abbrevs:
                continue
            row = out.get(opp)
            if not row:
                out[opp] = {"games": 0, "goals": 0, "assists": 0, "points": 0}
            out[opp]["games"] += 1
            out[opp]["goals"] += g.get("goals", 0) or 0
            out[opp]["assists"] += g.get("assists", 0) or 0
            out[opp]["points"] += g.get("points", 0) or 0
    return out


def get_rest_context(
    game_date: date,
    home_team_id: int,
    away_team_id: int,
) -> dict[str, RestContext]:
    """
    For a game on game_date, find each team's last game in the prior 10 days.
    Returns {"home": RestContext, "away": RestContext}.
    Back-to-back = 0 days rest. traveled_from = last game's venue when team was away.
    """
    out: dict[str, RestContext] = {}
    for label, team_id in [("home", home_team_id), ("away", away_team_id)]:
        days_rest = 999
        last_date: Optional[str] = None
        last_venue: Optional[str] = None
        was_away = False
        for d in range(1, 11):
            check = game_date - timedelta(days=d)
            day_games = get_schedule(start_date=check, end_date=check)
            for g in day_games:
                if g.home_team.id == team_id:
                    days_rest = d
                    last_date = g.date
                    last_venue = g.venue
                    was_away = False
                    break
                if g.away_team.id == team_id:
                    days_rest = d
                    last_date = g.date
                    last_venue = g.venue
                    was_away = True
                    break
            if last_date is not None:
                break
        if last_date is None:
            days_rest = 999
        # Back-to-back = played the day before (1 day rest)
        out[label] = RestContext(
            days_rest=days_rest,
            last_game_date=last_date,
            last_venue=last_venue,
            back_to_back=(days_rest == 1),
            traveled_from=last_venue if (days_rest == 1 and was_away) else None,
        )
    return out
