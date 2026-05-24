"""Company extraction heuristic for Bing-aggregator titles (spec §2 row 8)."""

from __future__ import annotations

import pytest

from jma.sources.bing import _heuristic_company_from_title


@pytest.mark.parametrize(
    "title,site_name,expected",
    [
        # 3-part: middle wins regardless of tail.
        ("AI Agent 工程师 - 阿里巴巴 - BOSS直聘", "BOSS直聘", "阿里巴巴"),
        # 2-part, segment_2 ≠ site_name → company.
        ("AI Engineer | NetEase", "BOSS直聘", "NetEase"),
        # 2-part, segment_2 == site_name → drop (locks in the site-name anchor).
        ("AI Agent | 拉勾招聘", "拉勾招聘", None),
        # 1-part: no delimiter, no signal.
        ("AI Agent 后端", "BOSS直聘", None),
        # No site_name available (host without site_names entry) — segment_2 wins.
        ("AI Engineer | NetEase", None, "NetEase"),
        # Underscore delimiter also splits.
        ("AI Engineer_NetEase_BOSS直聘", "BOSS直聘", "NetEase"),
        # Em-dash variant (we only split on [|\-_]; em-dash is not a delim → 1-part).
        ("AI Engineer — NetEase", "BOSS直聘", None),
        # Whitespace around delim is trimmed in segments.
        ("  AI Engineer   |   NetEase  ", "BOSS直聘", "NetEase"),
    ],
)
def test_company_heuristic_cases(title: str, site_name: str | None, expected: str | None) -> None:
    assert _heuristic_company_from_title(title, site_name) == expected
