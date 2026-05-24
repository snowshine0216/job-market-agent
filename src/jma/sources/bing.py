"""BingAggregatorSource — SerpAPI-backed Bing search across configured job boards.

Phase 2: snippet-only mapping (no detail-fetch). See docs/2026-05-24-phase-2-bing-view/
items/001-spec.md §§3.1–3.6 and docs/adr/0005-bing-aggregator-source-and-snippet-data-quality.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import (
    Experience,
    Job,
    Location,
    Salary,
    SourceResult,
    SourceStatus,
    WorkMode,
)
from jma.domain.normalize import (
    normalize_for_match,
    parse_experience,
    parse_salary,
)
from jma.sources.base import SourceConfig
from jma.sources.http import AsyncHttpClient
from jma.storage import blobs
from jma.storage.cache import CacheHit

_log = logging.getLogger(__name__)

_SleepFn = Callable[[float], Awaitable[None]]
_OnFetchFn = Callable[[str, int, "str | None"], Awaitable[None]]
_CacheGetFn = Callable[[str], Awaitable["CacheHit | None"]]

# Heuristic-only company extraction. Per-site snippet regexes are forbidden
# (spec §2 row 8). The only per-host knob is `site_names` from bing.yaml,
# used to recognise the board's own name in 2-part titles like
# "AI Agent | BOSS直聘" so we drop it rather than mis-extract it as a company.
_DELIM_SPLIT = re.compile(r"\s*[|\-_]\s*")


def _heuristic_company_from_title(title: str, site_name: str | None) -> str | None:
    """Return the heuristic company name or None.

    - 3-part title (`role DELIM company DELIM site_tail`): middle segment wins.
    - 2-part title (`role DELIM segment_2`):
        - if site_name is set AND segment_2 == site_name → None
        - else → segment_2 as company.
    - 1-part title → None.
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


def _matched_target_host(link: str, target_sites: tuple[str, ...]) -> str | None:
    """Return the target_sites entry that matches `link`'s netloc, or None.

    The match is suffix-aware: `www.zhipin.com`, `m.zhipin.com`, `app.zhipin.com`
    all collapse to `zhipin.com`. Bare `zhipin.com` matches itself.
    """
    try:
        host = urlparse(link).hostname or ""
    except ValueError:
        return None
    host = host.lower()
    for t in target_sites:
        if host == t or host.endswith("." + t):
            return t
    return None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _result_to_job(
    *,
    result: dict,
    cfg: SourceConfig,
    blob_ref: str,
    fetched_at: datetime,
) -> Job | None:
    """Map one SerpAPI organic_results entry to a Job. None when off-target."""
    link = result.get("link") or ""
    host = _matched_target_host(link, cfg.target_sites)
    if host is None:
        return None
    title_raw = (result.get("title") or "").strip()
    snippet = result.get("snippet") or ""
    source = f"bing:{host}"

    site_name = cfg.site_names.get(host)
    company = _heuristic_company_from_title(title_raw, site_name)

    internal_id: str | None = None
    pattern = cfg.id_patterns.get(host)
    if pattern:
        m = re.search(pattern, link)
        if m:
            internal_id = m.group(1)

    salary = parse_salary(snippet) if snippet else Salary(parsed=False, raw="")
    experience = parse_experience(snippet) if snippet else Experience(raw="")
    posted_at = _parse_iso(result.get("date"))

    # Cleaned title is the raw title (no TesterHome-style salary stripping
    # here; Phase 3 LLM extraction owns cleanup).
    title = title_raw

    return Job(
        id=job_id(source=source, internal_id=internal_id, title=title, company=company, city=None),
        canonical_id=canonical_id(title=title, company=company, city=None),
        source=source,
        source_internal_id=internal_id,
        title=title,
        title_raw=title_raw,
        company=company,
        location=Location(country="CN", city=None, district=None, work_mode=WorkMode.UNKNOWN),
        salary=salary,
        experience=experience,
        posted_at=posted_at,
        fetched_at=fetched_at,
        url=link,
        raw_payload_ref=blob_ref,
        data_quality=0.4,
        description_text=snippet,
    )


