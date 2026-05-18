"""Cheap heuristic filter: catches the most obvious noise headlines BEFORE
we pay Claude to classify them. We're conservative — anything that might
be real news goes to Claude. This only drops the high-confidence junk:
listicles, "X vs Y" comparisons, generic explainers, opinion pieces,
Reddit question posts.

Articles flagged here are still written to the DB so they show up in the
news feed; we just skip the LLM call and pre-fill them as is_material=False."""
from __future__ import annotations

import re

# Patterns matched against the headline (case-insensitive). Each was picked
# from real Yahoo/Google News/Motley Fool output during dev.
NOISE_PATTERNS: list[re.Pattern] = [
    # Listicles: "3 AI Stocks", "Top 5 Dividend...", "10 Stocks to Buy"
    re.compile(r"^\s*\d+\s+\S+\s+stocks?\s+to\s+(watch|buy|sell|own)\b", re.I),
    re.compile(r"^\s*(top|best)\s+\d+\s+\S+\s+stocks?\b", re.I),

    # "Better Buy: X or Y" / "X vs Y" comparisons
    re.compile(r"^\s*better\s+buy\b", re.I),
    re.compile(r"^\S+\s+vs\.?\s+\S+\s*:?\s+which\b", re.I),

    # Opinion / commentary framings
    re.compile(r"^\s*why\s+(i'?m|we'?re)\s+(still\s+)?(bullish|bearish)\b", re.I),
    re.compile(r"\bmy\s+top\s+\d*\s*\S+\s+stocks?\b", re.I),
    re.compile(r"\bone\s+stock\s+to\s+(buy|own|watch)\b", re.I),
    re.compile(r"\bcould\s+\S+\s+stock\s+be\s+the\s+next\b", re.I),
    re.compile(r"^\s*(here'?s|here\s+is)\s+why\b", re.I),

    # Reddit / social-style question titles
    re.compile(r"^\s*is\s+\S+\s+(going\s+to|gonna)\s+(tank|moon|crash|explode)\b", re.I),
    re.compile(r"^\s*what\s+(do\s+you\s+think|should\s+i\s+do)\b", re.I),
    re.compile(r"^\s*rate\s+my\s+(portfolio|picks)\b", re.I),

    # Round-ups / weekly discussion threads
    re.compile(r"\b(weekly|monthly|quarterly)\s+(discussion|thread|recap|wrap)\b", re.I),
    re.compile(r"\bahead\s+of\s+the\s+open\b", re.I),

    # Crypto/retail pump speak when not paired with a concrete event
    re.compile(r"\b(to\s+the\s+moon|🚀|diamond\s+hands)\b", re.I),
]


# Headlines containing any of these are NEVER filtered out — they're almost
# always real events even if the surrounding wrapper looks fluffy.
MATERIAL_OVERRIDE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(earnings|revenue|guidance|beat|miss|raises?|lowers?|cuts?)\b", re.I),
    re.compile(r"\b(FDA|DoJ|SEC\s+investigation|recall|lawsuit|settlement|injunction)\b", re.I),
    re.compile(r"\b(acquir(es?|ing|ed|ition)|merger|spin[\s-]?off|IPO|going\s+private)\b", re.I),
    re.compile(r"\b(8-K|10-K|10-Q|13-D|6-K|S-1)\b", re.I),
    re.compile(r"\b(CEO|CFO|COO|CTO|chair(man|woman|person))\b.*\b(resigns?|steps?\s+down|fired|appointed|hires?)\b", re.I),
    re.compile(r"\b(contract|deal|partnership)\s+(with|worth|valued)\b", re.I),
    re.compile(r"\b(downgrade|upgrade)d?\s+(by|from|to)\b", re.I),
    re.compile(r"\b\$\d+(\.\d+)?[BMK]?\b"),   # any dollar figure with magnitude
]


def is_obvious_noise(headline: str, source: str | None = None) -> bool:
    """Return True only when the headline matches a noise pattern AND
    no materiality override fires. Conservative by design: when in doubt,
    let Claude judge it."""
    if not headline:
        return False
    h = headline.strip()

    # Materiality override always wins.
    for p in MATERIAL_OVERRIDE_PATTERNS:
        if p.search(h):
            return False

    for p in NOISE_PATTERNS:
        if p.search(h):
            return True

    return False
