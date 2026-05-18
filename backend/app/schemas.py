from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SignalOut(BaseModel):
    """Matches the shape the Node frontend expects from data/mock.js."""
    ticker: str
    name: str
    sector: Optional[str] = None
    signal: str = Field(..., description="bullish | bearish | neutral")
    price: float = 0.0
    change: float = 0.0
    score: int = 50
    confidence: int = 50
    spark: list[float] = []
    rationale: Optional[str] = None
    updatedAt: str


class NewsOut(BaseModel):
    id: int
    headline: str
    source: str
    category: Optional[str] = None
    sentiment: str = "neutral"
    tickers: list[str] = []
    summary: Optional[str] = None
    url: Optional[str] = None
    timeAgo: str
    featured: bool = False


class TickerDetail(BaseModel):
    symbol: str
    name: str
    sector: Optional[str]
    signal: SignalOut
    news: list[NewsOut]


class SearchResult(BaseModel):
    tickers: list[dict]
    pages: list[dict]
