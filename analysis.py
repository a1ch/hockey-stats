"""Compare matchup (rosters, standings, news) to betting odds and produce insights."""
from dataclasses import dataclass, field
from typing import Optional

from nhl_client import Game, MatchupRoster, RestContext, get_standings, get_team_pp_pk
from odds_client import GameOdds


@dataclass
class MatchupInsight:
    title: str
    body: str
    sentiment: str  # "favor_home", "favor_away", "neutral", "caution"
    confidence: str = "medium"  # "low", "medium", "high" for edge strength


def roster_insights(
    home: MatchupRoster,
    away: MatchupRoster,
) -> list[MatchupInsight]:
    """Insights from roster status (injuries, scratches)."""
    insights: list[MatchupInsight] = []
    h_inactive = len(home.scratches)
    a_inactive = len(away.scratches)
    if h_inactive > a_inactive + 2:
        insights.append(
            MatchupInsight(
                title="More key absences for home team",
                body=f"{home.team.name} has {h_inactive} players not on active roster vs {away.team.name}'s {a_inactive}. Lineup depth may favor the road team.",
                sentiment="favor_away",
            )
        )
    elif a_inactive > h_inactive + 2:
        insights.append(
            MatchupInsight(
                title="More key absences for away team",
                body=f"{away.team.name} has {a_inactive} players not on active roster vs {home.team.name}'s {h_inactive}. Home lineup looks healthier.",
                sentiment="favor_home",
            )
        )
    if home.scratches or away.scratches:
        names_h = ", ".join(p.name for p in home.scratches[:5])
        names_a = ", ".join(p.name for p in away.scratches[:5])
        if home.scratches:
            insights.append(
                MatchupInsight(
                    title=f"{home.team.name} non-active",
                    body=names_h + (" ..." if len(home.scratches) > 5 else ""),
                    sentiment="neutral",
                )
            )
        if away.scratches:
            insights.append(
                MatchupInsight(
                    title=f"{away.team.name} non-active",
                    body=names_a + (" ..." if len(away.scratches) > 5 else ""),
                    sentiment="neutral",
                )
            )
    return insights


def rest_insights(
    game: Game,
    rest_context: dict[str, RestContext],
) -> list[MatchupInsight]:
    """Rest advantage and back-to-back / travel fatigue."""
    insights: list[MatchupInsight] = []
    home_rest = rest_context.get("home")
    away_rest = rest_context.get("away")
    if not home_rest or not away_rest:
        return insights
    # Rest advantage
    if home_rest.days_rest != 999 and away_rest.days_rest != 999:
        diff = home_rest.days_rest - away_rest.days_rest
        if diff >= 2:
            insights.append(
                MatchupInsight(
                    title="Rest advantage: home",
                    body=f"{game.home_team.name} has {home_rest.days_rest} days rest vs {away_rest.days_rest} for {game.away_team.name}. Rest edge favors home.",
                    sentiment="favor_home",
                    confidence="high",
                )
            )
        elif diff <= -2:
            insights.append(
                MatchupInsight(
                    title="Rest advantage: away",
                    body=f"{game.away_team.name} has {away_rest.days_rest} days rest vs {home_rest.days_rest} for {game.home_team.name}. Rest edge favors away.",
                    sentiment="favor_away",
                    confidence="high",
                )
            )
    # Back-to-back and travel
    if home_rest.back_to_back:
        travel = f" (flew in from {home_rest.traveled_from})" if home_rest.traveled_from else ""
        insights.append(
            MatchupInsight(
                title=f"{game.home_team.name} on back-to-back",
                body=f"Home team played yesterday{travel}. Fatigue risk.",
                sentiment="favor_away",
                confidence="high",
            )
        )
    if away_rest.back_to_back:
        travel = f" (flew in from {away_rest.traveled_from})" if away_rest.traveled_from else ""
        insights.append(
            MatchupInsight(
                title=f"{game.away_team.name} on back-to-back",
                body=f"Away team played yesterday{travel}. Fatigue risk.",
                sentiment="favor_home",
                confidence="high",
            )
        )
    return insights


