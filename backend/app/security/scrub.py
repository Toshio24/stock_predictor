"""Log scrubbing — strip anything that looks like a secret out of log
records before they hit stdout / a log aggregator / Sentry.

Why: even with careful coding, libraries (httpx, anthropic, sqlalchemy) can
include URLs, headers, or query params in their own log lines or exception
messages. A single `?token=<finnhub key>` in a retry log line leaks the
key forever. This filter is attached to the root logger at startup so
every record passes through it."""
from __future__ import annotations

import logging
import re
from typing import Iterable


# Order matters: most specific first. Each pattern captures the secret in
# group 1; we replace just the secret, not the surrounding context, so log
# lines remain readable.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Anthropic / OpenAI-style keys: sk-..., sk-ant-...
    (re.compile(r"(sk-[A-Za-z0-9_\-]{20,})"), "sk-***REDACTED***"),
    # Finnhub tokens are 40-char hex-ish strings, but we only redact when
    # they appear in a clearly-credentialed context — otherwise we'd eat
    # innocent IDs. Catch ?token=..., &token=..., "token": "...".
    (re.compile(r"([?&]token=)([^&\s\"']+)"), r"\1***REDACTED***"),
    (re.compile(r'("token"\s*:\s*")([^"]+)(")'), r"\1***REDACTED***\3"),
    # Bearer / Basic auth headers.
    (re.compile(r"(Bearer\s+)([A-Za-z0-9_\-\.=]+)"), r"\1***REDACTED***"),
    (re.compile(r"(Basic\s+)([A-Za-z0-9+/=]+)"), r"\1***REDACTED***"),
    # Anthropic header.
    (re.compile(r"(x-api-key:\s*)(\S+)", re.IGNORECASE), r"\1***REDACTED***"),
    # FRED / generic api_key= URL params.
    (re.compile(r"([?&]api_key=)([^&\s\"']+)"), r"\1***REDACTED***"),
    # Firebase service account private key blocks.
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
     "-----BEGIN PRIVATE KEY-----***REDACTED***-----END PRIVATE KEY-----"),
    # JSON Web Tokens (3 base64 segments separated by dots, eyJ... prefix).
    (re.compile(r"(eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})"), "eyJ***REDACTED***"),
    # Postgres URLs with passwords: postgres://user:password@host/db
    (re.compile(r"(://[^:/\s]+:)([^@\s]+)(@)"), r"\1***REDACTED***\3"),
]


def scrub(text: str) -> str:
    """Apply every redaction pattern to a string. Safe on non-secret input."""
    if not text:
        return text
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


class SecretScrubbingFilter(logging.Filter):
    """Logging filter that scrubs the formatted message AND any string args.

    We scrub `record.msg`, every arg, and `record.exc_text` (the formatted
    traceback) — that's where requests-/httpx-style exceptions tend to
    embed the offending URL with the token in it."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _maybe_scrub(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(_maybe_scrub(a) for a in record.args)
        if record.exc_text:
            record.exc_text = scrub(record.exc_text)
        return True


def _maybe_scrub(a):
    """Apply scrub() to a log arg. Tricky because:
      - bool/int/float MUST stay as-is or %d / %f format specifiers crash
      - str gets scrubbed in place
      - Anything else (httpx.URL, exceptions, dicts) gets stringified
        and scrubbed — this is the case that bit us when httpx logs the
        request URL as a URL object, not a str. The URL's __str__ contains
        the API token, but isinstance(url, str) is False, so a naive
        "only scrub strings" filter lets the secret through.
    """
    if a is None:
        return a
    if isinstance(a, bool):     # bool is a subclass of int — check first
        return a
    if isinstance(a, (int, float)):
        return a
    if isinstance(a, str):
        return scrub(a)
    # Complex object — stringify so we can scrub its representation. The
    # formatter would have called str() anyway, so this doesn't change
    # the rendered output (other than the redaction itself).
    try:
        return scrub(str(a))
    except Exception:
        return a


_GLOBAL_FILTER = SecretScrubbingFilter()


class _ScrubbingHandlerWrapper(logging.Handler):
    """Wraps an existing handler and runs the scrubbing filter on every
    record before delegating. Belt-and-braces because adding a filter to
    `handler.filters` works in theory but has surprised us in practice
    when third-party loggers (httpx) bypass the expected chain."""

    def __init__(self, inner: logging.Handler) -> None:
        super().__init__(level=inner.level)
        self._inner = inner

    def emit(self, record: logging.LogRecord) -> None:
        _GLOBAL_FILTER.filter(record)
        self._inner.emit(record)

    def handle(self, record: logging.LogRecord) -> bool:
        _GLOBAL_FILTER.filter(record)
        return self._inner.handle(record)

    def setFormatter(self, fmt) -> None:
        self._inner.setFormatter(fmt)

    def flush(self) -> None:
        self._inner.flush()


def install(loggers: Iterable[str] = ("",)) -> None:
    """Attach the scrubbing filter so EVERY log record passes through it
    before being written.

    Belt-and-braces approach (three layers):
      1. Add filter to every existing handler on every existing logger.
      2. Add filter to root + named loggers (catches direct emissions).
      3. Wrap every root handler in a scrubbing wrapper so records that
         somehow skip the filter chain (third-party loggers we've seen do
         this) still get scrubbed at the emit() boundary.

    Idempotent — calling install() twice is safe; the wrapper detects
    already-wrapped handlers.
    """
    f = _GLOBAL_FILTER
    seen: set[int] = set()

    root = logging.getLogger()
    targets: list[logging.Logger] = [root, *[
        l for l in logging.Logger.manager.loggerDict.values()
        if isinstance(l, logging.Logger)
    ]]
    # Layer 1: filter on every known handler.
    for logger in targets:
        for handler in logger.handlers:
            if id(handler) in seen:
                continue
            seen.add(id(handler))
            handler.addFilter(f)

    # Layer 2: filter on the loggers themselves.
    for name in loggers:
        logging.getLogger(name).addFilter(f)

    # Layer 3: wrap root's handlers so emit() runs the filter unconditionally.
    wrapped_handlers = []
    for h in list(root.handlers):
        if isinstance(h, _ScrubbingHandlerWrapper):
            wrapped_handlers.append(h)
            continue
        wrapper = _ScrubbingHandlerWrapper(h)
        wrapped_handlers.append(wrapper)
    root.handlers = wrapped_handlers

    # Emit a one-time confirmation log so operators can verify the
    # scrubber is live. This message itself gets scrubbed too.
    logging.getLogger(__name__).info(
        "secret scrubber installed (%d handler wrapper(s), %d known loggers)",
        len(wrapped_handlers), len(targets),
    )
