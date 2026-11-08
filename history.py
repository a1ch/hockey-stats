"""
Line-movement history. Every fresh odds pull is saved as a snapshot in
data/odds_history.jsonl (one line per pull), so the app can chart how lines
moved, flag big moves, and work out closing-line value for logged bets.
Costs no extra API credits: it only records pulls the app already made.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Optional

from config import DATA_DIR
from scanner import build_markets

HISTORY_FILE = DATA_DIR / "odds_history.jsonl"
KEEP_DAYS = 21


def save_snapshot(raw_games: list, at: Optional[float] = None) -> None:
    at = at or time.time()
    rows = []
    for mk in build_markets(raw_games):
        rows.append({
            "g": mk.game_id, "game": mk.game, "t0": mk.commence, "m": mk.name, "k": mk.key,
            "s": [s.label for s in mk.sides],
            "p": [s.prices for s in mk.sides],
            "f": mk.fair, "fs": mk.fair_source,
        })
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": at, "rows": rows}) + "\n")
    _prune()


def _prune() -> None:
    try:
        lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    cutoff = time.time() - KEEP_DAYS * 86400
    keep = [l for l in lines if l.strip() and json.loads(l).get("at", 0) >= cutoff]
    if len(keep) < len(lines):
        HISTORY_FILE.write_text("\n".join(keep) + "\n", encoding="utf-8")


def load_snapshots() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    out = []
    for line in HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _parse_t(s: str) -> float:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return 0.0


def market_series(game_id: str, market: str, snaps: Optional[list[dict]] = None) -> list[dict]:
    """Rows of {at, side, book, price, fair} for one market, oldest first (for charts)."""
    out = []
    for snap in snaps if snaps is not None else load_snapshots():
        for r in snap["rows"]:
            if r["g"] != game_id or r["m"] != market:
                continue
            ts = datetime.fromtimestamp(snap["at"], tz=timezone.utc)
            for i, side in enumerate(r["s"]):
                for book, price in r["p"][i].items():
                    out.append({"at": ts, "side": side, "book": book, "price": price,
                                "fair": (r["f"][i] if r.get("f") else None)})
    return out


def moves(snaps: Optional[list[dict]] = None, min_move: float = 0.03) -> list[dict]:
    """
    Markets whose fair probability moved at least min_move (3 points) between the
    first and latest snapshot for that game. A sharp move usually means news (goalie,
    injury) or big money; books slow to follow are where outliers show up.
    """
    snaps = snaps if snaps is not None else load_snapshots()
    first: dict[tuple, tuple] = {}
    last: dict[tuple, tuple] = {}
    for snap in snaps:
        for r in snap["rows"]:
            if not r.get("f"):
                continue
            k = (r["g"], r["m"])
            if _parse_t(r["t0"]) and snap["at"] > _parse_t(r["t0"]):
                continue  # after puck drop
            first.setdefault(k, (snap["at"], r))
            last[k] = (snap["at"], r)
    out = []
    for k, (t1, r1) in last.items():
        t0, r0 = first[k]
        if t1 == t0 or r0["s"] != r1["s"]:
            continue
        d = r1["f"][0] - r0["f"][0]
        if abs(d) >= min_move:
            toward = r1["s"][0] if d > 0 else r1["s"][1]
            out.append({"game": r1["game"], "game_id": k[0], "market": k[1], "toward": toward,
                        "move_pts": abs(d) * 100, "from": r0["f"][0 if d > 0 else 1],
                        "to": r1["f"][0 if d > 0 else 1], "since": t0, "commence": r1["t0"]})
    out.sort(key=lambda x: -x["move_pts"])
    return out


def closing_fair(game_id: str, market: str, pick: str, snaps: Optional[list[dict]] = None) -> Optional[float]:
    """Fair probability of `pick` in the last snapshot before puck drop (None if no data)."""
    best = None
    for snap in snaps if snaps is not None else load_snapshots():
        for r in snap["rows"]:
            if r["g"] == game_id and r["m"] == market and r.get("f") and pick in r["s"]:
                t0 = _parse_t(r["t0"])
                if t0 and snap["at"] > t0:
                    continue
                if best is None or snap["at"] >= best[0]:
                    best = (snap["at"], r["f"][r["s"].index(pick)])
    return best[1] if best else None
