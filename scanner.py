"""
Slate scanner: finds +EV outliers and arbitrage (hedges that pay either way)
across every NHL game, for moneyline, totals and puck line.

Fair price comes from Pinnacle (the sharpest book) with its margin removed.
If Pinnacle isn't quoting a market, the no-vig average of every book quoting
both sides is used instead (needs MIN_CONSENSUS_BOOKS).

All odds are decimal (The Odds API default). Pure functions, no network.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Iterable, Optional

SHARP_BOOKS = ("pinnacle",)
MIN_CONSENSUS_BOOKS = 3
MARKET_NAMES = {"h2h": "Moneyline", "totals": "Total", "spreads": "Puck line"}


# ---------- odds math ----------

def to_american(dec: float) -> str:
    if dec <= 1:
        return "—"
    if dec >= 2:
        return f"+{round((dec - 1) * 100)}"
    return f"{round(-100 / (dec - 1))}"


def implied(dec: float) -> float:
    return 1.0 / dec if dec > 0 else 0.0


def no_vig(prices: list[float]) -> list[float]:
    """Remove the bookmaker margin: scale implied probabilities to sum to 1."""
    raw = [implied(p) for p in prices]
    total = sum(raw)
    return [r / total for r in raw] if total > 0 else raw


def kelly_fraction(p: float, dec: float, fraction: float = 0.25) -> float:
    """Fraction of bankroll to stake (fractional Kelly). 0 if no edge."""
    b = dec - 1
    if b <= 0:
        return 0.0
    f = (p * b - (1 - p)) / b
    return max(0.0, f * fraction)


def arb_stakes(prices: list[float], total: float = 100.0) -> tuple[list[float], float]:
    """Stake split that returns the same amount whatever happens. Returns (stakes, profit %)."""
    inv = [implied(p) for p in prices]
    s = sum(inv)
    stakes = [total * i / s for i in inv]
    return stakes, (1 / s - 1) * 100


# ---------- data shapes ----------

@dataclass
class Side:
    """One side of a two-way market at one line, e.g. 'Over 6.5' or 'Oilers -1.5'."""
    label: str
    prices: dict[str, float] = field(default_factory=dict)  # book title -> decimal price


@dataclass
class Market:
    game_id: str
    game: str            # "Away @ Home"
    commence: str
    key: str             # h2h / totals / spreads
    line: str            # "" for moneyline, "6.5", "1.5"
    sides: list[Side]    # always two
    fair: Optional[list[float]] = None   # fair prob per side
    fair_source: str = ""                # "Pinnacle" or "Consensus (n books)"

    @property
    def name(self) -> str:
        base = MARKET_NAMES.get(self.key, self.key)
        return f"{base} {self.line}".strip()


@dataclass
class EVBet:
    game_id: str
    game: str
    commence: str
    market: str
    market_key: str
    pick: str
    book: str
    price: float
    fair_prob: float
    fair_price: float
    ev_pct: float
    kelly_pct: float
    fair_source: str
    books_quoting: int
    best_other: float  # best price at any *other* book for this side

    @property
    def american(self) -> str:
        return to_american(self.price)


@dataclass
class Arb:
    game_id: str
    game: str
    commence: str
    market: str
    legs: list[tuple[str, str, float]]  # (pick, book, price)
    profit_pct: float
    stakes_pct: list[float]


# ---------- building markets from The Odds API payload ----------

def _book_key(bm: dict) -> str:
    return (bm.get("key") or bm.get("title") or "").lower()


def build_markets(games: Iterable, books_filter: Optional[set[str]] = None) -> list[Market]:
    """
    games: GameOdds objects (or dicts with the same fields).
    Pairs the two sides of every market at the same line. Spreads pair
    'Home -1.5' with 'Away +1.5'.
    """
    out: list[Market] = []
    for g in games:
        gd = g if isinstance(g, dict) else g.__dict__
        home, away = gd.get("home_team", ""), gd.get("away_team", "")
        title = f"{away} @ {home}"
        # (market_key, line_id) -> {side_label: {book: price}}
        grouped: dict[tuple[str, str], dict[str, dict[str, float]]] = defaultdict(lambda: defaultdict(dict))
        for bm in gd.get("bookmakers", []) or []:
            book = bm.get("title") or bm.get("key") or "?"
            for m in bm.get("markets", []) or []:
                key = m.get("key")
                for o in m.get("outcomes", []) or []:
                    try:
                        price = float(o.get("price"))
                    except (TypeError, ValueError):
                        continue
                    name = (o.get("name") or "").strip()
                    pt = o.get("point")
                    if key == "h2h":
                        line, label = "", name
                    elif key == "totals":
                        if pt is None:
                            continue
                        line, label = f"{float(pt):g}", f"{name} {float(pt):g}"
                    elif key == "spreads":
                        if pt is None:
                            continue
                        p = float(pt)
                        # pair by the home team's handicap so both sides share one line id
                        home_pt = p if name == home else -p
                        line = f"{home_pt:+g}" if home_pt else "0"
                        label = f"{name} {p:+g}"
                    else:
                        continue
                    grouped[(key, line)][label][book] = price
        for (key, line), sides in grouped.items():
            if len(sides) != 2:
                continue
            labels = sorted(sides.keys())
            if key == "h2h":
                ordered = [l for l in (away, home) if l in sides]
                labels = ordered if len(ordered) == 2 else labels
            elif key == "totals":
                labels = sorted(labels, key=lambda s: 0 if s.startswith("Over") else 1)
            mk = Market(
                game_id=gd.get("id", ""), game=title, commence=gd.get("commence_time", ""),
                key=key, line=(f"home {line}" if key == "spreads" else line),
                sides=[Side(l, dict(sides[l])) for l in labels],
            )
            _set_fair(mk)
            if books_filter is not None:
                for s in mk.sides:
                    s.prices = {b: p for b, p in s.prices.items() if b.lower() in books_filter or _is_sharp(b)}
            out.append(mk)
    return out


def _is_sharp(book: str) -> bool:
    return book.lower() in SHARP_BOOKS


def _set_fair(mk: Market) -> None:
    a, b = mk.sides
    for book in a.prices:
        if _is_sharp(book) and book in b.prices:
            mk.fair = no_vig([a.prices[book], b.prices[book]])
            mk.fair_source = book.title()
            return
    both = [bk for bk in a.prices if bk in b.prices]
    if len(both) >= MIN_CONSENSUS_BOOKS:
        pa = [no_vig([a.prices[bk], b.prices[bk]])[0] for bk in both]
        fa = median(pa)
        mk.fair = [fa, 1 - fa]
        mk.fair_source = f"Consensus ({len(both)} books)"


# ---------- scans ----------

def find_ev(markets: list[Market], min_ev_pct: float = 2.0, kelly: float = 0.25,
            max_price: float = 6.0, my_books: Optional[set[str]] = None) -> list[EVBet]:
    """Prices that beat the fair price by at least min_ev_pct. Long shots above max_price are skipped (noisy)."""
    bets: list[EVBet] = []
    for mk in markets:
        if not mk.fair:
            continue
        for side, p in zip(mk.sides, mk.fair):
            for book, price in side.prices.items():
                if _is_sharp(book) and mk.fair_source.lower() == book.lower():
                    continue  # the reference can't beat itself
                if my_books is not None and book.lower() not in my_books:
                    continue
                if price > max_price:
                    continue
                ev = (price * p - 1) * 100
                if ev < min_ev_pct:
                    continue
                others = [v for b, v in side.prices.items() if b != book]
                bets.append(EVBet(
                    game_id=mk.game_id, game=mk.game, commence=mk.commence,
                    market=mk.name, market_key=mk.key, pick=side.label, book=book,
                    price=price, fair_prob=p, fair_price=1 / p if p else 0, ev_pct=ev,
                    kelly_pct=kelly_fraction(p, price, kelly) * 100,
                    fair_source=mk.fair_source, books_quoting=len(side.prices),
                    best_other=max(others) if others else 0.0,
                ))
    bets.sort(key=lambda x: -x.ev_pct)
    return bets


def find_arbs(markets: list[Market], min_profit_pct: float = 0.0,
              my_books: Optional[set[str]] = None) -> list[Arb]:
    """Best price on each side at different books; an arb when the implied probs add to under 100%."""
    arbs: list[Arb] = []
    for mk in markets:
        legs = []
        for side in mk.sides:
            prices = {b: p for b, p in side.prices.items() if my_books is None or b.lower() in my_books}
            if not prices:
                break
            book, price = max(prices.items(), key=lambda kv: kv[1])
            legs.append((side.label, book, price))
        if len(legs) != 2:
            continue
        stakes, profit = arb_stakes([l[2] for l in legs])
        if profit > min_profit_pct:
            arbs.append(Arb(mk.game_id, mk.game, mk.commence, mk.name, legs, profit, stakes))
    arbs.sort(key=lambda a: -a.profit_pct)
    return arbs


def near_arbs(markets: list[Market], within_pct: float = 1.0) -> list[Arb]:
    """Markets that are almost an arb (lose less than within_pct). Worth watching as lines move."""
    return [a for a in find_arbs(markets, min_profit_pct=-within_pct) if a.profit_pct <= 0]


def all_books(games: Iterable) -> list[str]:
    seen = set()
    for g in games:
        gd = g if isinstance(g, dict) else g.__dict__
        for bm in gd.get("bookmakers", []) or []:
            seen.add(bm.get("title") or bm.get("key"))
    return sorted(b for b in seen if b)
