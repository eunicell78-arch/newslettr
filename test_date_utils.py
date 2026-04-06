"""Minimal tests for date_utils.extract_publish_date and helpers."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from date_utils import (
    _parse_text_date,
    _parse_iso,
    _extract_from_json_ld,
    _extract_from_meta,
    _extract_from_body_text,
    extract_publish_date,
    is_within_cutoff,
)

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

pytestmark = pytest.mark.skipif(not BS4_AVAILABLE, reason="beautifulsoup4 not installed")


# ── _parse_iso ─────────────────────────────────────────────────────────────


def test_parse_iso_full_datetime():
    dt = _parse_iso("2026-03-25T14:00:00Z")
    assert dt == datetime(2026, 3, 25, tzinfo=timezone.utc)


def test_parse_iso_date_only():
    dt = _parse_iso("2026-03-11")
    assert dt == datetime(2026, 3, 11, tzinfo=timezone.utc)


def test_parse_iso_none_on_invalid():
    assert _parse_iso("") is None
    assert _parse_iso("not-a-date") is None


# ── _parse_text_date ───────────────────────────────────────────────────────


def test_parse_text_date_published_on():
    dt = _parse_text_date("Published on March 25, 2026", strict=True)
    assert dt == datetime(2026, 3, 25, tzinfo=timezone.utc)


def test_parse_text_date_published_colon():
    dt = _parse_text_date("Published: March 11, 2026", strict=True)
    assert dt == datetime(2026, 3, 11, tzinfo=timezone.utc)


def test_parse_text_date_generic_fallback():
    dt = _parse_text_date("Posted March 25, 2026 by admin", strict=False)
    assert dt == datetime(2026, 3, 25, tzinfo=timezone.utc)


def test_parse_text_date_no_match():
    assert _parse_text_date("No date here", strict=True) is None
    assert _parse_text_date("No date here", strict=False) is None


def test_parse_text_date_case_insensitive_month():
    dt = _parse_text_date("Published on MARCH 25, 2026", strict=True)
    assert dt == datetime(2026, 3, 25, tzinfo=timezone.utc)


def test_parse_text_date_abbreviated_month():
    dt = _parse_text_date("Published: Mar 11, 2026", strict=True)
    assert dt == datetime(2026, 3, 11, tzinfo=timezone.utc)


# ── JSON-LD extraction ─────────────────────────────────────────────────────


def test_extract_from_json_ld_date_published():
    html = """<html><head>
    <script type="application/ld+json">
    {"@type": "Article", "datePublished": "2026-03-25T10:00:00Z"}
    </script></head><body></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    dt = _extract_from_json_ld(soup)
    assert dt == datetime(2026, 3, 25, tzinfo=timezone.utc)


def test_extract_from_json_ld_date_created_fallback():
    html = """<html><head>
    <script type="application/ld+json">
    {"@type": "Article", "dateCreated": "2026-03-11"}
    </script></head><body></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    dt = _extract_from_json_ld(soup)
    assert dt == datetime(2026, 3, 11, tzinfo=timezone.utc)


def test_extract_from_json_ld_array():
    html = """<html><head>
    <script type="application/ld+json">
    [{"@type": "Article", "datePublished": "2026-03-20"}]
    </script></head><body></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    dt = _extract_from_json_ld(soup)
    assert dt == datetime(2026, 3, 20, tzinfo=timezone.utc)


def test_extract_from_json_ld_no_date():
    html = """<html><head>
    <script type="application/ld+json">{"@type": "Article"}</script>
    </head><body></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_from_json_ld(soup) is None


# ── Meta tag extraction ────────────────────────────────────────────────────


def test_extract_from_meta_article_published_time():
    html = """<html><head>
    <meta property="article:published_time" content="2026-03-25T08:00:00+00:00"/>
    </head><body></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    dt = _extract_from_meta(soup)
    assert dt == datetime(2026, 3, 25, tzinfo=timezone.utc)


def test_extract_from_meta_og_published_time():
    html = """<html><head>
    <meta property="og:published_time" content="2026-03-11"/>
    </head><body></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    dt = _extract_from_meta(soup)
    assert dt == datetime(2026, 3, 11, tzinfo=timezone.utc)


def test_extract_from_meta_time_tag():
    html = """<html><body>
    <time datetime="2026-03-25">March 25, 2026</time>
    </body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    dt = _extract_from_meta(soup)
    assert dt == datetime(2026, 3, 25, tzinfo=timezone.utc)


