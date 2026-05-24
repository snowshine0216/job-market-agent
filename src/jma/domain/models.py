"""Frozen pydantic models for the v1 domain surface (spec §4)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class WorkMode(StrEnum):
    ONSITE = "onsite"
    REMOTE = "remote"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class Seniority(StrEnum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    LEAD = "lead"
    UNKNOWN = "unknown"


class SalaryPeriod(StrEnum):
    MONTHLY = "monthly"
    ANNUAL = "annual"
    DAILY = "daily"
    HOURLY = "hourly"
    UNKNOWN = "unknown"


class SourceStatus(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"


class UrlStatus(StrEnum):
    LIVE = "live"
    GONE = "gone"
    UNKNOWN = "unknown"


class Location(BaseModel):
    model_config = ConfigDict(frozen=True)

    country: str | None = None
    city: str | None = None
    district: str | None = None
    work_mode: WorkMode = WorkMode.UNKNOWN


class Salary(BaseModel):
    model_config = ConfigDict(frozen=True)

    min: int | None = None
    max: int | None = None
    currency: str | None = None
    period: SalaryPeriod = SalaryPeriod.UNKNOWN
    months_per_year: int | None = None
    raw: str = ""
    parsed: bool = False

    @property
    def disclosure(self) -> Literal["parseable", "unparseable", "absent"]:
        if self.parsed:
            return "parseable"
        return "absent" if self.raw == "" else "unparseable"


class Experience(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_years: int | None = None
    max_years: int | None = None
    raw: str = ""


class BlockStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: SourceStatus
    reason: str = ""
    evidence: str = ""


class Job(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    canonical_id: str
    source: str
    source_internal_id: str | None = None
    title: str
    title_raw: str
    company: str | None = None
    location: Location
    salary: Salary
    experience: Experience
    skills_raw: list[str] = []
    skills_canonical: list[str] = []
    seniority: Seniority = Seniority.UNKNOWN
    responsibilities_summary: str = ""
    description_text: str = ""
    posted_at: datetime | None = None
    fetched_at: datetime
    url: str
    raw_payload_ref: str
    data_quality: float = 1.0
    url_status: UrlStatus = UrlStatus.UNKNOWN
    url_last_checked_at: datetime | None = None


class Run(BaseModel):
    """A single execution of `jma crawl`. See CONTEXT.md [[Run]]."""

    model_config = ConfigDict(frozen=True)

    id: str
    region: str
    keywords: tuple[str, ...]
    started_at: datetime
    finished_at: datetime | None = None


class SourceResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    status: SourceStatus
    jobs: tuple[Job, ...] = ()
    reason: str = ""
    pages_fetched: int = 0
    elapsed_ms: int = 0


class MarketReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    region: str
    keywords: tuple[str, ...]
    generated_at: datetime
    stats_json: dict[str, object] = {}
    narrative_md: str = ""


class FitReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    region: str
    keywords: tuple[str, ...]
    generated_at: datetime
    profile_id: str = ""
    top_jobs_md: str = ""
    synthesis_md: str = ""
