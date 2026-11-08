"""Builds tests/fixtures/sample_odds.json: a fake NHL slate in The Odds API format,
with a couple of planted outliers and one arb, for demo mode and tests."""
import json, random
from pathlib import Path

random.seed(7)
BOOKS = [("pinnacle","Pinnacle",0.025),("draftkings","DraftKings",0.045),("fanduel","FanDuel",0.045),
         ("betmgm","BetMGM",0.05),("caesars","Caesars",0.05),("betrivers","BetRivers",0.05),
         ("bet365","bet365",0.045),("betway","Betway",0.05),("unibet_eu","Unibet",0.045)]
GAMES = [("Edmonton Oilers","Calgary Flames",0.60,6.5),("Toronto Maple Leafs","Montreal Canadiens",0.57,6.5),
         ("Vegas Golden Knights","Seattle Kraken",0.58,5.5),("Colorado Avalanche","Utah Mammoth",0.55,6.5),
         ("Florida Panthers","Boston Bruins",0.56,5.5),("Winnipeg Jets","Vancouver Canucks",0.53,5.5)]

def price(p, vig):
    return round(1 / (p * (1 + vig)), 2)

def jit(p, amt=0.012):
    return min(0.95, max(0.05, p + random.uniform(-amt, amt)))

games = []
for gi, (home, away, ph, tot) in enumerate(GAMES):
    p_over = 0.5 + random.uniform(-0.04, 0.04)
    p_cover = ph - 0.22  # home -1.5
    bms = []
    for bi, (key, title, vig) in enumerate(BOOKS):
        h = jit(ph) if key != "pinnacle" else ph
        o = jit(p_over) if key != "pinnacle" else p_over
        c = jit(p_cover) if key != "pinnacle" else p_cover
        hp, ap = price(h, vig), price(1 - h, vig)
        op, up = price(o, vig), price(1 - o, vig)
        cp, cap = price(c, vig), price(1 - c, vig)
        # planted: BetRivers asleep on the Flames, bet365 generous on an Under, an arb on Utah
        if gi == 0 and key == "betrivers": ap = 2.95
        if gi == 4 and key == "bet365": up = 2.20
        if gi == 3 and key == "fanduel": ap = 2.40
        if gi == 3 and key == "caesars": hp = 1.85
        bms.append({"key": key, "title": title, "last_update": "2026-11-08T22:00:00Z", "markets": [
            {"key": "h2h", "outcomes": [{"name": home, "price": hp}, {"name": away, "price": ap}]},
            {"key": "spreads", "outcomes": [{"name": home, "price": cp, "point": -1.5}, {"name": away, "price": cap, "point": 1.5}]},
            {"key": "totals", "outcomes": [{"name": "Over", "price": op, "point": tot}, {"name": "Under", "price": up, "point": tot}]},
        ]})
    games.append({"id": f"sample{gi}", "sport_key": "icehockey_nhl", "commence_time": f"2026-11-09T0{gi % 3}:00:00Z",
                  "home_team": home, "away_team": away, "bookmakers": bms})
Path(__file__).with_name("fixtures").joinpath("sample_odds.json").write_text(json.dumps(games, indent=1))
print("ok", len(games))
