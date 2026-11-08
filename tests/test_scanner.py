import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scanner as sc
import betlog

SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "sample_odds.json").read_text())


def test_math():
    assert sc.to_american(2.5) == "+150"
    assert sc.to_american(1.5) == "-200"
    fair = sc.no_vig([1.91, 1.91])
    assert abs(fair[0] - 0.5) < 1e-9
    stakes, profit = sc.arb_stakes([2.1, 2.1])
    assert abs(stakes[0] - 50) < 1e-9 and profit > 0
    assert sc.kelly_fraction(0.5, 1.9) == 0.0
    assert sc.kelly_fraction(0.55, 2.0, 1.0) > 0.09


def test_markets_pair_up():
    mks = sc.build_markets(SAMPLE)
    assert len(mks) == 6 * 3
    for mk in mks:
        assert len(mk.sides) == 2
        assert mk.fair and abs(sum(mk.fair) - 1) < 1e-9
        assert mk.fair_source == "Pinnacle"
    pl = [m for m in mks if m.key == "spreads"][0]
    assert any("-1.5" in s.label for s in pl.sides) and any("+1.5" in s.label for s in pl.sides)


def test_finds_planted_outliers_and_arb():
    mks = sc.build_markets(SAMPLE)
    ev = sc.find_ev(mks, min_ev_pct=3)
    picks = {(b.book, b.pick) for b in ev}
    assert ("BetRivers", "Calgary Flames") in picks
    assert ("bet365", "Under 5.5") in picks
    arbs = sc.find_arbs(mks)
    utah = [a for a in arbs if "Utah" in a.game and a.market == "Moneyline"]
    assert utah and utah[0].profit_pct > 3
    assert {l[1] for l in utah[0].legs} == {"Caesars", "FanDuel"}


def test_my_books_filter():
    mks = sc.build_markets(SAMPLE)
    ev = sc.find_ev(mks, min_ev_pct=-100, my_books={"draftkings"})
    assert ev and all(b.book == "DraftKings" for b in ev)


def test_consensus_without_pinnacle():
    no_pin = json.loads(json.dumps(SAMPLE))
    for g in no_pin:
        g["bookmakers"] = [b for b in g["bookmakers"] if b["key"] != "pinnacle"]
    mks = sc.build_markets(no_pin)
    assert all(m.fair_source.startswith("Consensus") for m in mks)


def test_grading():
    g = "Calgary Flames @ Edmonton Oilers"
    assert betlog.grade("h2h", "Calgary Flames", g, 2, 3) == "won"
    assert betlog.grade("h2h", "Edmonton Oilers", g, 2, 3) == "lost"
    assert betlog.grade("totals", "Over 6.5", g, 4, 3) == "won"
    assert betlog.grade("totals", "Under 6", g, 4, 2) == "push"
    assert betlog.grade("spreads", "Edmonton Oilers -1.5", g, 4, 2) == "won"
    assert betlog.grade("spreads", "Calgary Flames +1.5", g, 4, 3) == "won"
    assert betlog.grade("spreads", "Calgary Flames +1.5", g, 5, 3) == "lost"


def test_history_and_clv(tmp_path, monkeypatch):
    import history
    monkeypatch.setattr(history, "HISTORY_FILE", tmp_path / "h.jsonl")
    monkeypatch.setattr(betlog, "BETS_FILE", tmp_path / "bets.csv")
    monkeypatch.setattr(history, "DATA_DIR", tmp_path)
    monkeypatch.setattr(betlog, "DATA_DIR", tmp_path)
    import time
    early = json.loads(json.dumps(SAMPLE))
    for g in early:
        g["commence_time"] = "2099-01-01T00:00:00Z"
    history.save_snapshot(early, time.time() - 3600)
    later = json.loads(json.dumps(early))
    pin = [b for b in later[0]["bookmakers"] if b["key"] == "pinnacle"][0]
    pin["markets"][0]["outcomes"][0]["price"] = 1.45   # Oilers steamed
    pin["markets"][0]["outcomes"][1]["price"] = 2.95
    history.save_snapshot(later, time.time())
    mv = history.moves()
    assert mv and mv[0]["toward"] == "Edmonton Oilers"
    cf = history.closing_fair("sample0", "Moneyline", "Calgary Flames")
    assert cf and cf < 0.4
    s = history.market_series("sample0", "Moneyline")
    assert len(s) > 10
