"""📒 Bets page: your bet log, auto-settled from final scores, with P/L and closing-line value."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

import betlog
import history
from nhl_client import get_schedule
from ui_common import local_time, render_settings_sidebar, settings


def _settle_open() -> int:
    open_bets = [b for b in betlog.load_bets() if b["result"] == "open" and b.get("commence")]
    if not open_bets:
        return 0
    days = []
    for b in open_bets:
        try:
            days.append(datetime.fromisoformat(b["commence"].replace("Z", "+00:00")).date())
        except ValueError:
            continue
    if not days:
        return 0
    start, end = min(days) - timedelta(days=1), min(max(days), date.today())
    if start > end:
        return 0
    finals = [(g.home_team.name, g.away_team.name, g.home_score, g.away_score, g.date)
              for g in get_schedule(start, end) if g.is_final and g.home_score is not None]
    return betlog.auto_settle(finals)


def render() -> None:
    render_settings_sidebar([])
    cfg = settings()
    st.title("📒 Bet log")
    settled = _settle_open()
    clv = betlog.update_clv(history.load_snapshots())
    if settled or clv:
        st.toast(f"Updated {settled} result(s) from final scores, {clv} closing line(s).")

    rows = betlog.load_bets()
    s = betlog.summary(rows)
    c = st.columns(5)
    c[0].metric("Bets", s["bets"], f"{s['open']} open", delta_color="off")
    c[1].metric("Record", f"{s['won']}-{s['lost']}")
    c[2].metric("Profit", f"${s['profit']:,.2f}", f"{s['roi']:+.1f}% ROI")
    c[3].metric("Avg edge when bet", f"{s['avg_ev']:+.1f}%" if s["avg_ev"] is not None else "—")
    c[4].metric("Avg CLV", f"{s['avg_clv']:+.1f}%" if s["avg_clv"] is not None else "—",
                f"{s['clv_n']} bets" if s["clv_n"] else None, delta_color="off")
    st.caption("**CLV** compares your price to the fair price right before puck drop. Beating the close on average is the "
               "best early sign your edges are real; win/loss takes hundreds of bets to mean anything.")

    if not rows:
        st.info("No bets yet. On 🎯 Scanner → Edges, click a row to log it, or add one by hand below.")
    else:
        settled_rows = [r for r in rows if r["pnl"] is not None]
        if len(settled_rows) > 1:
            pl = pd.DataFrame(settled_rows).sort_values("commence")
            pl["Running P/L"] = pl["pnl"].cumsum()
            st.line_chart(pl.set_index("commence")["Running P/L"], height=200)

        st.markdown("#### Open bets")
        for r in [r for r in rows if r["result"] == "open"]:
            cols = st.columns([5, 1, 1, 1, 1])
            cols[0].markdown(f"**{r['pick']}** ({r['market']}) · {r['book']} · {r['price']:.2f} · ${r['stake']:,.2f}  \n"
                             f"<span style='color:#9aa'>{r['game']} · {local_time(r['commence'])}</span>", unsafe_allow_html=True)
            for col, res, lab in zip(cols[1:4], ("won", "lost", "push"), ("✅ Won", "❌ Lost", "➖ Push")):
                if col.button(lab, key=f"{res}_{r['id']}"):
                    betlog.set_result(r["id"], res)
                    st.rerun()
            if cols[4].button("🗑️", key=f"del_{r['id']}", help="Delete"):
                betlog.delete_bet(r["id"])
                st.rerun()
        st.caption("Results fill in automatically once the NHL marks the game final.")

        st.markdown("#### History")
        df = pd.DataFrame(rows)[["placed_at", "game", "market", "pick", "book", "price", "stake", "result", "pnl", "clv_pct"]]
        df.columns = ["Placed", "Game", "Market", "Pick", "Book", "Odds", "Stake", "Result", "P/L", "CLV %"]
        st.dataframe(df.iloc[::-1], hide_index=True, width="stretch")
        st.download_button("Download bets (CSV)", df.to_csv(index=False), "bets.csv", "text/csv")

    with st.expander("➕ Add a bet by hand"):
        with st.form("manual_bet"):
            c = st.columns(2)
            away = c[0].text_input("Away team", placeholder="Calgary Flames")
            home = c[1].text_input("Home team", placeholder="Edmonton Oilers")
            c = st.columns(3)
            when = c[0].date_input("Game date", date.today())
            mkey = c[1].selectbox("Market", ["h2h", "totals", "spreads"],
                                  format_func=lambda m: {"h2h": "Moneyline", "totals": "Total", "spreads": "Puck line"}[m])
            pick = c[2].text_input("Pick", placeholder="Calgary Flames / Over 6.5 / Edmonton Oilers -1.5")
            c = st.columns(3)
            book = c[0].text_input("Book", placeholder="Sports Interaction")
            price = c[1].number_input("Decimal odds", 1.01, 100.0, 1.91, 0.01)
            stake = c[2].number_input("Stake $", 0.0, 100000.0, 20.0, 1.0)
            if st.form_submit_button("Add") and away and home and pick:
                name = {"h2h": "Moneyline", "totals": "Total", "spreads": "Puck line"}[mkey]
                if mkey == "totals":
                    name += " " + pick.split()[-1]
                betlog.add_bet("", f"{away} @ {home}", f"{when.isoformat()}T23:00:00Z", name, mkey, pick, book, price, stake, None)
                st.rerun()
