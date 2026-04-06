"""날짜 파싱 및 결정론적 날짜 필터링 로직 테스트.

RSS 기반 국제 기사 수집 시 발행일을 코드에서 직접 검증하여
7일 이전 기사가 포함되지 않는지 확인하는 유닛 테스트.
"""
import calendar
import os
import sys
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app


# ── 헬퍼 ─────────────────────────────────────────────────


def _utc_struct(year: int, month: int, day: int, hour: int = 0) -> time.struct_time:
    """UTC time.struct_time 생성 헬퍼 (feedparser published_parsed 형식)."""
    return time.struct_time((year, month, day, hour, 0, 0, 0, 0, 0))


def _make_entry(
    title: str,
    pub_struct,
    url: str = "http://example.com/article",
    summary: str = "Article summary text.",
    source_title: str = "",
) -> MagicMock:
    """feedparser RSS 엔트리 모의 객체 생성."""
    entry = MagicMock()
    entry.get.side_effect = lambda key, default=None: {
        "published_parsed": pub_struct,
        "updated_parsed": None,
        "title": title,
        "link": url,
        "source": {"title": source_title} if source_title else {},
        "summary": summary,
    }.get(key, default)
    return entry


# ── _rss_entry_date 테스트 ────────────────────────────────


def test_rss_entry_date_returns_utc_datetime():
    """`published_parsed` 필드에서 UTC timezone-aware datetime을 반환한다."""
    entry = _make_entry("Test", _utc_struct(2026, 4, 3, 10))
    result = app._rss_entry_date(entry)

    assert result is not None
    assert result.year == 2026
    assert result.month == 4
    assert result.day == 3
    assert result.tzinfo == timezone.utc


def test_rss_entry_date_returns_none_when_no_date():
    """`published_parsed`와 `updated_parsed`가 모두 없으면 None을 반환한다."""
    entry = MagicMock()
    entry.get.return_value = None

    assert app._rss_entry_date(entry) is None


def test_rss_entry_date_falls_back_to_updated_parsed():
    """`published_parsed`가 None이면 `updated_parsed`로 폴백한다."""
    entry = MagicMock()
    entry.get.side_effect = lambda key, default=None: {
        "published_parsed": None,
        "updated_parsed": _utc_struct(2026, 4, 1, 8),
    }.get(key, default)

    result = app._rss_entry_date(entry)
    assert result is not None
    assert result.day == 1
    assert result.month == 4


def test_rss_entry_date_handles_corrupt_struct():
    """파싱할 수 없는 struct_time은 None을 반환한다 (예외 전파 없음)."""
    entry = MagicMock()
    entry.get.side_effect = lambda key, default=None: {
        "published_parsed": "not-a-struct",
        "updated_parsed": None,
    }.get(key, default)

    # 예외가 발생하지 않고 None을 반환해야 함
    result = app._rss_entry_date(entry)
    assert result is None


# ── _extract_rss_source 테스트 ────────────────────────────


def test_extract_rss_source_from_source_dict():
    """`source.title` dict 필드에서 출처명을 추출한다."""
    entry = _make_entry("Title - Reuters", _utc_struct(2026, 4, 2), source_title="Reuters")
    assert app._extract_rss_source(entry) == "Reuters"


def test_extract_rss_source_fallback_to_title_suffix():
    """`source` 필드가 비어 있으면 기사 제목의 ' - 출처명' 패턴에서 추출한다."""
    entry = _make_entry("EV sales hit record - Bloomberg", _utc_struct(2026, 4, 2))
    assert app._extract_rss_source(entry) == "Bloomberg"


def test_extract_rss_source_returns_empty_when_unavailable():
    """출처를 추출할 수 없으면 빈 문자열을 반환한다."""
    entry = _make_entry("EV Article With No Source", _utc_struct(2026, 4, 2))
    assert app._extract_rss_source(entry) == ""


# ── collect_rss_articles 필터링 테스트 ───────────────────


@pytest.fixture
def cutoff_dt() -> datetime:
    """테스트용 cutoff: 2026-03-30 UTC (오늘 2026-04-06 기준 7일 이전)."""
    return datetime(2026, 3, 30, tzinfo=timezone.utc)


def _mock_feed(*entries):
    mock = MagicMock()
    mock.entries = list(entries)
    return mock


def test_collect_rss_filters_out_old_articles(cutoff_dt):
    """cutoff 이전 기사(2026-02-01)는 결과에서 제외된다."""
    old = _make_entry("Old Article - Reuters", _utc_struct(2026, 2, 1), url="http://ex.com/old")
    new = _make_entry("New Article - AP",      _utc_struct(2026, 4, 2), url="http://ex.com/new")

    with patch("feedparser.parse", return_value=_mock_feed(old, new)), \
         patch("app._FEEDPARSER_AVAILABLE", True):
        result = app.collect_rss_articles(["electric vehicle"], cutoff_dt)

    assert len(result) == 1
    assert result[0]["published_date"] == "2026-04-02"


def test_collect_rss_excludes_no_date_articles(cutoff_dt):
    """날짜가 없는 기사는 안전하게 제외된다."""
    no_date = _make_entry("No Date Article", None, url="http://ex.com/nodate")

    with patch("feedparser.parse", return_value=_mock_feed(no_date)), \
         patch("app._FEEDPARSER_AVAILABLE", True):
        result = app.collect_rss_articles(["electric vehicle"], cutoff_dt)

    assert result == []


