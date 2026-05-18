"""Claude sentiment classifier for news articles. Uses Haiku 4.5 with
structured outputs and a cache-friendly system prompt."""
from __future__ import annotations

import logging
import time
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, Field

from app.config import get_settings

log = logging.getLogger(__name__)


# Pydantic schema → drives Anthropic structured outputs + validation in one shot.
class ClassifierOutput(BaseModel):
    sentiment_label: Literal["bullish", "bearish", "neutral"]
    sentiment_score: float = Field(..., ge=-1.0, le=1.0, description="−1.0 max bearish, +1.0 max bullish")
    confidence: float = Field(..., ge=0.0, le=1.0)
    event_type: Literal[
        "earnings", "guidance", "fda", "legal", "executive",
        "macro", "product", "partnership", "regulatory", "other", "none"
    ]
    rationale: str = Field(..., max_length=400)


SYSTEM_PROMPT = """You are a financial-news sentiment classifier.

You receive a single news headline (plus a short summary, if available) about a
publicly traded company, and you return a structured assessment of how the
news affects that ticker's near-term price expectation.

GUIDELINES
- "bullish" means the news is likely to support a higher near-term price.
  Examples: earnings beat, raised guidance, FDA approval, product launch,
  large new contract, favorable regulatory ruling.
- "bearish" means the news is likely to drag the near-term price.
  Examples: earnings miss, lowered guidance, recall, lawsuit, executive
  departure under bad terms, downgrade, fraud allegation.
- "neutral" means the headline carries no clear directional signal, or is
  routine corporate information (dividend announcement on schedule, minor
  reshuffle, vague PR copy with no facts).
- "sentiment_score" should be calibrated: a clear earnings beat is +0.6 to
  +0.9; a vague mention is closer to 0; a confirmed major lawsuit is −0.7
  or worse. Reserve |score| > 0.85 for very high-conviction events.
- "confidence" is your meta-uncertainty — lower it when the headline is
  ambiguous, sarcastic, or you only see a fragment.
- "event_type" is the dominant category of the news; pick "none" for pure
  market commentary.
- "rationale" is one or two short sentences explaining your call.
- Do NOT speculate beyond the text. If the headline says "Apple denies
  rumor about layoffs", do not infer that layoffs are happening.
- Do NOT hallucinate numbers (prices, percentages) that aren't in the text.

Return ONLY the structured JSON the schema requires."""


_settings = get_settings()
_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not _settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        _client = anthropic.Anthropic(api_key=_settings.anthropic_api_key)
    return _client


# Haiku 4.5 input/output prices ($/1M tokens). Updated 2026-05.
_PRICE_IN = 1.00 / 1_000_000
_PRICE_OUT = 5.00 / 1_000_000


def classify_article(
    *,
    headline: str,
    summary: str | None,
    ticker: str,
    company_name: str,
    sector: str | None,
) -> tuple[ClassifierOutput, dict]:
    """Returns (parsed output, metadata dict with tokens/latency/cost).
    Raises anthropic.APIError subclasses on API failure."""
    client = get_client()

    user_text = (
        f"TICKER: {ticker} ({company_name})\n"
        f"SECTOR: {sector or 'unknown'}\n\n"
        f"HEADLINE: {headline.strip()}\n"
    )
    if summary:
        # Cap summary to keep prompts tight + cache-friendly.
        user_text += f"SUMMARY: {summary.strip()[:1200]}\n"

    t0 = time.monotonic()
    try:
        response = client.messages.parse(
            model=_settings.claude_model,
            max_tokens=_settings.classify_max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_text}],
            output_format=ClassifierOutput,
        )
    except anthropic.BadRequestError:
        log.exception("classify bad request — payload likely malformed")
        raise

    latency_ms = int((time.monotonic() - t0) * 1000)

    usage = response.usage
    input_tokens = (usage.input_tokens or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0)
    output_tokens = usage.output_tokens or 0
    cost = (input_tokens * _PRICE_IN) + (output_tokens * _PRICE_OUT)

    meta = {
        "model": _settings.claude_model,
        "input_tokens": usage.input_tokens or 0,
        "output_tokens": output_tokens,
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_creation_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        "latency_ms": latency_ms,
        "cost_usd": round(cost, 6),
    }

    return response.parsed_output, meta  # type: ignore[return-value]