# ── Body-text extraction ───────────────────────────────────────────────────


def test_extract_from_body_text_published_on():
    html = """<html><body><p>Published on March 25, 2026</p></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    dt = _extract_from_body_text(soup)
    assert dt == datetime(2026, 3, 25, tzinfo=timezone.utc)


def test_extract_from_body_text_published_colon():
    html = """<html><body><p>Published: March 11, 2026</p></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    dt = _extract_from_body_text(soup)
    assert dt == datetime(2026, 3, 11, tzinfo=timezone.utc)


def test_extract_from_body_text_no_date():
    html = """<html><body><p>No date information here.</p></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_from_body_text(soup) is None


# ── is_within_cutoff ──────────────────────────────────────────────────────


def test_is_within_cutoff_inside():
    cutoff = datetime(2026, 3, 30, tzinfo=timezone.utc)
    dt = datetime(2026, 4, 1, tzinfo=timezone.utc)
    assert is_within_cutoff(dt, cutoff) is True


def test_is_within_cutoff_on_boundary():
    cutoff = datetime(2026, 3, 30, tzinfo=timezone.utc)
    dt = datetime(2026, 3, 30, tzinfo=timezone.utc)
    assert is_within_cutoff(dt, cutoff) is True


def test_is_within_cutoff_before():
    cutoff = datetime(2026, 3, 30, tzinfo=timezone.utc)
    dt = datetime(2026, 3, 25, tzinfo=timezone.utc)
    assert is_within_cutoff(dt, cutoff) is False


def test_is_within_cutoff_none():
    cutoff = datetime(2026, 3, 30, tzinfo=timezone.utc)
    assert is_within_cutoff(None, cutoff) is False


def test_is_within_cutoff_naive_dt():
    cutoff = datetime(2026, 3, 30, tzinfo=timezone.utc)
    dt = datetime(2026, 4, 1)  # naive
    assert is_within_cutoff(dt, cutoff) is True


# ── extract_publish_date (integration with mocked HTTP) ───────────────────


def _make_response(html_text: str, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html_text
    resp.raise_for_status = MagicMock()
    return resp


@patch("date_utils.requests.get")
def test_extract_publish_date_via_json_ld(mock_get):
    html = """<html><head>
    <script type="application/ld+json">
    {"datePublished": "2026-04-01T00:00:00Z"}
    </script></head><body></body></html>"""
    mock_get.return_value = _make_response(html)
    dt = extract_publish_date("https://example.com/article")
    assert dt == datetime(2026, 4, 1, tzinfo=timezone.utc)


@patch("date_utils.requests.get")
def test_extract_publish_date_via_meta(mock_get):
    html = """<html><head>
    <meta property="article:published_time" content="2026-04-02"/>
    </head><body></body></html>"""
    mock_get.return_value = _make_response(html)
    dt = extract_publish_date("https://example.com/article")
    assert dt == datetime(2026, 4, 2, tzinfo=timezone.utc)


@patch("date_utils.requests.get")
def test_extract_publish_date_via_body_published_on(mock_get):
    html = """<html><body><p>Published on March 25, 2026</p></body></html>"""
    mock_get.return_value = _make_response(html)
    dt = extract_publish_date("https://evchargingstations.com/some-article/")
    assert dt == datetime(2026, 3, 25, tzinfo=timezone.utc)


@patch("date_utils.requests.get")
def test_extract_publish_date_via_body_published_colon(mock_get):
    html = """<html><body><p>Published: March 11, 2026</p></body></html>"""
    mock_get.return_value = _make_response(html)
    dt = extract_publish_date("https://example.com/old-article/")
    assert dt == datetime(2026, 3, 11, tzinfo=timezone.utc)


@patch("date_utils.requests.get")
def test_extract_publish_date_network_error(mock_get):
    mock_get.side_effect = Exception("connection refused")
    assert extract_publish_date("https://example.com/article") is None


@patch("date_utils.requests.get")
def test_extract_publish_date_no_date_found(mock_get):
    html = """<html><body><p>No date here.</p></body></html>"""
    mock_get.return_value = _make_response(html)
    assert extract_publish_date("https://example.com/nodatearticle/") is None
