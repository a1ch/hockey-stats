"""
Bet log: what you bet, at what price, and how it went. Stored locally in
data/bets.csv (never committed). Settles itself from NHL final scores and
tracks closing-line value (CLV): did you beat the fair price at puck drop?
Positive CLV over many bets is the best sign the edges are real, long
before win/loss results settle down.
"""
from __future__ import annotations

import csv
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from config import DATA_DIR

BETS_FILE = DATA_DIR / "bets.csv"
FIELDS = ["id", "placed_at", "game_id", "game", "commence", "market", "market_key", "pick",
          "book", "price", "stake", "fair_prob", "result", "closing_fair", "clv_pct", "pnl"]


def load_bets() -> list[dict]:
    if not BETS_FILE.exists():
        return []
    with BETS_FILE.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("price", "stake", "fair_prob", "closing_fair", "clv_pct", "pnl"):
            try:
                r[k] = float(r[k]) if r.get(k) not in (None, "") else None
            except ValueError:
                r[k] = None
    return rows


def save_bets(rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with BETS_FILE.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in FIELDS})


def add_bet(game_id: str, game: str, commence: str, market: str, market_key: str, pick: str,
            book: str, price: float, stake: float, fair_prob: Optional[float]) -> dict:
    rows = load_bets()
    bet = {"id": uuid.uuid4().hex[:8], "placed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "game_id": game_id, "game": game, "commence": commence, "market": market, "market_key": market_key,
           "pick": pick, "book": book, "price": price, "stake": stake, "fair_prob": fair_prob,
           "result": "open", "closing_fair": None, "clv_pct": None, "pnl": None}
    rows.append(bet)
    save_bets(rows)
    return bet


def set_result(bet_id: str, result: str) -> None:
    rows = load_bets()
    for r in rows:
        if r["id"] == bet_id:
            r["result"] = result
            r["pnl"] = pnl(r["price"], r["stake"], result)
    save_bets(rows)


def delete_bet(bet_id: str) -> None:
    save_bets([r for r in load_bets() if r["id"] != bet_id])


def pnl(price: float, stake: float, result: str) -> Optional[float]:
    if result == "won":
        return round(stake * (price - 1), 2)
    if result == "lost":
        return -stake
    if result == "push":
        return 0.0
    return None


def grade(market_key: str, pick: str, game: str, home_score: int, away_score: int) -> Optional[str]:
    """
    Grade a bet from the final score. NHL moneylines, totals and puck lines at
    these books include overtime and the shootout goal, which matches the NHL
    API's final score. Returns won / lost / push, or None if the pick isn't understood.
    """
    away, home = [s.strip() for s in game.split(" @ ", 1)]
    total = home_score + away_score
    if market_key == "h2h":
        winner = home if home_score > away_score else away
        return "won" if pick == winner else "lost"
    if market_key == "totals":
        side, _, line = pick.partition(" ")
        line = float(line)
        if total == line:
            return "push"
        over = total > line
        return "won" if (over if side == "Over" else not over) else "lost"
    if market_key == "spreads":
        name, _, pt = pick.rpartition(" ")
        pt = float(pt)
        margin = (home_score - away_score) if name == home else (away_score - home_score)
        adj = margin + pt
        if adj == 0:
            return "push"
        return "won" if adj > 0 else "lost"
    return None


def auto_settle(finals: list[tuple[str, str, int, int, str]]) -> int:
    """
    finals: (home_name, away_name, home_score, away_score, date YYYY-MM-DD) for finished games.
    Settles open bets whose game matches. Returns how many were settled.
    """
    from odds_client import _norm
    rows = load_bets()
    n = 0
    for r in rows:
        if r["result"] != "open":
            continue
        away, home = [_norm(s) for s in r["game"].split(" @ ", 1)]
        day = (r.get("commence") or "")[:10]
        for h, a, hs, as_, d in finals:
            if _norm(h) == home and _norm(a) == away and _close_dates(day, d):
                res = grade(r["market_key"], r["pick"], r["game"], hs, as_)
                if res:
                    r["result"] = res
                    r["pnl"] = pnl(r["price"], r["stake"], res)
                    n += 1
                break
    if n:
        save_bets(rows)
    return n


def _close_dates(a: str, b: str) -> bool:
    """Odds API times are UTC; an evening game in North America can be the next UTC day."""
    try:
        da = datetime.fromisoformat(a).date()
        db = datetime.fromisoformat(b).date()
    except ValueError:
        return a == b
    return abs((da - db).days) <= 1


def update_clv(snaps: Optional[list[dict]] = None) -> int:
    """Fill closing fair price and CLV for bets whose game has started. Returns how many changed."""
    from history import closing_fair, _parse_t
    rows = load_bets()
    n = 0
    now = time.time()
    for r in rows:
        if r.get("closing_fair") is not None or not r.get("commence"):
            continue
        if _parse_t(r["commence"]) > now:
            continue
        cf = closing_fair(r["game_id"], r["market"], r["pick"], snaps)
        if cf:
            r["closing_fair"] = round(cf, 4)
            r["clv_pct"] = round((r["price"] * cf - 1) * 100, 2)
            n += 1
    if n:
        save_bets(rows)
    return n


def summary(rows: Optional[list[dict]] = None) -> dict:
    rows = rows if rows is not None else load_bets()
    settled = [r for r in rows if r["result"] in ("won", "lost", "push")]
    staked = sum(r["stake"] or 0 for r in settled)
    profit = sum(r["pnl"] or 0 for r in settled)
    clvs = [r["clv_pct"] for r in rows if r.get("clv_pct") is not None]
    evs = [(r["price"] * r["fair_prob"] - 1) * 100 for r in rows if r.get("fair_prob")]
    return {
        "bets": len(rows), "open": sum(r["result"] == "open" for r in rows),
        "won": sum(r["result"] == "won" for r in settled), "lost": sum(r["result"] == "lost" for r in settled),
        "staked": staked, "profit": profit, "roi": (profit / staked * 100) if staked else 0.0,
        "avg_clv": (sum(clvs) / len(clvs)) if clvs else None, "clv_n": len(clvs),
        "avg_ev": (sum(evs) / len(evs)) if evs else None,
    }
