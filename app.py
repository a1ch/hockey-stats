"""
Bettin Jimmy: news, lineups, and betting odds comparison.
Pick a game, see who's healthy, recent news, and how odds compare to the narrative.
"""
from pathlib import Path

from dotenv import load_dotenv

# Load .env before config so ODDS_API_KEY is available
load_dotenv(Path(__file__).resolve().parent / ".env")

from datetime import date, datetime, timedelta

import streamlit as st

from analysis import (
    build_comparison_summary,
    get_best_bet_and_confidence,
)
from news_client import NewsItem, fetch_nhl_news, filter_news_for_matchup
from nhl_client import (
    Game,
    get_player_landing,
    get_player_stats_vs_opponents,
    get_rest_context,
    get_rosters_for_matchup,
    get_schedule,
    get_team_pp_pk,
)
from config import APP_PASSWORD, ODDS_API_KEY, ON_AZURE
from odds_client import find_hedge_opportunities, match_odds_to_game
import scanner as sc
import ui_bets
import ui_scanner
from ui_common import load_odds, render_settings_sidebar, settings


def _read_odds_key_from_env() -> str:
    """Read ODDS_API_KEY from config or by parsing .env file (no session state)."""
    key = (ODDS_API_KEY or "").strip()
    if key:
        return key
    for base in [Path(__file__).resolve().parent, Path.cwd()]:
        env_path = base / ".env"
        if env_path.exists():
            try:
                text = env_path.read_text(encoding="utf-8-sig", errors="ignore")
            except Exception:
                continue
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("ODDS_API_KEY="):
                    val = line.split("=", 1)[1].strip()
                    if "#" in val:
                        val = val.split("#", 1)[0].strip()
                    val = val.strip('"').strip("'")
                    if val:
                        return val
    return ""


def _get_odds_api_key() -> str:
    """Odds API key: sidebar override, then .env/config."""
    key = (st.session_state.get("odds_api_key") or "").strip()
    if key:
        return key
    return _read_odds_key_from_env()

