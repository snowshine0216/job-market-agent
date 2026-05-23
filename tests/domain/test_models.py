from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jma.domain.models import (
    BlockStatus,
    Experience,
    Job,
    Location,
    Salary,
    SalaryPeriod,
    Seniority,
    SourceResult,
    SourceStatus,
    WorkMode,
)


def _make_job(**overrides) -> Job:
    defaults = dict(
        id="obs-1",
        canonical_id="canon-1",
        source="testerhome",
        title="AI Agent Engineer",
        title_raw="【杭州】AI Agent Engineer 15-30K·14薪",
        location=Location(country="CN", city="Hangzhou"),
        salary=Salary(raw=""),
        experience=Experience(raw=""),
        fetched_at=datetime(2026, 5, 21, tzinfo=UTC),
        url="https://testerhome.com/topics/123",
        raw_payload_ref="raw/testerhome/20260521/abc.html.gz",
    )
    return Job(**{**defaults, **overrides})


def test_models_are_frozen() -> None:
    loc = Location(country="CN", city="Hangzhou")
    with pytest.raises(ValidationError):
        loc.city = "Shanghai"  # type: ignore[misc]


def test_location_defaults() -> None:
    loc = Location()
    assert loc.country is None
    assert loc.city is None
    assert loc.district is None
    assert loc.work_mode is WorkMode.UNKNOWN


def test_salary_defaults() -> None:
    s = Salary()
    assert s.min is None
    assert s.max is None
    assert s.currency is None
    assert s.period is SalaryPeriod.UNKNOWN
    assert s.months_per_year is None
    assert s.raw == ""
    assert s.parsed is False


def test_salary_disclosure_three_way() -> None:
    parseable = Salary(
        min=15000,
        max=30000,
        currency="CNY",
        period=SalaryPeriod.MONTHLY,
        months_per_year=14,
        raw="15-30K·14薪",
        parsed=True,
    )
    unparseable = Salary(raw="面议")
    absent = Salary()
    assert parseable.disclosure == "parseable"
    assert unparseable.disclosure == "unparseable"
    assert absent.disclosure == "absent"


def test_experience_defaults() -> None:
    e = Experience()
    assert e.min_years is None and e.max_years is None and e.raw == ""


def test_block_status_defaults() -> None:
    b = BlockStatus(kind=SourceStatus.OK)
    assert b.reason == "" and b.evidence == ""


def test_job_round_trip() -> None:
    job = _make_job()
    payload = job.model_dump()
    rebuilt = Job.model_validate(payload)
    assert rebuilt == job


def test_job_phase3_fields_default_empty() -> None:
    job = _make_job()
    assert job.skills_raw == []
    assert job.skills_canonical == []
    assert job.seniority is Seniority.UNKNOWN
    assert job.responsibilities_summary == ""
    assert job.description_text == ""
    assert job.data_quality == 1.0


def test_source_result_defaults_jobs_to_empty_tuple() -> None:
    r = SourceResult(source="testerhome", status=SourceStatus.OK)
    assert r.jobs == ()
    assert r.reason == ""
    assert r.pages_fetched == 0
    assert r.elapsed_ms == 0
