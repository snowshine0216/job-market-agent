"""BingAggregatorSource — SerpAPI-backed Bing search across configured job boards.

Phase 2: snippet-only mapping (no detail-fetch). See docs/2026-05-24-phase-2-bing-view/
items/001-spec.md §§3.1–3.6 and docs/adr/0005-bing-aggregator-source-and-snippet-data-quality.md.
"""

from __future__ import annotations

import re

# Heuristic-only company extraction. Per-site snippet regexes are forbidden
# (spec §2 row 8). The only per-host knob is `site_names` from bing.yaml,
# used to recognise the board's own name in 2-part titles like
# "AI Agent | BOSS直聘" so we drop it rather than mis-extract it as a company.
_DELIM_SPLIT = re.compile(r"\s*[|\-_]\s*")


def _heuristic_company_from_title(title: str, site_name: str | None) -> str | None:
    """Return the heuristic company name or None.

    - 3-part title (`role DELIM company DELIM site_tail`): the middle segment wins.
    - 2-part title (`role DELIM segment_2`):
        - if site_name is set AND segment_2 == site_name → return None
        - else → return segment_2 as the company.
    - 1-part title (no delimiter) → None.
    """
    parts = [p.strip() for p in _DELIM_SPLIT.split(title.strip()) if p.strip()]
    if len(parts) >= 3:
        return parts[1]
    if len(parts) == 2:
        segment_2 = parts[1]
        if site_name is not None and segment_2 == site_name:
            return None
        return segment_2
    return None