def _site_clause(target_sites: tuple[str, ...]) -> str:
    return " OR ".join(f"site:{s}" for s in target_sites)


def _resolve_region_variants(
    region: str, region_aliases: dict[str, list[str]]
) -> tuple[list[str], bool]:
    """Return (variants, was_identity_fallback).

    Empty region → ([], False). Unknown region → ([region], True).
    """
    if region == "":
        return [], False
    variants = region_aliases.get(region)
    if variants:
        return list(variants), False
    return [region], True


def _render_query(
    *, cfg: SourceConfig, keywords: tuple[str, ...], region_variants: list[str]
) -> str:
    """Render cfg.query_template against the (keywords, region, site_clause) trio.

    Empty region_variants omits the entire `({region_variants})` clause.
    """
    kw_clause = " OR ".join(f'"{k}"' for k in keywords if k != "")
    site_clause = _site_clause(cfg.target_sites)
    template = cfg.query_template
    if not region_variants:
        # Remove the "({region_variants})" group entirely (with surrounding
        # whitespace) so the rendered query has no empty parens.
        template = re.sub(r"\s*\(\{region_variants\}\)\s*", " ", template)
        rendered = template.format(keywords=kw_clause, site_clause=site_clause)
    else:
        rv = " OR ".join(region_variants)
        rendered = template.format(keywords=kw_clause, region_variants=rv, site_clause=site_clause)
    # Collapse any double spaces left by removal of the region clause.
    return re.sub(r"\s+", " ", rendered).strip()


def _filter_region(jobs: list[Job], region: str) -> list[Job]:
    """Same semantics as TesterHome's _filter_region: empty region disables;
    otherwise NFKC + substring on Location.city, keeping rows with city=None.
    """
    if region == "":
        return jobs
    needle = normalize_for_match(region)
    kept: list[Job] = []
    for j in jobs:
        city = j.location.city
        if city is None or city == "":
            kept.append(j)
            continue
        if needle in normalize_for_match(city):
            kept.append(j)
    return kept


def _filter_keywords(jobs: list[Job], keywords: tuple[str, ...]) -> list[Job]:
    needles = tuple(normalize_for_match(k) for k in keywords if k != "")
    if not needles:
        return jobs
    kept: list[Job] = []
    for j in jobs:
        hay = normalize_for_match(j.title_raw)
        if any(n in hay for n in needles):
            kept.append(j)
    return kept


