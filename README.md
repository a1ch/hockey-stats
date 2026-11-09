# Hockey Matchup: News vs Odds

A Streamlit app that gathers **NHL matchup news**, **lineups/health**, and **betting odds**, then compares them so you can see how the narrative (injuries, standings, news) lines up with the odds.

## Features

### 🎯 Scanner (new)
- **Every game tonight in one scan** across moneyline, totals and puck line.
- **Hedges:** best price on each side at different books; when they add up to under 100% implied, it shows the stake split and locked-in profit for the amount you enter. Near misses (within 1%) are listed to watch.
- **Edges (+EV):** each book's price vs the fair price (Pinnacle with its margin removed, or the no-vig consensus when Pinnacle isn't quoting). Shows edge %, fractional-Kelly stake on your bankroll, and the next best price. Click a row to log the bet.
- **Line moves:** every odds pull is saved (no extra credits), so it flags markets whose fair price moved 3+ points and charts each book's line over time.
- **My books:** pick the books you can actually use; edges and hedges only use those.
- **Credit saver:** odds are reused for N minutes (default 10) instead of re-pulled on every click, and the remaining monthly credits are shown.
- **Sample odds:** switch on in ⚙️ settings to try everything without a key.

### 📒 Bets (new)
- Log bets from the scanner or by hand. Results settle automatically from NHL final scores; P/L, ROI and a running chart.
- **Closing-line value (CLV):** your price vs the fair price right before puck drop. The best early check that your edges are real.
- Stored locally in `data/bets.csv` (git-ignored).

### 🔍 Matchup

- **Schedule** – Pick a date and select a game (today or upcoming).
- **Rest & back-to-back** – Days rest for each team; back-to-back and “flew in from X” travel fatigue from schedule data.
- **Multi-game view** – Check “View all games tonight” to see every game on the selected date at a glance.
- **Rosters & health** – Active roster (and non-active when API provides it) for both teams.
- **Standings** – Points and rank context for the matchup.
- **News** – NHL RSS feed filtered to headlines mentioning either team.
- **Odds** – Moneyline, spreads, and totals from [The Odds API](https://the-odds-api.com/) (optional; API key in sidebar or .env).
- **Insights** – Rest advantage, standings, roster, and odds in one place with **confidence** (low/medium/high) and a **best bet** suggestion (ML lean from rest/standings/roster).
- **Export** – Download a Markdown report (pre-game notes) for the selected matchup; use Print → Save as PDF for PDF.

- **PP/PK rankings** — Power play and penalty kill % for both teams (from `api.nhle.com/stats/rest`), with edge insights when one team has a clear special-teams advantage.

### More context (see DATA_SOURCES.md)

- **DATA_SOURCES.md** lists where to get: referee assignment, public % / sharp money, reverse line movement, ATS record, situational trends, starter goalie, weather/outdoor. Some are free (e.g. scrape), others need paid APIs (OddsJam, Sportradar, The Odds API historical, SportsDataIO).

## Setup

1. **Clone or open the project** and create a virtual environment:

   ```bash
   cd "hockey stats"
   python -m venv venv
   venv\Scripts\activate   # Windows
   # source venv/bin/activate   # macOS/Linux
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Odds (optional):**  
   Get a free API key from [The Odds API](https://the-odds-api.com/) (500 requests/month on free tier).  
   Copy `.env.example` to `.env` and set:

   ```env
   ODDS_API_KEY=your_key_here
   ```

   On Streamlit Community Cloud, add `ODDS_API_KEY` under the app's **Settings → Secrets** instead.

   Credits: each refresh costs (markets × regions). The default `us` + `eu` with 3 markets is 6 credits, about 80 refreshes a month on the free tier.

   If you don’t set this, the app still runs; schedule, rosters, news, and insights will work, and odds will show a message to add the key.

## Run the app

From the project folder with your venv activated:

```bash
# Windows
.\venv\Scripts\python.exe -m streamlit run app.py

# or, if Streamlit is on your PATH after activating venv:
streamlit run app.py
```

Then open **http://localhost:8501** in your browser.

## Data sources

| Data        | Source | Auth |
|------------|--------|------|
| Schedule   | [NHL Stats API](https://statsapi.web.nhl.com/api/v1) | None |
| Rosters    | NHL Stats API (`/teams/:id/roster`) | None |
| Standings  | NHL Stats API (`/standings`) | None |
| News       | NHL RSS (e.g. to-rss.xyz) | None |
| Odds       | [The Odds API](https://the-odds-api.com/) | API key in `.env` |

## Project layout

- `app.py` – Streamlit UI and flow.
- `nhl_client.py` – Schedule, teams, rosters from NHL Stats API.
- `odds_client.py` – Fetch and match NHL odds from The Odds API.
- `news_client.py` – Fetch and filter NHL news from RSS.
- `analysis.py` – Build insights (rosters, standings, odds).
- `config.py` – Settings and env-loaded API keys.

## Notes

- **Roster status** comes from the NHL API `rosterStatus` (e.g. Y = active, I = injured). The “not active” list is everyone not on the active roster for that team.
- **Odds** are matched to games by team name; small naming differences between NHL and Odds API are handled with flexible matching.
- This app is for informational use only; it does not provide betting advice.

## Hosted copy (Azure)

Runs on Azure Container Apps in the Ingot sponsorship subscription (rg-bettinjimmy, Canada Central): https://bettinjimmy.proudflower-c4960394.canadacentral.azurecontainerapps.io

- Scales to zero when nobody is using it, so it costs pennies a month (a small Azure Files share holds bets, line history and settings). The first load after it's been idle takes about a minute.
- The container pulls `main` from GitHub when it starts. To ship changes: commit, then `.\deploy.ps1` (pushes and restarts it).
- `.\set-secrets.ps1` sets the Odds API key and the site password (it prompts; nothing is saved).

