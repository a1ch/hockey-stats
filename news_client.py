"""NHL news fetcher via RSS and optional team/keyword filtering."""
import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import feedparser
import requests

from config import NHL_NEWS_RSS

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    title: str
    link: str
    published: Optional[str]
    summary: str
    source: str


def fetch_nhl_news(rss_url: Optional[str] = None) -> list[NewsItem]:
    """Parse NHL RSS feed and return list of news items."""
    url = rss_url or NHL_NEWS_RSS
    try:
        feed = feedparser.parse(
            url,
            request_headers={"User-Agent": "NHL-Matchup-App/1.0"},
        )
    except Exception as e:
        logger.warning("RSS parse failed: %s", e)
        return []

    items: list[NewsItem] = []
    for entry in feed.entries[:50]:
        items.append(
            NewsItem(
                title=entry.get("title", ""),
                link=entry.get("link", ""),
                published=entry.get("published"),
                summary=entry.get("summary", "")[:500] if entry.get("summary") else "",
                source=feed.feed.get("title", "NHL"),
            )
        )
    return items


def filter_news_for_matchup(
    items: list[NewsItem],
    home_team_name: str,
    away_team_name: str,
    limit: int = 15,
) -> list[NewsItem]:
    """Filter news to items mentioning either team (by name or city/abbrev)."""
    if not home_team_name and not away_team_name:
        return items[:limit]

    # Build keywords: full name + common abbrevs (e.g. "Rangers", "NYR")
    def keywords(name: str) -> set[str]:
        if not name:
            return set()
        # "New York Rangers" -> {"new york rangers", "rangers", "ny rangers"}
        s = name.lower()
        out = {s}
        words = s.split()
        if len(words) > 1:
            out.add(words[-1])  # "Rangers"
            out.add(" ".join(words[-2:]))  # "NY Rangers"
        return out

    home_kw = keywords(home_team_name)
    away_kw = keywords(away_team_name)
    all_kw = home_kw | away_kw

    def score(item: NewsItem) -> int:
        text = (item.title + " " + item.summary).lower()
        return sum(1 for k in all_kw if k in text)

    scored = [(score(i), i) for i in items]
    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored if _ > 0][:limit] or items[:limit]