class BingAggregatorSource:
    name = "bing"

    def __init__(
        self,
        cfg: SourceConfig,
        http: AsyncHttpClient,
        data_root: str | Path,
        *,
        api_key: str,
        sleep: _SleepFn | None = None,
        on_fetch: _OnFetchFn | None = None,
        cache_get: _CacheGetFn | None = None,
    ) -> None:
        self._cfg = cfg
        self._http = http
        self._root = Path(data_root)
        self._api_key = api_key
        self._sleep: _SleepFn = sleep or asyncio.sleep
        self._on_fetch = on_fetch
        self._cache_get = cache_get

    def _cache_url(self, *, query: str, start: int) -> str:
        """Return the canonical URL used as cache key and blob filename input.

        The api_key param is intentionally excluded so the key is stable across
        key rotations and the secret is never written to url_cache or the blob
        file path on disk.
        """
        import httpx as _httpx

        return str(
            _httpx.URL(
                self._cfg.endpoint,
                params={
                    "engine": self._cfg.engine,
                    "q": query,
                    "start": str(start),
                    "count": str(self._cfg.results_per_query),
                },
            )
        )

    def _request_url(self, *, query: str, start: int) -> str:
        """Return the full URL including api_key, used only for the actual HTTP GET."""
        import httpx as _httpx

        return str(
            _httpx.URL(
                self._cfg.endpoint,
                params={
                    "engine": self._cfg.engine,
                    "q": query,
                    "start": str(start),
                    "count": str(self._cfg.results_per_query),
                    "api_key": self._api_key,
                },
            )
        )

    async def crawl(
        self,
        region: str,
        keywords: tuple[str, ...],
        max_pages: int,
        max_jobs: int,
    ) -> SourceResult:
        region_variants, fallback = _resolve_region_variants(region, self._cfg.region_aliases)
        if fallback:
            _log.info("region %r has no aliases; using identity fallback", region)
        query = _render_query(cfg=self._cfg, keywords=keywords, region_variants=region_variants)

        collected: list[Job] = []
        dropped = 0
        pages_fetched = 0
        now = datetime.now(UTC)

        for page_num in range(1, max_pages + 1):
            start = (page_num - 1) * self._cfg.results_per_query
            cache_url = self._cache_url(query=query, start=start)
            request_url = self._request_url(query=query, start=start)
            pages_fetched = page_num

            # Cache lookup uses the key-less URL so the cache is stable across
            # api_key rotations and the key never reaches url_cache or disk.
            hit = await self._cache_get(cache_url) if self._cache_get else None
            _cache_usable = False
            if hit and hit.status_code == 200 and hit.blob_ref:
                try:
                    body_text = blobs.read(root=self._root, ref=hit.blob_ref)
                    blob_ref = hit.blob_ref
                    _cache_usable = True
                except FileNotFoundError:
                    _log.info(
                        "cache stale (blob missing for %s); refetching",
                        cache_url,
                    )
            if not _cache_usable:
                fetched = await self._http.fetch(request_url)
                if fetched.status_code != 200:
                    # Bing/SerpAPI failure for this page. If we already have rows,
                    # surface a partial; else return ERROR.
                    if collected:
                        return SourceResult(
                            source=self.name,
                            status=SourceStatus.OK,
                            jobs=tuple(collected),
                            reason=(
                                f"partial: stopped at page {page_num} "
                                f"(http {fetched.status_code}); dropped={dropped} off-target"
                            ),
                            pages_fetched=pages_fetched,
                        )
                    return SourceResult(
                        source=self.name,
                        status=SourceStatus.ERROR,
                        jobs=(),
                        reason=f"http {fetched.status_code}",
                        pages_fetched=pages_fetched,
                    )
                body_text = fetched.body
                blob_ref = blobs.write(
                    root=self._root,
                    source=self.name,
                    url=cache_url,
                    body=body_text,
                    suffix=".json.gz",
                )
                if self._on_fetch is not None:
                    await self._on_fetch(cache_url, 200, blob_ref)

            payload = json.loads(body_text)
            organic = payload.get("organic_results", []) or []

            page_jobs: list[Job] = []
            for r in organic:
                j = _result_to_job(result=r, cfg=self._cfg, blob_ref=blob_ref, fetched_at=now)
                if j is None:
                    dropped += 1
                    continue
                page_jobs.append(j)

            page_jobs = _filter_region(page_jobs, region)
            page_jobs = _filter_keywords(page_jobs, keywords)

            remaining = max_jobs - len(collected)
            if remaining < len(page_jobs):
                page_jobs = page_jobs[:remaining]

            collected.extend(page_jobs)

            if len(collected) >= max_jobs:
                return SourceResult(
                    source=self.name,
                    status=SourceStatus.OK,
                    jobs=tuple(collected),
                    reason=f"max_jobs reached; dropped={dropped} off-target",
                    pages_fetched=pages_fetched,
                )

            if page_num < max_pages:
                await self._sleep(self._cfg.rate.delay_ms / 1000.0)

        return SourceResult(
            source=self.name,
            status=SourceStatus.OK,
            jobs=tuple(collected),
            reason=f"max_pages reached; dropped={dropped} off-target",
            pages_fetched=pages_fetched,
        )
