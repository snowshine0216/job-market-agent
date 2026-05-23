"""TesterHomeSource — listing-page crawl (spec §7.3)."""
from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

from selectolax.parser import HTMLParser

from jma.domain.blockage import classify
from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import (
    Job,
    SourceResult,
    SourceStatus,
)
from jma.domain.normalize import (
    normalize_for_match,
    parse_experience,
    parse_location,
    parse_salary,
)
from jma.sources.base import SourceConfig
from jma.sources.http import AsyncHttpClient
from jma.storage import blobs
from jma.storage.cache import CacheHit

# Salary tokens we strip out of `title_raw` to derive `title`.
_RE_SALARY_TOKENS = re.compile(
    r"(\d+\s*[Kk]?\s*[-–]\s*\d+\s*[Kk](?:\s*·\s*\d+\s*薪)?"
    r"|年薪\s*\d+\s*[-–]\s*\d+\s*万"
    r"|\$\s*\d+\s*K\s*[-–]\s*\$?\s*\d+\s*K"
    r"|日薪\s*\d+(?:\s*[-–]\s*\d+)?"
    r"|时薪\s*\d+(?:\s*[-–]\s*\d+)?)"
)
_RE_TOPIC_ID = re.compile(r"/topics/(\d+)")


_SleepFn = Callable[[float], Awaitable[None]]
_OnFetchFn = Callable[[str, int, "str | None"], Awaitable[None]]
_CacheGetFn = Callable[[str], Awaitable["CacheHit | None"]]


class TesterHomeSource:
    name = "testerhome"

    def __init__(
        self,
        cfg: SourceConfig,
        http: AsyncHttpClient,
        data_root: str | Path,
        sleep: _SleepFn | None = None,
        on_fetch: _OnFetchFn | None = None,
        cache_get: _CacheGetFn | None = None,
    ) -> None:
        self._cfg = cfg
        self._http = http
        self._root = Path(data_root)
        self._sleep: _SleepFn = sleep or asyncio.sleep
        self._on_fetch = on_fetch
        self._cache_get = cache_get

    async def crawl(
        self,
        region: str,
        keywords: tuple[str, ...],
        max_pages: int,
        max_jobs: int,
    ) -> SourceResult:
        collected: list[Job] = []
        pages_fetched = 0
        for n in range(1, max_pages + 1):
            url = self._cfg.listing.url_template.format(
                base_url=self._cfg.base_url, page=n
            )
            pages_fetched = n

            # L1: try cache first when a cache_get callback is wired in.
            hit = await self._cache_get(url) if self._cache_get else None
            if hit and hit.status_code == 200 and hit.blob_ref:
                body_text = blobs.read(root=self._root, ref=hit.blob_ref)
                status_code: int = 200
                headers: dict = {}
                blob_ref: str | None = hit.blob_ref
            else:
                fetched = await self._http.fetch(url)
                status_code = fetched.status_code
                headers = fetched.headers
                body_text = fetched.body
                # L4: only write blob when the fetch was successful.
                if status_code == 200:
                    blob_ref = blobs.write(
                        root=self._root, source=self.name, url=url, body=body_text,
                    )
                else:
                    blob_ref = None
                # L3: pass blob_ref (may be None for non-200); on_fetch handles source tagging.
                if self._on_fetch is not None:
                    await self._on_fetch(url, status_code, blob_ref)

            block = classify(
                status_code=status_code,
                headers=headers,
                body_text=body_text,
                cfg=self._cfg,
            )
            if block.kind is not SourceStatus.OK:
                if collected:
                    return SourceResult(
                        source=self.name,
                        status=SourceStatus.OK,
                        jobs=tuple(collected),
                        reason=f"partial: stopped at page {n} ({block.kind.value}: {block.reason})",
                        pages_fetched=pages_fetched,
                    )
                return SourceResult(
                    source=self.name,
                    status=block.kind,
                    jobs=(),
                    reason=block.reason,
                    pages_fetched=pages_fetched,
                )

            items = _parse_listing(body_text, self._cfg)
            if not items:
                if collected:
                    return SourceResult(
                        source=self.name,
                        status=SourceStatus.OK,
                        jobs=tuple(collected),
                        reason=f"end of listing at page {n}",
                        pages_fetched=pages_fetched,
                    )
                return SourceResult(
                    source=self.name,
                    status=SourceStatus.EMPTY,
                    jobs=(),
                    reason=f"0 items at {self._cfg.known_good_list_selector!r} on page {n}",
                    pages_fetched=pages_fetched,
                )

            # Invariant: items only exist when status==200 → blob_ref is always a str here.
            assert blob_ref is not None
            page_jobs = [
                _item_to_job(item, cfg=self._cfg, source_name=self.name,
                             blob_ref=blob_ref)
                for item in items
            ]
            page_jobs = _filter_region(page_jobs, region)
            page_jobs = _filter_keywords(page_jobs, keywords)
            collected.extend(page_jobs)

            if len(collected) >= max_jobs:
                collected = collected[:max_jobs]
                return SourceResult(
                    source=self.name,
                    status=SourceStatus.OK,
                    jobs=tuple(collected),
                    reason="max_jobs reached",
                    pages_fetched=pages_fetched,
                )

            if n == max_pages:
                return SourceResult(
                    source=self.name,
                    status=SourceStatus.OK,
                    jobs=tuple(collected),
                    reason="max_pages reached",
                    pages_fetched=pages_fetched,
                )

            await self._sleep(self._cfg.rate.delay_ms / 1000.0)

        # Unreachable in practice; defensive default.
        return SourceResult(
            source=self.name, status=SourceStatus.OK, jobs=tuple(collected),
            pages_fetched=pages_fetched,
        )