def pp_pk_insights(
    game: Game,
    pp_pk_by_team: dict[int, dict],
) -> list[MatchupInsight]:
    """Power play and penalty kill rankings — big for handicapping."""
    insights: list[MatchupInsight] = []
    home_rec = pp_pk_by_team.get(game.home_team.id)
    away_rec = pp_pk_by_team.get(game.away_team.id)
    if not home_rec or not away_rec:
        return insights
    home_pp = home_rec.get("pp_pct")
    home_pk = home_rec.get("pk_pct")
    away_pp = away_rec.get("pp_pct")
    away_pk = away_rec.get("pk_pct")
    if home_pp is not None and away_pp is not None:
        pp_diff = home_pp - away_pp
        if pp_diff >= 0.05:
            insights.append(
                MatchupInsight(
                    title="Power play edge: home",
                    body=f"{game.home_team.name} PP {home_pp:.1%} vs {game.away_team.name} {away_pp:.1%}. Home has the special-teams edge on the man advantage.",
                    sentiment="favor_home",
                    confidence="medium",
                )
            )
        elif pp_diff <= -0.05:
            insights.append(
                MatchupInsight(
                    title="Power play edge: away",
                    body=f"{game.away_team.name} PP {away_pp:.1%} vs {game.home_team.name} {home_pp:.1%}. Away has the PP edge.",
                    sentiment="favor_away",
                    confidence="medium",
                )
            )
    if home_pk is not None and away_pk is not None:
        pk_diff = home_pk - away_pk
        if pk_diff >= 0.05:
            insights.append(
                MatchupInsight(
                    title="Penalty kill edge: home",
                    body=f"{game.home_team.name} PK {home_pk:.1%} vs {game.away_team.name} {away_pk:.1%}. Home kills penalties better.",
                    sentiment="favor_home",
                    confidence="medium",
                )
            )
        elif pk_diff <= -0.05:
            insights.append(
                MatchupInsight(
                    title="Penalty kill edge: away",
                    body=f"{game.away_team.name} PK {away_pk:.1%} vs {game.home_team.name} {home_pk:.1%}. Away PK edge.",
                    sentiment="favor_away",
                    confidence="medium",
                )
            )
    # One-line summary if we have both
    if home_pp is not None and away_pp is not None and home_pk is not None and away_pk is not None:
        insights.append(
            MatchupInsight(
                title="Special teams summary",
                body=f"Home PP {home_pp:.1%} / PK {home_pk:.1%} · Away PP {away_pp:.1%} / PK {away_pk:.1%}.",
                sentiment="neutral",
                confidence="low",
            )
        )
    return insights


def standings_insights(
    game: Game,
) -> list[MatchupInsight]:
    """Insights from standings (points, rank)."""
    standings = get_standings()
    insights: list[MatchupInsight] = []
    home_rec = standings.get(game.home_team.abbreviation)
    away_rec = standings.get(game.away_team.abbreviation)
    if not home_rec or not away_rec:
        return insights
    home_pts = home_rec.get("points") or 0
    away_pts = away_rec.get("points") or 0
    diff = home_pts - away_pts
    if diff >= 10:
        insights.append(
            MatchupInsight(
                title="Standings favor home",
                body=f"{game.home_team.name} has {diff} more points than {game.away_team.name}. Odds may already reflect this.",
                sentiment="favor_home",
            )
        )
    elif diff <= -10:
        insights.append(
            MatchupInsight(
                title="Standings favor away",
                body=f"{game.away_team.name} has {-diff} more points than {game.home_team.name}. Odds may already reflect this.",
                sentiment="favor_away",
            )
        )
    return insights


