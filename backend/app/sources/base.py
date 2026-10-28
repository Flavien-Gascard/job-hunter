"""Helpers shared by the source adapters."""

import html
import re
from datetime import datetime, timezone

_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6])[^>]*>", re.I)
_SPACES = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n\s*\n+")


def html_to_text(raw: str) -> str:
    """Strip HTML (sometimes double-escaped, as Greenhouse sends it) to plain text."""
    if not raw:
        return ""
    text = html.unescape(html.unescape(raw))
    text = _BLOCK.sub("\n", text)
    text = _TAG.sub("", text)
    text = _SPACES.sub(" ", text)
    return _BLANKS.sub("\n\n", text).strip()


def looks_remote(*fields: str) -> bool:
    return any("remote" in (f or "").lower() for f in fields)


def iso_from_ms(ms: int | None) -> str:
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
