from datetime import UTC, datetime

from jma.domain.dedup import canonical_id, job_id
from jma.domain.models import Experience, Job, Location, Salary, UrlStatus
from jma.sources.testerhome import _apply_url_freshness


def _job(**overrides) -> Job:
    base = dict(
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
    base.update(overrides)
    return Job(**base)


def test_200_marks_live_and_does_not_touch_data_quality() -> None:
    now = datetime(2026, 5, 23, tzinfo=UTC)
    out = _apply_url_freshness(_job(), status_code=200, checked_at=now)
    assert out.url_status is UrlStatus.LIVE
    assert out.url_last_checked_at == now
    assert out.data_quality == 1.0


def test_404_marks_gone_and_does_not_touch_data_quality() -> None:
    now = datetime(2026, 5, 23, tzinfo=UTC)
    out = _apply_url_freshness(_job(), status_code=404, checked_at=now)
    assert out.url_status is UrlStatus.GONE
    assert out.url_last_checked_at == now
    assert out.data_quality == 1.0


def test_410_marks_gone() -> None:
    out = _apply_url_freshness(_job(), status_code=410,
                                checked_at=datetime.now(UTC))
    assert out.url_status is UrlStatus.GONE


def test_500_is_transient_preserves_prior_status() -> None:
    prior = _job(url_status=UrlStatus.LIVE,
                 url_last_checked_at=datetime(2026, 5, 1, tzinfo=UTC))
    out = _apply_url_freshness(prior, status_code=500,
                                checked_at=datetime(2026, 5, 23, tzinfo=UTC))
    assert out.url_status is UrlStatus.LIVE
    assert out.url_last_checked_at == datetime(2026, 5, 1, tzinfo=UTC)


def test_429_is_transient_preserves_prior_status() -> None:
    prior = _job(url_status=UrlStatus.LIVE,
                 url_last_checked_at=datetime(2026, 5, 1, tzinfo=UTC))
    out = _apply_url_freshness(prior, status_code=429,
                                checked_at=datetime(2026, 5, 23, tzinfo=UTC))
    assert out.url_status is UrlStatus.LIVE
    assert out.url_last_checked_at == datetime(2026, 5, 1, tzinfo=UTC)


def test_3xx_is_transient_preserves_prior_status() -> None:
    prior = _job(url_status=UrlStatus.GONE,
                 url_last_checked_at=datetime(2026, 5, 1, tzinfo=UTC))
    out = _apply_url_freshness(prior, status_code=302,
                                checked_at=datetime(2026, 5, 23, tzinfo=UTC))
    assert out.url_status is UrlStatus.GONE
    assert out.url_last_checked_at == datetime(2026, 5, 1, tzinfo=UTC)


def test_other_4xx_is_transient_preserves_prior_status() -> None:
    """403 (auth) and 401 are not 'gone' — the resource may exist behind auth."""
    prior = _job(url_status=UrlStatus.LIVE,
                 url_last_checked_at=datetime(2026, 5, 1, tzinfo=UTC))
    out = _apply_url_freshness(prior, status_code=403,
                                checked_at=datetime(2026, 5, 23, tzinfo=UTC))
    assert out.url_status is UrlStatus.LIVE


def test_transient_on_fresh_job_keeps_unknown_defaults() -> None:
    """A 429 on a Job that has never been verified leaves url_status=UNKNOWN
    and url_last_checked_at=None. We don't fake a 'we tried' timestamp."""
    out = _apply_url_freshness(_job(), status_code=429,
                                checked_at=datetime.now(UTC))
    assert out.url_status is UrlStatus.UNKNOWN
    assert out.url_last_checked_at is None


def test_helper_is_idempotent_on_repeat_definitive_outcome() -> None:
    now = datetime(2026, 5, 23, tzinfo=UTC)
    once = _apply_url_freshness(_job(), status_code=404, checked_at=now)
    twice = _apply_url_freshness(once, status_code=404, checked_at=now)
    assert once == twice