def odds_insights(
    game: Game,
    odds: Optional[GameOdds],
) -> list[MatchupInsight]:
    """Summarize odds and highlight value vs narrative (e.g. big favorite with injuries)."""
    insights: list[MatchupInsight] = []
    if not odds or not odds.bookmakers:
        return insights
    # Use first bookmaker for simple summary
    for bm in odds.bookmakers[:1]:
        for market in bm.get("markets", []):
            if market.get("key") != "h2h":
                continue
            outcomes = market.get("outcomes", [])
            home_out = next((o for o in outcomes if o.get("name") == odds.home_team), None)
            away_out = next((o for o in outcomes if o.get("name") == odds.away_team), None)
            if home_out and away_out:
                try:
                    home_dec = float(home_out.get("price", 0))
                    away_dec = float(away_out.get("price", 0))
                    # Implied prob from decimal odds: 1/price
                    home_impl = 100 / home_dec if home_dec else 0
                    away_impl = 100 / away_dec if away_dec else 0
                    fav = "home" if home_impl >= away_impl else "away"
                    insights.append(
                        MatchupInsight(
                            title=f"Moneyline ({bm.get('title', 'Sportsbook')})",
                            body=f"Home {home_dec:.2f} ({home_impl:.0f}% implied) · Away {away_dec:.2f} ({away_impl:.0f}% implied). Favorite: {odds.home_team if fav == 'home' else odds.away_team}.",
                            sentiment="neutral",
                        )
                    )
                except (TypeError, ZeroDivisionError):
                    pass
            break
    return insights


def build_comparison_summary(
    game: Game,
    home_roster: MatchupRoster,
    away_roster: MatchupRoster,
    odds: Optional[GameOdds],
    rest_context: Optional[dict[str, RestContext]] = None,
    pp_pk_by_team: Optional[dict[int, dict]] = None,
) -> list[MatchupInsight]:
    """Combine rest, PP/PK, standings, roster, and odds into one ordered list of insights."""
    out: list[MatchupInsight] = []
    if rest_context:
        out.extend(rest_insights(game, rest_context))
    if pp_pk_by_team:
        out.extend(pp_pk_insights(game, pp_pk_by_team))
    out.extend(standings_insights(game))
    out.extend(roster_insights(home_roster, away_roster))
    out.extend(odds_insights(game, odds))
    return out


def get_best_bet_and_confidence(
    game: Game,
    home_roster: MatchupRoster,
    away_roster: MatchupRoster,
    odds: Optional[GameOdds],
    rest_context: Optional[dict[str, RestContext]] = None,
) -> tuple[str, str]:
    """
    Simple heuristic best bet (moneyline lean) and overall confidence.
    Returns (recommendation_text, confidence "low"|"medium"|"high").
    """
    factors_home = 0
    factors_away = 0
    standings = get_standings()
    home_rec = standings.get(game.home_team.abbreviation) or {}
    away_rec = standings.get(game.away_team.abbreviation) or {}
    home_pts = home_rec.get("points") or 0
    away_pts = away_rec.get("points") or 0
    if home_pts > away_pts + 5:
        factors_home += 1
    elif away_pts > home_pts + 5:
        factors_away += 1
    if rest_context:
        h = rest_context.get("home")
        a = rest_context.get("away")
        if h and a:
            if h.days_rest < a.days_rest and a.back_to_back:
                factors_home += 1
            elif a.days_rest < h.days_rest and h.back_to_back:
                factors_away += 1
            elif h.days_rest > a.days_rest + 1:
                factors_home += 1
            elif a.days_rest > h.days_rest + 1:
                factors_away += 1
    if len(home_roster.scratches) > len(away_roster.scratches) + 2:
        factors_away += 1
    elif len(away_roster.scratches) > len(home_roster.scratches) + 2:
        factors_home += 1
    total = factors_home + factors_away
    if total == 0:
        return "No clear edge from rest/standings/roster. Check odds and news.", "low"
    if factors_home >= 2 and factors_away == 0:
        return f"Lean: {game.home_team.name} ML (rest/standings/roster favor home).", "high"
    if factors_away >= 2 and factors_home == 0:
        return f"Lean: {game.away_team.name} ML (rest/standings/roster favor away).", "high"
    if factors_home > factors_away:
        return f"Slight lean: {game.home_team.name} ML.", "medium"
    if factors_away > factors_home:
        return f"Slight lean: {game.away_team.name} ML.", "medium"
    return "Factors split. No strong ML lean.", "low"
