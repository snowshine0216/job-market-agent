"""Gzipped raw-HTML blobs at data/raw/{source}/{yyyymmdd}/{sha1(url)[:16]}.html.gz."""

from __future__ import annotations

import gzip
import hashlib
from datetime import UTC, datetime
from pathlib import Path


def _sha1_short(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _ref(source: str, url: str, when: datetime) -> str:
    ymd = when.astimezone(UTC).strftime("%Y%m%d")
    return f"raw/{source}/{ymd}/{_sha1_short(url)}.html.gz"


def write(
    *,
    root: str | Path,
    source: str,
    url: str,
    body: str,
    now: datetime | None = None,
) -> str:
    when = now or datetime.now(UTC)
    ref = _ref(source, url, when)
    full = Path(root) / ref
    full.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(full, "wb") as f:
        f.write(body.encode("utf-8"))
    return ref


def read(*, root: str | Path, ref: str) -> str:
    full = Path(root) / ref
    with gzip.open(full, "rb") as f:
        return f.read().decode("utf-8")
