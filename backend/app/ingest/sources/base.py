"""Common source interface.

Every news source produces a stream of `RawArticle`s. The ingest worker
normalizes them into `Article` ORM rows (with `ArticleTicker` links) and
hands them off to the classifier. Source modules don't touch the DB."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional, Protocol


@dataclass
class RawArticle:
    # external_id helps when the source has stable IDs (Finnhub, Reddit, HN);
    # falls back to url_hash for RSS sources.
    external_id: Optional[str]
    source: str               # 'finnhub' | 'yahoo' | 'sec_edgar' | 'google_news' | 'reddit' | 'hackernews'
    source_url: str
    headline: str
    summary: str = ""
    image_url: Optional[str] = None
    category: str = "news"    # 'news' | 'filing' | 'social' | 'tech'
    published_at: Optional[datetime] = None
    # Symbols this article is explicitly known to be about (from per-ticker
    # fetches). Empty for global feeds — the worker will run the regex tagger
    # against the headline + summary.
    ticker_hints: list[str] = field(default_factory=list)


class Source(Protocol):
    """A source knows how to produce a batch of RawArticles per cycle.
    The protocol intentionally keeps two flavors:
      - per-ticker sources accept a ticker symbol (Yahoo, SEC EDGAR, Google
        News, Finnhub /company-news)
      - global sources fetch once and tag downstream (Reddit, HN, Finnhub /news)
    A concrete source implements whichever one fits."""

    name: str           # display name used in DB Article.source
    cadence_seconds: int

    async def fetch_per_ticker(self, symbol: str) -> Iterable[RawArticle]:
        ...

    async def fetch_global(self, tracked: dict[str, int]) -> Iterable[RawArticle]:
        ...