st.set_page_config(
    page_title="Bettin Jimmy",
    page_icon="🏒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Light styling: hockey feel with bright, readable text
st.markdown("""
<style>
    .stApp { background: linear-gradient(180deg, #0e1117 0%, #1a1d24 100%); }
    /* Top bar – deep blue */
    header[data-testid="stHeader"], .stApp > header { background: #0a1628 !important; }
    [data-testid="stToolbar"], [data-testid="stDecoration"] { background: #0a1628 !important; }
    /* Left sidebar – darker gray */
    section[data-testid="stSidebar"] > div, [data-testid="stSidebar"] { background: #15181d !important; }
    section[data-testid="stSidebar"] .stMarkdown { color: #e0e0e0 !important; }
    h1 { color: #f5f5f5; font-weight: 700; }
    h2, h3, h4 { color: #e8e8e8; }
    p, label, div[data-testid="stMarkdown"] { color: #e0e0e0 !important; }
    .stMarkdown p, .stMarkdown li { color: #e0e0e0 !important; }
    .stCaptionContainer { color: #c8c8c8 !important; }
    .matchup-card {
        background: #262730;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin: 0.5rem 0;
        border-left: 4px solid #4a9eff;
        color: #e0e0e0 !important;
    }
    .insight-favor-home { border-left-color: #4caf50; }
    .insight-favor-away { border-left-color: #ff9800; }
    .insight-caution { border-left-color: #f44336; }
    .news-item { background: #1e2128; border-radius: 8px; padding: 0.75rem 1rem; margin: 0.4rem 0; color: #e0e0e0; }
    div[data-testid="stMetric"] { background: #262730; padding: 0.5rem 1rem; border-radius: 8px; }
    div[data-testid="stMetric"] label { color: #c8c8c8 !important; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #ffffff !important; }
</style>
""", unsafe_allow_html=True)


# NHL team primary colors (official/primary brand)
TEAM_PRIMARY_COLORS = {
    "ANA": "#F47A38", "ARI": "#8C2633", "ATL": "#041E42", "BOS": "#FFB81C",
    "BUF": "#002654", "CGY": "#C8102E", "CAR": "#CC0000", "CHI": "#C8102E",
    "COL": "#6F263D", "CBJ": "#002654", "DAL": "#006847", "DET": "#C8102E",
    "EDM": "#FF4C00", "FLA": "#C8102E", "LAK": "#111111", "MIN": "#154734",
    "MTL": "#AF1E2D", "NJD": "#CE1126", "NSH": "#FFB81C", "NYI": "#F47D30",
    "NYR": "#0033A0", "OTT": "#C52032", "PHI": "#F74902", "PIT": "#000000",
    "SJS": "#006D75", "SEA": "#001628", "STL": "#002F87", "TBL": "#002868",
    "TOR": "#003E7E", "UTA": "#532E76", "VAN": "#00205B", "VGK": "#B4975A",
    "WSH": "#C8102E", "WPG": "#041E42",
}


def _parse_game_date(game_date: str) -> date:
    """Parse YYYY-MM-DD to date."""
    try:
        return datetime.strptime(game_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return date.today()


def render_sidebar() -> tuple[date, list[Game], Game | None]:
    """Date picker and game selector. Returns (selected_date, all_games_that_day, selected_game)."""
    st.sidebar.header("🏒 Select matchup")
    today = date.today()
    sel_date = st.sidebar.date_input(
        "Game date",
        value=today,
        min_value=today - timedelta(days=7),
        max_value=today + timedelta(days=14),
    )
    games = get_schedule(start_date=sel_date, end_date=sel_date)
    if not games:
        st.sidebar.info("No games scheduled for this date.")
        return sel_date, [], None
    options = [
        f"{g.away_team.name} @ {g.home_team.name} — {g.state}"
        for g in games
    ]
    idx = st.sidebar.selectbox(
        "Game",
        range(len(options)),
        format_func=lambda i: options[i],
    )
    return sel_date, games, games[idx] if 0 <= idx < len(games) else None


def render_news(news: list[NewsItem], limit: int = 10) -> None:
    for item in news[:limit]:
        with st.container():
            st.markdown(f"**[{item.title}]({item.link})**")
            if item.published:
                st.caption(item.published)
            if item.summary:
                st.markdown(item.summary[:400] + ("..." if len(item.summary) > 400 else ""))
            st.divider()


def _unlocked() -> bool:
    """Password gate for the hosted copy. Locally with no APP_PASSWORD it's open."""
    if not APP_PASSWORD:
        if ON_AZURE:
            st.error("Locked: set the APP_PASSWORD app setting in Azure first.")
            return False
        return True
    if st.session_state.get("unlocked"):
        return True
    st.title("🏒 Bettin Jimmy")
    pw = st.text_input("Password", type="password")
    if pw:
        import hmac
        if hmac.compare_digest(pw, APP_PASSWORD):
            st.session_state["unlocked"] = True
            st.rerun()
        st.error("Wrong password.")
    return False


def main() -> None:
    if not _unlocked():
        return
    page = st.sidebar.radio("Bettin Jimmy", ["🎯 Scanner", "🔍 Matchup", "📒 Bets"], label_visibility="collapsed")
    st.sidebar.divider()
    if page == "🎯 Scanner":
        ui_scanner.render()
    elif page == "📒 Bets":
        ui_bets.render()
    else:
        render_matchup()


def render_matchup() -> None:
    st.title("Bettin Jimmy")
    st.caption("Lineups, health, news, and betting odds in one place.")

    sel_date, all_games, game = render_sidebar()
    render_settings_sidebar([])
    if not game:
        st.info("Choose a date with games in the sidebar.")
        return

    # Multi-game view toggle
    view_all = st.checkbox("View all games tonight", value=False, key="view_all_games")
    if view_all and len(all_games) > 1:
        st.markdown("### All games tonight")
        for i, g in enumerate(all_games):
            with st.expander(f"{g.away_team.name} @ {g.home_team.name} — {g.venue}"):
                st.caption(f"{g.date} · {g.state}")
                st.write("Select a single game in the sidebar to see full insights, lineups, and odds.")
        st.divider()

    # Clear selected player if game changed
    if st.session_state.get("last_game_id") != game.id:
        st.session_state.pop("selected_player", None)
        st.session_state["last_game_id"] = game.id

    # Fetch data
    game_date = _parse_game_date(game.date)
    with st.spinner("Loading matchup data…"):
        rest_ctx = get_rest_context(game_date, game.home_team.id, game.away_team.id)
        pp_pk = get_team_pp_pk()
        home_roster, away_roster = get_rosters_for_matchup(
            game.home_team,
            game.away_team,
        )
        api_key = _get_odds_api_key().strip()
        odds_list, odds_error, _ = load_odds()
        game_odds = match_odds_to_game(
            odds_list,
            game.home_team.name,
            game.away_team.name,
        ) if odds_list else None
        if odds_list and not game_odds:
            odds_error = (
                f"Odds API returned {len(odds_list)} game(s) but none matched this matchup "
                f"({game.home_team.name} vs {game.away_team.name}). Team names may differ slightly."
            )
        all_news = fetch_nhl_news()
        matchup_news = filter_news_for_matchup(
            all_news,
            game.home_team.name,
            game.away_team.name,
            limit=15,
        )
        insights = build_comparison_summary(
            game, home_roster, away_roster, game_odds,
            rest_context=rest_ctx,
            pp_pk_by_team=pp_pk,
        )
        best_bet, edge_confidence = get_best_bet_and_confidence(
            game, home_roster, away_roster, game_odds, rest_context=rest_ctx
        )

    # Header: matchup and time
    st.subheader(f"{game.away_team.name} @ {game.home_team.name}")
    st.caption(f"{game.date} · {game.venue} · {game.state}")
    # Rest/travel one-liner
    rh, ra = rest_ctx.get("home"), rest_ctx.get("away")
    if rh and ra:
        parts = []
        if rh.days_rest != 999:
            parts.append(f"{game.home_team.abbreviation} {rh.days_rest}d rest" + (" (B2B)" if rh.back_to_back else ""))
        if ra.days_rest != 999:
            parts.append(f"{game.away_team.abbreviation} {ra.days_rest}d rest" + (" (B2B)" if ra.back_to_back else ""))
        if ra.traveled_from:
            parts.append(f"Away flew in from {ra.traveled_from}")
        if rh.traveled_from:
            parts.append(f"Home flew in from {rh.traveled_from}")
        if parts:
            st.caption(" · ".join(parts))

    # Metrics row: roster health
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            f"{game.home_team.name} active",
            len(home_roster.players),
            delta=f"{len(home_roster.scratches)} not active" if home_roster.scratches else None,
        )
    with col2:
        st.metric(
            f"{game.away_team.name} active",
            len(away_roster.players),
            delta=f"{len(away_roster.scratches)} not active" if away_roster.scratches else None,
        )
    with col3:
        if game_odds and game_odds.bookmakers:
            bm = game_odds.bookmakers[0]
            h2h = next((m for m in bm.get("markets", []) if m.get("key") == "h2h"), None)
            if h2h:
                parts = [f"{o['name']}: {o.get('price')}" for o in h2h.get("outcomes", [])]
                st.metric("Moneyline", " · ".join(parts) if parts else "—", delta=None)
            else:
                st.metric("Odds", "Available", delta=odds_error or None)
        else:
            st.metric("Odds", "—", delta=odds_error)
    with col4:
        st.metric("Relevant news", len(matchup_news), delta=None)

    # Tabs: Insights | Lineups | News | Odds
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Insights", "Lineups", "News", "Odds", "Export"])

    with tab1:
        st.markdown("### Comparison: lineup, rest & standings vs odds")
        # Confidence meter
        conf_color = {"high": "#4caf50", "medium": "#ff9800", "low": "#9e9e9e"}.get(edge_confidence, "#9e9e9e")
        st.markdown(
            f'<div style="background:#262730;border-radius:8px;padding:0.5rem 1rem;margin-bottom:1rem;">'
            f'<span style="color:#b0b0b0;">Edge confidence</span> '
            f'<span style="color:{conf_color};font-weight:bold;">{edge_confidence.upper()}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        # Best bet
        st.markdown(f"**Best bet** · {best_bet}")
        st.divider()
        for ins in insights:
            css = f"insight-{ins.sentiment}" if ins.sentiment != "neutral" else ""
            conf_badge = getattr(ins, "confidence", "medium")
            conf_c = {"high": "#4caf50", "medium": "#ff9800", "low": "#9e9e9e"}.get(conf_badge, "")
            badge = f'<span style="font-size:0.75rem;color:{conf_c};">[{conf_badge}]</span>' if conf_c else ""
            st.markdown(
                f'<div class="matchup-card {css}"><strong>{ins.title}</strong> {badge}<br>{ins.body}</div>',
                unsafe_allow_html=True,
            )
        if not insights:
            st.info("No insights yet. Odds and roster data will appear here.")
        # Placeholders for future data (see DATA_SOURCES.md)
        with st.expander("More context (coming soon)"):
            st.markdown("- **Referee** — Assignment and penalty tendencies (see DATA_SOURCES.md)")
            st.markdown("- **Public % vs sharp** — Betting splits (OddsJam, SharpAPI)")
            st.markdown("- **Reverse line movement** — Odds move vs public %")
            st.markdown("- **ATS record** — Historical against-the-spread (StatSharp or Odds API historical)")
            st.markdown("- **Situational trends** — e.g. home underdog record")

    with tab2:
        # Initialize selected player in session state
        if "selected_player" not in st.session_state:
            st.session_state["selected_player"] = None

        # Player stats panel - show at TOP when selected so it's visible without scrolling
        sel = st.session_state.get("selected_player")
        if sel:
            pid, pname, opp_abbrevs, pos = sel
            st.markdown("---")
            st.markdown(f"### 📊 {pname} — stats vs opponent")
            if st.button("← Back to roster", key="close_player_stats"):
                st.session_state["selected_player"] = None
                st.rerun()
            with st.spinner(f"Loading {pname}'s stats…"):
                landing = get_player_landing(pid)
                vs_stats = get_player_stats_vs_opponents(pid, opp_abbrevs)
            if landing:
                fs = landing.get("featuredStats", {}) or {}
                rs = (fs.get("regularSeason") or {}).get("subSeason") or fs.get("regularSeason", {}).get("career") or {}
                if rs:
                    st.markdown("**Season / career totals**")
                    st.write(
                        f"GP: {rs.get('gamesPlayed', '—')} · G: {rs.get('goals', '—')} · "
                        f"A: {rs.get('assists', '—')} · Pts: {rs.get('points', '—')}"
                    )
            st.markdown("**Goals vs opponent team** (last 2 seasons)")
            if vs_stats:
                for abbrev, row in vs_stats.items():
                    if row["games"] > 0:
                        g, a, pts = row["goals"], row["assists"], row["points"]
                        st.metric(
                            f"vs {abbrev}",
                            f"{g}G · {a}A · {pts}Pts in {row['games']} GP",
                            f"{g / row['games']:.2f} goals/game" if row["games"] else None,
                        )
            else:
                st.caption("No games vs this opponent in the last 2 seasons.")
            st.markdown("**Goals vs opponent goalie**")
            st.caption("Goalie-specific splits require play-by-play data. Coming in a future update.")
            st.markdown("---")
            st.markdown("#### Roster")

        # Style player buttons with team primary colors
        home_color = TEAM_PRIMARY_COLORS.get(game.home_team.abbreviation.upper(), "#4a9eff")
        away_color = TEAM_PRIMARY_COLORS.get(game.away_team.abbreviation.upper(), "#ff9800")
        st.markdown(f"""
        <style>
            div:has(#lineups-home-col) ~ * button,
            div:has(#lineups-home-col) ~ * button[kind="primary"] {{
                background-color: {home_color} !important;
                border-color: {home_color} !important;
                filter: brightness(1.5);
            }}
            div:has(#lineups-away-col) ~ * button,
            div:has(#lineups-away-col) ~ * button[kind="primary"] {{
                background-color: {away_color} !important;
                border-color: {away_color} !important;
                filter: brightness(1.5);
            }}
        </style>
        """, unsafe_allow_html=True)

        def _make_select_callback(pid: int, pname: str, opp_abbrevs: list[str], pos: str):
            def _on_click():
                st.session_state["selected_player"] = (pid, pname, opp_abbrevs, pos)
            return _on_click

        def _render_clickable_player(p, opponent_abbrevs: list[str], team_label: str) -> None:
            key = f"player_btn_{p.id}_{team_label}"
            label = f"#{p.jersey_number or '—'} {p.name} ({p.position})"
            st.button(
                label,
                key=key,
                help="Click to view stats vs opponent",
                type="primary",
                on_click=_make_select_callback(p.id, p.name, opponent_abbrevs, p.position),
            )

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"#### {game.home_team.name}")
            st.markdown("**Active roster** — *click a name for stats vs opponent*")
            st.markdown('<div id="lineups-home-col" style="display:none;"></div>', unsafe_allow_html=True)
            for p in home_roster.players:
                _render_clickable_player(p, [game.away_team.abbreviation], "home")
            if home_roster.scratches:
                st.markdown("**Not active**")
                for p in home_roster.scratches:
                    st.text(f"{p.name} ({p.position}) — status: {p.roster_status}")
        with c2:
            st.markdown(f"#### {game.away_team.name}")
            st.markdown("**Active roster** — *click a name for stats vs opponent*")
            st.markdown('<div id="lineups-away-col" style="display:none;"></div>', unsafe_allow_html=True)
            for p in away_roster.players:
                _render_clickable_player(p, [game.home_team.abbreviation], "away")
            if away_roster.scratches:
                st.markdown("**Not active**")
                for p in away_roster.scratches:
                    st.text(f"{p.name} ({p.position}) — status: {p.roster_status}")

    with tab3:
        st.markdown("### News mentioning either team")
        render_news(matchup_news)

    with tab4:
        if game_odds and game_odds.bookmakers:
            hedges = find_hedge_opportunities(game_odds)
            st.markdown("### 🛡️ Hedge opportunities (pays either way)")
            st.caption("Bet home at one book and away at another for guaranteed profit. Stake split locks in the same return either outcome.")
            if hedges:
                best = hedges[0]
                st.success(
                    f"**Best:** {best['book_home']} (home @ {best['home_odds']:.2f}) + {best['book_away']} (away @ {best['away_odds']:.2f}) "
                    f"→ **{best['profit_pct']:.2f}%** profit · Stake {best['stake_pct_home']:.1f}% / {best['stake_pct_away']:.1f}%"
                )
                if len(hedges) > 1:
                    with st.expander(f"All {len(hedges)} hedge(s)"):
                        for h in hedges:
                            st.markdown(
                                f"**{h['book_home']}** (home @ {h['home_odds']:.2f}) + **{h['book_away']}** (away @ {h['away_odds']:.2f}) "
                                f"→ **{h['profit_pct']:.2f}%** profit"
                            )
                            st.caption(f"Stake {h['stake_pct_home']:.1f}% on home, {h['stake_pct_away']:.1f}% on away.")
                st.divider()
            else:
                st.info("No hedge found for this game — implied odds across books don’t leave a guaranteed profit. Check back as lines move.")
                st.divider()
            mks = sc.build_markets([game_odds])
            edges = sc.find_ev(mks, settings()["min_ev"], settings()["kelly"], settings()["max_price"])
            st.markdown("### 💰 Prices that beat the fair line")
            if edges:
                for b in edges:
                    st.markdown(f"**{b.pick}** ({b.market}) at **{b.book}** {b.american} vs fair {sc.to_american(b.fair_price)} "
                                f"→ **+{b.ev_pct:.1f}%** edge")
            else:
                st.caption("None right now.")
            st.divider()
            st.markdown("### Odds by book")
            for bm in game_odds.bookmakers:
                st.markdown(f"**{bm.get('title', 'Book')}**")
                for market in bm.get("markets", []):
                    key = market.get("key", "")
                    name = {"h2h": "Moneyline", "spreads": "Spread", "totals": "Total"}.get(key, key)
                    st.markdown(f"*{name}*")
                    for o in market.get("outcomes", []):
                        st.text(f"  {o.get('name')}: {o.get('price')} {o.get('point', '')}".strip())
                st.divider()
        else:
            msg = odds_error or "Odds not available. Add ODDS_API_KEY to .env for live odds."
            st.warning(msg)
            if api_key and "Invalid" in (odds_error or ""):
                st.caption("Your key may be invalid or expired. Check the-odds-api.com and try a new key in the sidebar.")
            elif api_key and "rate limit" in (odds_error or "").lower():
                st.caption("Free tier allows 500 requests/month. Try again later.")

    with tab5:
        st.markdown("### Export pre-game notes")
        report_lines = [
            f"# {game.away_team.name} @ {game.home_team.name}",
            f"**Date:** {game.date} · **Venue:** {game.venue}",
            "",
            "## Rest & travel",
        ]
        if rh and ra:
            report_lines.append(f"- {game.home_team.name}: {rh.days_rest}d rest" + (" (back-to-back)" if rh.back_to_back else ""))
            report_lines.append(f"- {game.away_team.name}: {ra.days_rest}d rest" + (" (back-to-back)" if ra.back_to_back else ""))
            if ra.traveled_from:
                report_lines.append(f"- Away traveled from {ra.traveled_from}")
            if rh.traveled_from:
                report_lines.append(f"- Home traveled from {rh.traveled_from}")
        report_lines.extend(["", "## Best bet", best_bet, "", "## Insights"])
        for ins in insights:
            report_lines.append(f"- **{ins.title}** — {ins.body}")
        report_lines.extend(["", "## Odds"])
        if game_odds and game_odds.bookmakers:
            for bm in game_odds.bookmakers[:3]:
                report_lines.append(f"**{bm.get('title')}**")
                for m in bm.get("markets", []):
                    for o in m.get("outcomes", []):
                        report_lines.append(f"  {o.get('name')}: {o.get('price')}")
        report = "\n".join(report_lines)
        st.download_button(
            "Download report (Markdown)",
            data=report,
            file_name=f"matchup-{game.date}-{game.away_team.abbreviation}-at-{game.home_team.abbreviation}.md",
            mime="text/markdown",
        )
        st.caption("Open in any text editor or paste into a doc; use Print → Save as PDF for a PDF.")


if __name__ == "__main__":
    main()
