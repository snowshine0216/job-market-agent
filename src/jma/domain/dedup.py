"""Pure dedup keys (spec §2 row 4 / ADR-0001)."""
from __future__ import annotations

import hashlib

from jma.domain.normalize import _normalize_for_match


def _norm(value: str | None) -> str:
    if value is None:
        return ""
    return _normalize_for_match(value)


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def job_id(
    *,
    source: str,
    internal_id: str | None,
    title: str,
    company: str | None,
    city: str | None,
) -> str:
    """JobObservation id. Source-scoped. Uses internal_id when present, else title|company|city."""
    if internal_id:
        return _sha1(f"{source}:{internal_id}")
    payload = f"{source}:{_norm(title)}|{_norm(company)}|{_norm(city)}"
    return _sha1(payload)


def canonical_id(*, title: str, company: str | None, city: str | None) -> str:
    """Job (cross-source) id. Source-independent."""
    return _sha1(f"{_norm(title)}|{_norm(company)}|{_norm(city)}")
