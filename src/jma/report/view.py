"""Pure context builder for the jma view template.

Effect-free: takes a Run row and a list of Job rows (already ordered by the
DB query), returns a dict the Jinja2 template renders. The `data_root_abs`
key is the resolved data-root path the template uses to produce absolute
`file://` URIs for the blob column — so the rendered HTML works regardless
of where --out writes it (spec §3.5 Pure/effect split).
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from jma.domain.models import Job, Run

# URL schemes that are safe to render as clickable <a> links.
_SAFE_SCHEMES = frozenset({"http", "https", "mailto"})


def _sanitize_url(raw_url: str) -> tuple[str, bool]:
    """Return (safe_url, url_unsafe).

    If raw_url's scheme is not in _SAFE_SCHEMES (or parsing fails), returns
    ('#', True). Otherwise returns the original URL and False.
    """
    try:
        scheme = urlparse(raw_url).scheme.lower()
    except Exception:
        return "#", True
    if scheme not in _SAFE_SCHEMES:
        return "#", True
    return raw_url, False


def _row_dict(job: Job) -> dict:
    safe_url, url_unsafe = _sanitize_url(job.url)
    return {
        "title": job.title,
        "title_raw": job.title_raw,
        "company": job.company,
        "city": job.location.city,
        "salary_raw": job.salary.raw,
        "posted_at": job.posted_at.isoformat() if job.posted_at else None,
        "source": job.source,
        "url": safe_url,
        "url_unsafe": url_unsafe,
        "raw_payload_ref": job.raw_payload_ref,
        "dq": job.data_quality,
    }


def build_view_context(run: Run, jobs: list[Job], data_root_abs: Path) -> dict:
    """Build the Jinja2 template context.

    `data_root_abs` should be the absolute resolved data root (CLI passes
    `Path(data_root).resolve()`); the template renders blob `<a href>`s as
    `file://{data_root_abs}/{raw_payload_ref}` so the output is portable
    across `--out` locations on the local machine.
    """
    return {
        "run": {
            "id": run.id,
            "region": run.region,
            "keywords": run.keywords,
            "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        },
        "count": len(jobs),
        "rows": [_row_dict(j) for j in jobs],
        "data_root_abs": str(data_root_abs),
    }