# -- pure helpers --------------------------------------------------------


def _parse_listing(body: str, cfg: SourceConfig) -> list[dict]:
    tree = HTMLParser(body)
    selector = cfg.listing.list_item_selector
    # Split once outside the loop; posted_at_attr is e.g. ".time@title".
    posted_at_selector, _, posted_at_attr_name = cfg.listing.posted_at_attr.partition("@")
    items: list[dict] = []
    for node in tree.css(selector):
        anchor = node.css_first(cfg.listing.title_selector)
        if anchor is None:
            continue
        href = anchor.attributes.get(cfg.listing.href_attr) or ""
        title_text = (anchor.text() or "").strip()
        posted_at = ""
        time_node = node.css_first(posted_at_selector)
        if time_node is not None:
            posted_at = time_node.attributes.get(posted_at_attr_name) or ""
        items.append({"title": title_text, "href": href, "posted_at_attr": posted_at})
    return items


def _strip_salary_tokens(title_raw: str) -> str:
    out = _RE_SALARY_TOKENS.sub("", title_raw)
    return re.sub(r"\s+", " ", out).strip()


def _extract_salary_token(title_raw: str) -> str:
    m = _RE_SALARY_TOKENS.search(title_raw)
    return m.group(0) if m else ""


def _item_to_job(item: dict, *, cfg: SourceConfig, source_name: str, blob_ref: str) -> Job:
    title_raw = item["title"]
    href = item["href"]
    posted_at_attr = item["posted_at_attr"]

    title = _strip_salary_tokens(title_raw)
    salary = parse_salary(_extract_salary_token(title_raw))
    location = parse_location(title_raw)
    experience = parse_experience(title_raw)

    m = _RE_TOPIC_ID.search(href)
    internal_id = m.group(1) if m else None

    url = urljoin(cfg.base_url, href)

    posted_at = None
    if posted_at_attr:
        try:
            posted_at = datetime.fromisoformat(posted_at_attr)
        except ValueError:
            posted_at = None

    company = None  # listing page doesn't expose company

    return Job(
        id=job_id(source=source_name, internal_id=internal_id,
                  title=title, company=company, city=location.city),
        canonical_id=canonical_id(title=title, company=company, city=location.city),
        source=source_name,
        source_internal_id=internal_id,
        title=title,
        title_raw=title_raw,
        company=company,
        location=location,
        salary=salary,
        experience=experience,
        posted_at=posted_at,
        fetched_at=datetime.now(UTC),
        url=url,
        raw_payload_ref=blob_ref,
    )


def _filter_region(jobs: list[Job], region: str) -> list[Job]:
    if region == "":
        return jobs
    needle = normalize_for_match(region)
    kept: list[Job] = []
    for j in jobs:
        city = j.location.city
        if city is None or city == "":
            kept.append(j)  # keep observations with unparseable city
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
