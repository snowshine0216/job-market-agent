from datetime import UTC, datetime

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import Experience, Job, Location, Salary, UrlStatus


def _minimal_job() -> Job:
    return Job(
        id=job_id(source="testerhome", internal_id="1", title="t",
                  company=None, city=None),
        canonical_id=canonical_id(title="t", company=None, city=None),
        source="testerhome",
        title="t",
        title_raw="t",
        location=Location(),
        salary=Salary(),
        experience=Experience(),
        fetched_at=datetime.now(UTC),
        url="https://x/",
        raw_payload_ref="x.gz",
    )


def test_job_defaults_url_status_to_unknown_and_no_check_time() -> None:
    j = _minimal_job()
    assert j.url_status is UrlStatus.UNKNOWN
    assert j.url_last_checked_at is None


def test_job_accepts_all_url_status_values() -> None:
    base = _minimal_job()
    now = datetime.now(UTC)
    for status in (UrlStatus.LIVE, UrlStatus.GONE, UrlStatus.UNKNOWN):
        upd = base.model_copy(update={"url_status": status, "url_last_checked_at": now})
        assert upd.url_status is status
        assert upd.url_last_checked_at == now


def test_url_status_serialises_as_string_value() -> None:
    assert UrlStatus.LIVE.value == "live"
    assert UrlStatus.GONE.value == "gone"
    assert UrlStatus.UNKNOWN.value == "unknown"