def test_collect_rss_includes_boundary_date(cutoff_dt):
    """정확히 cutoff 날짜(2026-03-30)에 발행된 기사는 포함된다."""
    boundary = _make_entry("Boundary Article - AP", _utc_struct(2026, 3, 30),
                           url="http://ex.com/boundary")

    with patch("feedparser.parse", return_value=_mock_feed(boundary)), \
         patch("app._FEEDPARSER_AVAILABLE", True):
        result = app.collect_rss_articles(["electric vehicle"], cutoff_dt)

    assert len(result) == 1
    assert result[0]["published_date"] == "2026-03-30"


def test_collect_rss_deduplicates_same_url(cutoff_dt):
    """같은 URL의 기사는 한 번만 포함된다."""
    e1 = _make_entry("Article A", _utc_struct(2026, 4, 1), url="http://ex.com/same")
    e2 = _make_entry("Article B", _utc_struct(2026, 4, 2), url="http://ex.com/same")

    with patch("feedparser.parse", return_value=_mock_feed(e1, e2)), \
         patch("app._FEEDPARSER_AVAILABLE", True):
        result = app.collect_rss_articles(["electric vehicle"], cutoff_dt)

    assert len(result) == 1


def test_collect_rss_respects_max_per_query(cutoff_dt):
    """max_per_query 제한이 지켜진다."""
    entries = [
        _make_entry(f"Article {i}", _utc_struct(2026, 4, 1), url=f"http://ex.com/{i}")
        for i in range(20)
    ]

    with patch("feedparser.parse", return_value=_mock_feed(*entries)), \
         patch("app._FEEDPARSER_AVAILABLE", True):
        result = app.collect_rss_articles(["electric vehicle"], cutoff_dt, max_per_query=5)

    assert len(result) == 5


def test_collect_rss_returns_empty_when_feedparser_unavailable(cutoff_dt):
    """feedparser가 설치되지 않은 환경에서는 빈 목록을 반환한다."""
    with patch("app._FEEDPARSER_AVAILABLE", False):
        result = app.collect_rss_articles(["electric vehicle"], cutoff_dt)

    assert result == []


def test_collect_rss_handles_network_error_gracefully(cutoff_dt):
    """개별 쿼리에서 네트워크 오류가 발생해도 나머지 결과를 반환한다."""
    good_entry = _make_entry("Good Article", _utc_struct(2026, 4, 2),
                             url="http://ex.com/good")
    good_feed = _mock_feed(good_entry)

    call_count = 0

    def fake_parse(url):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("simulated network error")
        return good_feed

    with patch("feedparser.parse", side_effect=fake_parse), \
         patch("app._FEEDPARSER_AVAILABLE", True):
        result = app.collect_rss_articles(
            ["query1", "query2"], cutoff_dt
        )

    # 첫 번째 쿼리 실패해도 두 번째 쿼리 결과는 포함
    assert len(result) == 1
    assert result[0]["published_date"] == "2026-04-02"


def test_collect_rss_article_fields(cutoff_dt):
    """반환된 기사 dict에 필요한 모든 필드가 포함된다."""
    entry = _make_entry(
        "Tesla EV Sales - Reuters",
        _utc_struct(2026, 4, 3),
        url="http://ex.com/tesla",
        summary="Tesla reported record EV sales.",
        source_title="Reuters",
    )

    with patch("feedparser.parse", return_value=_mock_feed(entry)), \
         patch("app._FEEDPARSER_AVAILABLE", True):
        result = app.collect_rss_articles(["electric vehicle"], cutoff_dt)

    assert len(result) == 1
    art = result[0]
    assert art["title"] == "Tesla EV Sales - Reuters"
    assert art["url"] == "http://ex.com/tesla"
    assert art["source"] == "Reuters"
    assert art["published_date"] == "2026-04-03"
    assert art["summary"] == "Tesla reported record EV sales."


# ── timezone 경계값 테스트 ─────────────────────────────────


def test_rss_entry_date_utc_conversion_preserves_timestamp():
    """UTC timestamp가 올바르게 변환되는지 확인 (시차 없음)."""
    # 2026-03-30 23:59:59 UTC — cutoff(2026-03-30 00:00 UTC) 이후이므로 포함돼야 함
    struct = _utc_struct(2026, 3, 30, 23)
    entry = _make_entry("Late Night Article", struct, url="http://ex.com/late")
    cutoff = datetime(2026, 3, 30, tzinfo=timezone.utc)

    with patch("feedparser.parse", return_value=_mock_feed(entry)), \
         patch("app._FEEDPARSER_AVAILABLE", True):
        result = app.collect_rss_articles(["test"], cutoff)

    assert len(result) == 1


def test_article_just_before_cutoff_excluded():
    """cutoff 직전(2026-03-29 23:59 UTC)에 발행된 기사는 제외된다."""
    struct = _utc_struct(2026, 3, 29, 23)
    entry = _make_entry("Day Before Cutoff", struct, url="http://ex.com/daybefore")
    cutoff = datetime(2026, 3, 30, tzinfo=timezone.utc)

    with patch("feedparser.parse", return_value=_mock_feed(entry)), \
         patch("app._FEEDPARSER_AVAILABLE", True):
        result = app.collect_rss_articles(["test"], cutoff)

    assert result == []
