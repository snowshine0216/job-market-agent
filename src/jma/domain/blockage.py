"""Pure blockage classifier (spec §6). No I/O, no globals, no clock."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Protocol

from jma.domain.models import BlockStatus, SourceStatus

_MAX_EVIDENCE = 200


class _HasMarkers(Protocol):
    content_block_markers: tuple[str, ...]


def snippet_around(text: str, marker: str, radius: int) -> str:
    i = text.find(marker)
    if i == -1:
        return ""
    start = max(0, i - radius)
    end = i + len(marker) + radius
    raw = text[start:end]
    collapsed = re.sub(r"\s+", " ", raw).strip()
    if len(collapsed) > _MAX_EVIDENCE:
        collapsed = collapsed[:_MAX_EVIDENCE]
    return collapsed


def classify(
    status_code: int,
    headers: Mapping[str, str],
    body_text: str,
    cfg: _HasMarkers,
) -> BlockStatus:
    if status_code == 429:
        retry = headers.get("retry-after") or headers.get("Retry-After") or "?"
        return BlockStatus(kind=SourceStatus.RATE_LIMITED,
                           reason=f"HTTP 429; Retry-After={retry}s")
    if status_code in (401, 403):
        return BlockStatus(kind=SourceStatus.BLOCKED, reason=f"HTTP {status_code}")
    if status_code >= 500:
        return BlockStatus(kind=SourceStatus.ERROR, reason=f"HTTP {status_code}")
    if status_code != 200:
        return BlockStatus(kind=SourceStatus.ERROR, reason=f"HTTP {status_code}")

    for marker in cfg.content_block_markers:
        if marker in body_text:
            return BlockStatus(
                kind=SourceStatus.BLOCKED,
                reason=f"soft-block: {marker}",
                evidence=snippet_around(body_text, marker, 120),
            )

    if body_text == "":
        return BlockStatus(kind=SourceStatus.ERROR, reason="empty response body")

    return BlockStatus(kind=SourceStatus.OK)
