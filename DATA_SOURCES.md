# Data Sources for Extra Features

Where to get each type of data, cost, and how to plug it in.

---

## ✅ PP/PK rankings (implementable now)

| Source | URL | Auth | Notes |
|--------|-----|------|--------|
| **NHL Stats REST API** | `https://api.nhle.com/stats/rest/en/team/summary` | None | **Free.** Returns `powerPlayPct`, `penaltyKillPct`, `teamId`, `teamFullName` for all teams. Use query: `?sort=powerPlayPct&dir=DESC&cayenneExp=gameTypeId=2%20and%20seasonId=YYYYYYYY` (e.g. `20252026`). Map `teamId` to your game’s home/away team for rankings. Different host from `statsapi.web.nhl.com`, so it should resolve. |

**Example:**  
`GET https://api.nhle.com/stats/rest/en/team/summary?sort=powerPlayPct&dir=DESC&cayenneExp=gameTypeId=2%20and%20seasonId=20252026`

---

## Referee assignment

| Source | URL | Auth | Notes |
|--------|-----|------|--------|
| **NHL api-web boxscore** | `https://api-web.nhle.com/v1/gamecenter/{gameId}/boxscore` | None | Current boxscore response does **not** include officials in the JSON; only player/team stats. Worth re-checking after game start or other endpoints (e.g. landing/lineup). |
| **Sportradar NHL API** | `https://developer.sportradar.com/ice-hockey/reference/nhl-game-boxscore` | Paid API key | Boxscore includes referee/officials. B2B product. |
| **Scouting The Refs** | https://scoutingtherefs.com/ | None | “Tonight’s Officials” and referee stats; **web only**, no public API. Scraping possible but fragile. |

**Recommendation:** Try `api-web.nhle.com` game/landing or lineup endpoints for officials; if not available, use Sportradar for a paid, reliable referee feed.

---

## Public % / sharp money / reverse line movement

| Source | URL | Auth | Notes |
|--------|-----|------|--------|
| **SharpAPI** | https://sharpapi.io/ , https://docs.sharpapi.io/ | Free tier + paid ($0–$399/mo) | Real-time odds, +EV vs Pinnacle, arbitrage. **Does not** expose “public %” or “sharp %” directly; you’d infer from odds/EV. |
| **OddsJam** | https://oddsjam.com/odds-api | Paid | “Sharp Money” tool and API; tracks sharp/pro syndicate action. Good fit for “where is smart money going” and RLM-style signals. |
| **The Odds API** | https://the-odds-api.com/ | Free tier + paid | Live/upcoming **odds only**. No public betting % or sharp %. **Historical odds** (paid) give line movement over time; you could compare open vs current for “reverse” moves if you define heuristics. |

**Recommendation:** For true “public % vs sharp” or RLM, use a product that exposes betting splits (e.g. OddsJam) or build line-movement logic from The Odds API historical (paid) and interpret as proxy.

---

## ATS record (against the spread)

| Source | URL | Auth | Notes |
|--------|-----|------|--------|
| **StatSharp** | https://www.statsharp.com/nhl/bettingstats.php | None | NHL ATS (and other betting stats) by team/season; **web only**, no public API. You’d need to scrape or find a partner feed. |
| **The Odds API (historical)** | https://the-odds-api.com/historical-odds-data/ | **Paid only** | Historical spread (and ML/totals) by book. Combine with **game results** (e.g. from NHL schedule/boxscore: home/away, win/loss, goal diff) to compute “covered spread” and build ATS records. |

**Recommendation:** Either scrape StatSharp for pre-built ATS, or compute ATS yourself from The Odds API historical spreads + NHL results (both needed).

---

## Situational trends (e.g. “home as underdog”)

| Source | URL | Auth | Notes |
|--------|-----|------|--------|
| **NHL schedule + results** | `api-web.nhle.com` schedule/boxscore | None | You have schedule and (post-game) scores. You can derive home/away, W/L, and (with odds) favorite/underdog. |
| **The Odds API** | Current + historical odds | Free (current) / Paid (historical) | To label “underdog”/“favorite” and spread result you need **opening or closing lines** (historical is paid). |

**Recommendation:** Build situational queries (e.g. “home as underdog”) from NHL game results plus a source of opening/closing lines (e.g. The Odds API historical, or a site that publishes “team as underdog” stats).

---

## Starter goalie confirmation

| Source | URL | Auth | Notes |
|--------|-----|------|--------|
| **api-web.nhle.com boxscore** | `.../gamecenter/{gameId}/boxscore` | None | After game: goalies have `"starter": true/false`. **Pre-game** confirmed starters are not in this response. |
| **SportsDataIO** | https://sportsdata.io/nhl-confirmed-coverage , workflow guide | Paid API key | Confirmed starting goalies, depth charts, lineups. Built for this use case. |
| **FPTrack** | https://fptrack.com/hockey/starting-lineups | None | Starting goalies/lines; **web only**, no API. |

**Recommendation:** For “confirmed starter” before puck drop, use SportsDataIO or a similar lineup/confirmed-starter API; FPTrack is reference-only unless you scrape.

---

## Weather / outdoor / altitude

| Source | URL | Auth | Notes |
|--------|-----|------|--------|
| **Static list** | — | None | Maintain a list of outdoor/high-altitude venues (e.g. Stadium Series, Denver). No API needed for “is this outdoor/altitude?”. |
| **OpenWeather / other weather API** | e.g. https://openweathermap.org/api | Free tier + paid | For outdoor games, pass venue lat/long or city to get conditions. |

**Recommendation:** Use a static list for venue type; add a weather API only for outdoor games if you want live conditions.

---

## Quick reference

| Data | Free option | Paid option |
|------|-------------|-------------|
| **PP/PK** | ✅ `api.nhle.com/stats/rest` team summary | — |
| **Referee** | ❌ (boxscore no officials) | Sportradar NHL |
| **Public % / sharp / RLM** | ❌ | OddsJam, SharpAPI (odds/EV) |
| **ATS** | Scrape StatSharp (web) | The Odds API historical + your ATS calc |
| **Situational** | NHL results + your logic | The Odds API historical for lines |
| **Starter goalie** | ❌ pre-game | SportsDataIO |
| **Weather / outdoor** | Static list + optional weather API | — |
