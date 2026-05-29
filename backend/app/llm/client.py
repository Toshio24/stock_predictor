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
    is_material: bool = Field(
        ...,
        description="True only if this article carries actionable, new "
                    "information that a rational investor would consider "
                    "moving the price. False for round-ups, SEO listicles, "
                    "opinion pieces, rehashes of old news, generic social "
                    "posts, and tangential mentions.",
    )
    time_horizon: Literal["intraday", "short_term", "medium_term", "long_term", "none"] = Field(
        ...,
        description="Over what window does this news matter? Use 'none' "
                    "for non-material articles.",
    )
    rationale: str = Field(..., max_length=400)


SYSTEM_PROMPT = """You are a financial-news sentiment classifier whose
output feeds a trading-signal aggregator. Your job has two equally
important parts: judging direction AND judging whether the article
carries any signal at all.

You receive a single news article (headline + optional summary) about a
publicly traded company, and you return a structured assessment.

# DIRECTION (sentiment_label, sentiment_score)
- "bullish" — likely to support a higher near-term price. Examples:
  earnings beat, raised guidance, FDA approval, product launch, large
  new contract, favorable regulatory ruling.
- "bearish" — likely to drag the near-term price. Examples: earnings
  miss, lowered guidance, recall, lawsuit, executive departure under
  bad terms, downgrade, fraud allegation, going-concern doubt.
- "neutral" — no clear directional read, or routine corporate filing.
- Calibrate sentiment_score:
  - A clear earnings beat is +0.6 to +0.9
  - A confirmed major lawsuit is −0.7 or worse
  - A vague mention is closer to 0
  - Reserve |score| > 0.85 for very high-conviction events

# MATERIALITY (is_material) — be strict here
Set is_material=true ONLY if the article carries actionable, NEW
information that a rational investor would price in.

Set is_material=false (the default for most low-quality content) for:
- Round-ups and listicles: "3 AI stocks to watch", "Top 5 dividend
  picks", "Better Buy: X or Y"
- Opinion / commentary with no new facts ("Why I'm still bullish on X")
- Old news being re-summarized ("Last week's earnings show…")
- Generic explainers ("Here's why X stock has been volatile")
- Analyst hot-takes without an actual rating change ("Analyst is
  cautiously optimistic on X")
- Routine SEC filings that aren't material events: bylaw amendments,
  Form 4 insider sales below 1% of holdings, prospectus supplements,
  ARS auction rate notices
- Tangential mentions: the article is about Y but parenthetically
  names X
- Social-media questions ("is NVDA going to tank?"), memes, low-effort
  speculation
- Repeated coverage of the same event already classified (you can't
  see history, but if the headline is generic-sounding and lacks
  concrete numbers/specifics, lean toward false)

Set is_material=true for things like:
- Earnings reports with actual numbers
- Guidance revisions
- M&A announcements
- Regulatory rulings (FDA, DoJ, antitrust, court orders)
- Material SEC filings: 8-K material events, 10-Q, 10-K, 13-D activist
  stakes
- Major contracts, customer wins, or losses
- Executive changes at C-suite level
- Plant fires, recalls, breaches, major operational disruptions

When is_material=false, you must still return a sentiment_label
(usually "neutral") and a low confidence (≤ 0.3), because the
aggregator downstream filters non-material analyses out — your job
is just to flag the noise.

# TIME HORIZON
- "intraday" — moves the price today (breaking news, real-time guidance)
- "short_term" — days to a few weeks (earnings, contract wins)
- "medium_term" — months (strategic shift, regulatory ruling)
- "long_term" — quarters+ (industry trend, leadership change)
- "none" — pair with is_material=false

# CONFIDENCE
Lower confidence when:
- The headline is ambiguous or sarcastic
- You only see a fragment
- The article is from a low-quality source (random Motley Fool, Reddit
  post, anonymous blog)
- The article is non-material — cap confidence at 0.3

# HARD RULES
- Do NOT speculate beyond the text. "Apple denies rumor of layoffs"
  does NOT mean layoffs are happening.
- Do NOT hallucinate numbers (prices, percentages) that aren't in the
  text.
- "rationale" is one or two short sentences explaining your call.
- Return ONLY the structured JSON the schema requires."""


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


# Structured output via tool use: the Pydantic schema becomes the tool's
# input_schema, and we force Claude to call it. This is the supported path
# on anthropic==0.39.0 (which has no messages.parse()).
_TOOL_NAME = "record_classification"
_CLASSIFIER_TOOL = {
    "name": _TOOL_NAME,
    "description": "Record the structured sentiment classification for the article.",
    "input_schema": ClassifierOutput.model_json_schema(),
}


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
        response = client.messages.create(
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
            tools=[_CLASSIFIER_TOOL],
            # Force the model to return its answer as a call to our tool, so
            # the output is always a structured object matching the schema.
            tool_choice={"type": "tool", "name": _TOOL_NAME},
        )
    except anthropic.BadRequestError:
        log.exception("classify bad request — payload likely malformed")
        raise

    latency_ms = int((time.monotonic() - t0) * 1000)

    # Pull the forced tool call out of the response and validate it against
    # the Pydantic model. tool_choice guarantees a tool_use block is present.
    tool_input = next(
        (block.input for block in response.content if block.type == "tool_use"),
        None,
    )
    if tool_input is None:
        raise ValueError("classifier returned no tool_use block")
    parsed = ClassifierOutput.model_validate(tool_input)

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

    return parsed, meta
