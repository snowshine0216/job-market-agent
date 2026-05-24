"""Pure context builder for the jma view template.

Effect-free: takes a Run row and a list of Job rows (already ordered by the
DB query), returns a dict the Jinja2 template renders. The `data_root_abs`
key is the resolved data-root path the template uses to produce absolute
`file://` URIs for the blob column — so the rendered HTML works regardless
of where --out writes it (spec §3.5 Pure/effect split).
"""

from __future__ import annotations

from pathlib import Path

from jma.domain.models import Job, Run


def _row_dict(job: Job) -> dict:
    return {
        "title": job.title,
        "title_raw": job.title_raw,
        "company": job.company,
        "city": job.location.city,
        "salary_raw": job.salary.raw,
        "posted_at": job.posted_at.isoformat() if job.posted_at else None,
        "source": job.source,
        "url": job.url,
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
