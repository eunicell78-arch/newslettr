"""Deterministic publish-date extraction for article URLs.

Priority order:
1. JSON-LD  datePublished / dateCreated
2. <meta>   article:published_time / og:published_time / pubdate / date
3. Body-text regex  ("Published on March 25, 2026" / "Published: March 11, 2026")
"""

import re
import json
import logging
from datetime import datetime, timezone
from typing import Optional

try:
    import requests
    from bs4 import BeautifulSoup
    _DEPS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _DEPS_AVAILABLE = False

logger = logging.getLogger(__name__)

# Month name → number (English)
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# "Published on March 25, 2026" or "Published: March 11, 2026"
_PUBLISHED_TEXT_RE = re.compile(
    r"[Pp]ublished\s*(?:on|:)\s*"
    r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})",
)

# Generic "Month DD, YYYY" anywhere in text (fallback)
_GENERIC_DATE_RE = re.compile(
    r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b",
)

# ISO-8601 prefix (e.g. "2026-03-25" or "2026-03-25T10:00:00Z")
_ISO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _parse_iso(value: str) -> Optional[datetime]:
    """Parse an ISO-8601 date/datetime string → UTC-aware datetime."""
    if not value:
        return None
    m = _ISO_DATE_RE.search(value)
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_text_date(text: str, strict: bool = True) -> Optional[datetime]:
    """Parse a textual English date string like 'March 25, 2026'.

    When *strict* is True only the 'Published on/: ...' prefix form is tried.
    When *strict* is False a broader generic "Month DD, YYYY" search is used.
    """
    pattern = _PUBLISHED_TEXT_RE if strict else _GENERIC_DATE_RE
    m = pattern.search(text)
    if not m:
        return None
    month_str, day_str, year_str = m.group(1), m.group(2), m.group(3)
    month = _MONTHS.get(month_str.lower())
    if not month:
        return None
    try:
        return datetime(int(year_str), month, int(day_str), tzinfo=timezone.utc)
    except ValueError:
        return None


def _extract_from_json_ld(soup: "BeautifulSoup") -> Optional[datetime]:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        # data can be a list or a single dict
        items = data if isinstance(data, list) else [data]
        for item in items:
            for key in ("datePublished", "dateCreated"):
                val = item.get(key) if isinstance(item, dict) else None
                if val:
                    dt = _parse_iso(val)
                    if dt:
                        return dt
    return None


def _extract_from_meta(soup: "BeautifulSoup") -> Optional[datetime]:
    candidates = [
        # (attribute_name, attribute_value, content_attr)
        ("property", "article:published_time", "content"),
        ("name",     "article:published_time", "content"),
        ("property", "og:published_time",       "content"),
        ("name",     "og:published_time",        "content"),
        ("name",     "pubdate",                  "content"),
        ("name",     "date",                     "content"),
        ("itemprop", "datePublished",            "content"),
        ("itemprop", "datePublished",            "datetime"),
    ]
    for attr, value, content_attr in candidates:
        tag = soup.find("meta", {attr: value})
        if tag:
            val = tag.get(content_attr, "")
            dt = _parse_iso(val)
            if dt:
                return dt
    # Also look for <time> elements with datetime attr
    for time_tag in soup.find_all("time", datetime=True):
        dt = _parse_iso(time_tag["datetime"])
        if dt:
            return dt
    return None


def _extract_from_body_text(soup: "BeautifulSoup") -> Optional[datetime]:
    text = soup.get_text(" ", strip=True)
    # Try strict form first ("Published on …" / "Published: …")
    dt = _parse_text_date(text, strict=True)
    if dt:
        return dt
    # Fall back to generic "Month DD, YYYY" anywhere in visible text
    return _parse_text_date(text, strict=False)


def extract_publish_date(url: str, timeout: int = 10) -> Optional[datetime]:
    """Fetch *url* and return its publish date as a UTC-aware datetime.

    Returns ``None`` when the date cannot be determined (network error,
    parse failure, etc.).
    """
    if not _DEPS_AVAILABLE:  # pragma: no cover
        logger.warning("requests/beautifulsoup4 not installed; skipping date extraction")
        return None

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NewslettrBot/1.0)"},
            allow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        return None

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        logger.debug("Failed to parse HTML for %s: %s", url, exc)
        return None

    # Try each strategy in priority order
    for strategy in (_extract_from_json_ld, _extract_from_meta, _extract_from_body_text):
        dt = strategy(soup)
        if dt:
            return dt

    return None


def is_within_cutoff(dt: Optional[datetime], cutoff: datetime) -> bool:
    """Return True iff *dt* is not None and on-or-after *cutoff*."""
    if dt is None:
        return False
    # Make both offset-aware for comparison
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    return dt >= cutoff
