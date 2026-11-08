"""🎯 Scanner page: every game tonight, hedges, +EV outliers and line moves."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import betlog
import history
import scanner as sc
from ui_common import ago, local_time, load_odds, quota_text, render_settings_sidebar, settings


def render() -> None:
    cfg = settings()
    games, err, fetched = load_odds()
    render_settings_sidebar(sc.all_books(games))
    my_books = {b.lower() for b in cfg["my_books"]} or None

    top = st.columns([3, 1])
    with top[0]:
        st.title("🎯 Tonight's scan")
        st.caption("Every NHL game, every book: guaranteed-profit hedges, prices that beat the fair line, and lines on the move.")
    with top[1]:
        st.write("")
        if st.button("🔄 Refresh odds", width="stretch", disabled=cfg["sample"],
                     help="Pulls fresh odds now (spends credits)."):
            games, err, fetched = load_odds(force=True)
    if err:
        st.warning(err)
    if not games:
        st.info("No odds yet. Add your Odds API key in ⚙️ settings, or switch on **sample odds** to try it out.")
        return

    markets = sc.build_markets(games)
    ev = sc.find_ev(markets, cfg["min_ev"], cfg["kelly"], cfg["max_price"], my_books)
    arbs = sc.find_arbs(markets, 0.0, my_books)
    near = sc.near_arbs(markets, 1.0)
    snaps = history.load_snapshots()
    mv = history.moves(snaps)
    no_fair = sum(1 for m in markets if not m.fair)

    c = st.columns(5)
    c[0].metric("Games", len(games))
    c[1].metric("Hedges (pay either way)", len(arbs))
    c[2].metric(f"Edges ≥ {cfg['min_ev']:g}%", len(ev))
    c[3].metric("Big line moves", len(mv))
    c[4].metric("Odds pulled", ago(fetched), quota_text(), delta_color="off")
    if not any(m.fair_source == "Pinnacle" for m in markets):
        st.caption("ℹ️ Pinnacle isn't in these odds, so fair prices come from the consensus of all books. "
                   "Add the **eu** region in settings for a sharper reference.")

    t1, t2, t3, t4 = st.tabs([f"🛡️ Hedges ({len(arbs)})", f"💰 Edges ({len(ev)})", f"📈 Line moves ({len(mv)})", "📋 All prices"])
    with t1:
        _hedges(arbs, near, cfg)
    with t2:
        _edges(ev, cfg)
    with t3:
        _moves(mv, snaps, markets)
    with t4:
        _board(markets)
    if no_fair:
        st.caption(f"{no_fair} market(s) skipped for edges: too few books quoting both sides.")


def _hedges(arbs, near, cfg) -> None:
    if not arbs:
        st.info("No guaranteed-profit hedges right now. They're rare and short-lived; the near misses below are worth watching.")
    total = st.number_input("Total to put on each hedge ($)", 10.0, 100000.0, 200.0, 10.0, key="arb_total")
    for a in arbs:
        with st.container(border=True):
            st.markdown(f"**{a.game}** · {a.market} · {local_time(a.commence)} — "
                        f"<span style='color:#4caf50;font-weight:bold'>+{a.profit_pct:.2f}% locked in</span>",
                        unsafe_allow_html=True)
            cols = st.columns(2)
            for col, (pick, book, price), pct in zip(cols, a.legs, a.stakes_pct):
                stake = total * pct / 100
                col.markdown(f"**{pick}** at **{book}**  \n{sc.to_american(price)} ({price:.2f}) · "
                             f"bet **${stake:,.2f}** → returns ${stake * price:,.2f}")
            st.caption(f"Profit ≈ ${total * a.profit_pct / 100:,.2f} whichever side wins. Place both quickly: one line moving kills it.")
    if near:
        with st.expander(f"Near misses ({len(near)}), within 1% of a hedge"):
            st.dataframe(pd.DataFrame([{
                "Game": a.game, "Market": a.market,
                "Side A": f"{a.legs[0][0]} @ {a.legs[0][1]} {sc.to_american(a.legs[0][2])}",
                "Side B": f"{a.legs[1][0]} @ {a.legs[1][1]} {sc.to_american(a.legs[1][2])}",
                "Gap": f"{a.profit_pct:.2f}%",
            } for a in near]), hide_index=True, width="stretch")
    st.caption("Heads-up: books limit accounts that hedge across books a lot. Round your stakes to normal-looking amounts.")


def _edges(ev, cfg) -> None:
    if not ev:
        st.info(f"Nothing beats the fair price by {cfg['min_ev']:g}% or more right now. Lower the threshold in ⚙️ settings to see smaller edges.")
        return
    bank = float(cfg["bankroll"])
    rows = [{
        "When": local_time(b.commence), "Game": b.game, "Market": b.market, "Pick": b.pick, "Book": b.book,
        "Odds": b.american, "Fair": sc.to_american(b.fair_price), "Edge %": round(b.ev_pct, 1),
        "Stake $": round(bank * b.kelly_pct / 100, 2), "Next best": sc.to_american(b.best_other) if b.best_other else "—",
        "Win %": round(b.fair_prob * 100, 1), "Fair from": b.fair_source,
    } for b in ev]
    st.caption("**Edge %** = expected profit per $100 if the fair price is right. **Stake $** = "
               f"{cfg['kelly']:g} Kelly on a ${bank:,.0f} bankroll. Big edges at one book are often a stale line: check before betting.")
    sel = st.dataframe(
        pd.DataFrame(rows), hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
        column_config={"Edge %": st.column_config.ProgressColumn("Edge %", min_value=0, max_value=max(10, max(r["Edge %"] for r in rows)), format="%.1f%%"),
                       "Stake $": st.column_config.NumberColumn(format="$%.2f")},
        key="ev_table",
    )
    picked = sel.selection.rows if sel and sel.selection else []
    if picked:
        b = ev[picked[0]]
        with st.form("log_bet"):
            st.markdown(f"**Log bet:** {b.pick} ({b.market}) at {b.book}, {b.game}")
            c = st.columns(2)
            price = c[0].number_input("Decimal odds you got", 1.01, 100.0, float(b.price), 0.01)
            stake = c[1].number_input("Stake $", 0.0, 100000.0, float(max(1.0, round(bank * b.kelly_pct / 100))), 1.0)
            if st.form_submit_button("📒 Add to bet log"):
                betlog.add_bet(b.game_id, b.game, b.commence, b.market, b.market_key, b.pick, b.book, price, stake, b.fair_prob)
                st.success("Logged. See 📒 Bets.")
    else:
        st.caption("Click a row to log that bet.")


def _moves(mv, snaps, markets) -> None:
    st.caption("Fair-price moves since the first pull of the day. Steam toward one side usually means goalie news or sharp money; "
               "books that haven't moved yet are where edges pop up. History builds as you refresh (no extra credits).")
    if len(snaps) < 2:
        st.info("Need at least two odds pulls to show movement. Refresh again later today.")
    if mv:
        st.dataframe(pd.DataFrame([{
            "Game": m["game"], "Market": m["market"], "Moved toward": m["toward"],
            "Win % then → now": f"{m['from'] * 100:.1f} → {m['to'] * 100:.1f}", "Move (pts)": round(m["move_pts"], 1),
            "Starts": local_time(m["commence"]),
        } for m in mv]), hide_index=True, width="stretch")
    opts = sorted({(m.game_id, m.game, m.name) for m in markets}, key=lambda x: (x[1], x[2]))
    if not opts:
        return
    i = st.selectbox("Chart a market", range(len(opts)), format_func=lambda i: f"{opts[i][1]} · {opts[i][2]}")
    gid, _, mname = opts[i]
    series = history.market_series(gid, mname, snaps)
    if not series:
        st.caption("No history for this one yet.")
        return
    df = pd.DataFrame(series)
    side = st.radio("Side", sorted(df["side"].unique()), horizontal=True)
    d = df[df["side"] == side]
    st.line_chart(d.pivot_table(index="at", columns="book", values="price", aggfunc="last"), height=280)
    fair = d.dropna(subset=["fair"]).groupby("at")["fair"].last()
    if len(fair) > 1:
        st.caption("Fair win % over time")
        st.line_chart(fair * 100, height=160)


def _board(markets) -> None:
    games = sorted({m.game for m in markets})
    g = st.selectbox("Game", games, key="board_game")
    for m in [m for m in markets if m.game == g]:
        rows = {}
        for s in m.sides:
            for book, p in s.prices.items():
                rows.setdefault(book, {})[s.label] = p
        df = pd.DataFrame(rows).T
        st.markdown(f"**{m.name}**" + (f" · fair {' / '.join(sc.to_american(1 / p) for p in m.fair)} ({m.fair_source})" if m.fair else ""))
        st.dataframe(df.style.highlight_max(axis=0, color="#1f5130").format("{:.2f}"), width="stretch")
