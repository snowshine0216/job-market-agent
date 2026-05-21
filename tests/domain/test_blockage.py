from dataclasses import dataclass

from jma.domain.blockage import classify, snippet_around
from jma.domain.models import BlockStatus, SourceStatus


@dataclass(frozen=True)
class _Cfg:
    content_block_markers: tuple[str, ...] = ()


def test_429_rate_limited_with_retry_after() -> None:
    b = classify(429, {"retry-after": "30"}, "anything", _Cfg())
    assert b.kind is SourceStatus.RATE_LIMITED
    assert "Retry-After=30" in b.reason


def test_429_without_retry_after() -> None:
    b = classify(429, {}, "anything", _Cfg())
    assert b.kind is SourceStatus.RATE_LIMITED
    assert "Retry-After=?" in b.reason


def test_403_blocked() -> None:
    b = classify(403, {}, "x", _Cfg())
    assert b.kind is SourceStatus.BLOCKED
    assert b.reason == "HTTP 403"


def test_5xx_error() -> None:
    b = classify(503, {}, "x", _Cfg())
    assert b.kind is SourceStatus.ERROR
    assert b.reason == "HTTP 503"


def test_other_non_200_error() -> None:
    b = classify(302, {}, "x", _Cfg())
    assert b.kind is SourceStatus.ERROR
    assert b.reason == "HTTP 302"


def test_soft_block_marker_match() -> None:
    cfg = _Cfg(content_block_markers=("访问受限",))
    b = classify(200, {}, "前文 访问受限 后文", cfg)
    assert b.kind is SourceStatus.BLOCKED
    assert "soft-block: 访问受限" in b.reason
    assert "访问受限" in b.evidence


def test_empty_body_is_error() -> None:
    b = classify(200, {}, "", _Cfg())
    assert b.kind is SourceStatus.ERROR
    assert b.reason == "empty response body"


def test_ok_when_status_200_and_body_present() -> None:
    b = classify(200, {}, "<html>jobs</html>", _Cfg())
    assert b == BlockStatus(kind=SourceStatus.OK)


def test_snippet_around_collapses_whitespace() -> None:
    text = "abc    \n DEF  marker   tail  \n\n end"
    out = snippet_around(text, "marker", radius=5)
    assert "  " not in out  # all whitespace runs collapsed
    assert "marker" in out


def test_evidence_capped_at_200_chars() -> None:
    long = "x" * 1000 + "MARK" + "y" * 1000
    cfg = _Cfg(content_block_markers=("MARK",))
    b = classify(200, {}, long, cfg)
    assert len(b.evidence) <= 200
