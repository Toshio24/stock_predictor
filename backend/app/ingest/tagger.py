"""Ticker tagger. For Finnhub /company-news the symbol is already known, so we
just match it. For /news (general) we scan headline+summary for whole-word
matches against our tracked-ticker set."""
import re
from typing import Iterable

# Cache so we don't rebuild the regex every call.
_PATTERN_CACHE: tuple[frozenset[str], re.Pattern] | None = None


def _pattern(symbols: Iterable[str]) -> re.Pattern:
    global _PATTERN_CACHE
    key = frozenset(symbols)
    if _PATTERN_CACHE and _PATTERN_CACHE[0] == key:
        return _PATTERN_CACHE[1]
    # match $TICKER or whole-word TICKER (uppercase only, 1-5 chars)
    escaped = "|".join(re.escape(s) for s in sorted(key, key=len, reverse=True))
    pat = re.compile(r"(?:\$)?\b(" + escaped + r")\b")
    _PATTERN_CACHE = (key, pat)
    return pat


def find_tickers(text: str, tracked: Iterable[str]) -> set[str]:
    if not text:
        return set()
    return set(_pattern(tracked).findall(text))
