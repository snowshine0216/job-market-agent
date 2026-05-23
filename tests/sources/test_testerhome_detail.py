from pathlib import Path

from jma.sources.base import load_source_config
from jma.sources.testerhome import _parse_detail

REPO = Path(__file__).resolve().parents[2]
_CFG_PATH = REPO / "config/sources/testerhome.yaml"
_FIX_BASIC = REPO / "tests/fixtures/sources/testerhome/detail_basic.html"
_FIX_MIN = REPO / "tests/fixtures/sources/testerhome/detail_minified.html"


def _cfg_with_detail_enabled():
    cfg = load_source_config(_CFG_PATH)
    return cfg.model_copy(update={"detail": cfg.detail.model_copy(update={"enabled": True})})


def test_parse_detail_extracts_company_and_salary_from_basic_fixture() -> None:
    body = _FIX_BASIC.read_text(encoding="utf-8")
    cfg = _cfg_with_detail_enabled()
    out = _parse_detail(body, cfg)
    assert out["company"] == "上海冰鲸科技有限公司"
    assert out["salary_raw"] == "30k-50k·14薪"


def test_parse_detail_extracts_correctly_from_minified_fixture() -> None:
    """Renderer minification (no whitespace between </p> and <p>) must not
    cause label scan to span paragraphs. Child-element iteration is the
    invariant under test here."""
    body = _FIX_MIN.read_text(encoding="utf-8")
    cfg = _cfg_with_detail_enabled()
    out = _parse_detail(body, cfg)
    assert out["company"] == "上海冰鲸科技有限公司"
    assert out["salary_raw"] == "30k-50k·14薪"


def test_parse_detail_returns_empty_strings_when_no_match() -> None:
    body = "<html><body><div class='markdown-body'><p>nothing useful</p></div></body></html>"
    cfg = _cfg_with_detail_enabled()
    out = _parse_detail(body, cfg)
    assert out == {"company": "", "salary_raw": ""}


def test_parse_detail_no_op_when_disabled() -> None:
    body = _FIX_BASIC.read_text(encoding="utf-8")
    cfg = load_source_config(_CFG_PATH)  # detail.enabled = False from YAML
    out = _parse_detail(body, cfg)
    assert out == {"company": "", "salary_raw": ""}


from datetime import UTC, datetime  # noqa: E402

from jma.domain.dedup import canonical_id, job_id  # noqa: E402
from jma.domain.models import Experience, Job, Location, Salary, WorkMode  # noqa: E402
from jma.domain.normalize import parse_salary  # noqa: E402
from jma.sources.testerhome import _enrich_from_detail  # noqa: E402


def _make_listing_job() -> Job:
    return Job(
        id=job_id(
            source="testerhome",
            internal_id="42",
            title="测试开发",
            company=None,
            city="Shanghai",
        ),
        canonical_id=canonical_id(title="测试开发", company=None, city="Shanghai"),
        source="testerhome",
        source_internal_id="42",
        title="测试开发",
        title_raw="【上海】测试开发",
        company=None,
        location=Location(country="CN", city="Shanghai", work_mode=WorkMode.UNKNOWN),
        salary=Salary(raw=""),
        experience=Experience(raw=""),
        fetched_at=datetime.now(UTC),
        url="https://testerhome.com/topics/42",
        raw_payload_ref="testerhome/abc.html.gz",
    )


def test_enrich_fills_company_and_salary_and_recomputes_canonical_id_only() -> None:
    job = _make_listing_job()
    detail = {"company": "上海冰鲸科技有限公司", "salary_raw": "30k-50k·14薪"}
    enriched = _enrich_from_detail(job, detail, source_name="testerhome")

    assert enriched.company == "上海冰鲸科技有限公司"
    assert enriched.salary == parse_salary("30k-50k·14薪")
    # canonical_id changes (per ADR-0003, latest-wins).
    assert enriched.canonical_id == canonical_id(
        title="测试开发", company="上海冰鲸科技有限公司", city="Shanghai"
    )
    # id is UNCHANGED — job_id is sha1("testerhome:42") regardless of company.
    assert enriched.id == job.id


def test_enrich_no_op_when_detail_empty() -> None:
    job = _make_listing_job()
    enriched = _enrich_from_detail(
        job, {"company": "", "salary_raw": ""}, source_name="testerhome"
    )
    assert enriched.company is None
    assert enriched.salary == job.salary
    assert enriched.id == job.id
    assert enriched.canonical_id == job.canonical_id


def test_enrich_preserves_listing_salary_when_detail_salary_blank() -> None:
    job = _make_listing_job().model_copy(update={"salary": parse_salary("20k-30k")})
    enriched = _enrich_from_detail(
        job, {"company": "X公司", "salary_raw": ""}, source_name="testerhome"
    )
    assert enriched.salary == parse_salary("20k-30k")  # not clobbered
    assert enriched.company == "X公司"


def test_enrich_does_not_degrade_parseable_listing_salary_to_unparseable() -> None:
    """Detail wins only when it parses cleanly. If detail salary is e.g.
    '面议' (unparseable) and listing salary is parseable, listing wins."""
    listing_salary = parse_salary("30k-50k")
    assert listing_salary.parsed is True
    job = _make_listing_job().model_copy(update={"salary": listing_salary})

    enriched = _enrich_from_detail(
        job,
        {"company": "Y公司", "salary_raw": "面议"},
        source_name="testerhome",
    )
    assert enriched.salary == listing_salary  # listing preserved
    assert enriched.company == "Y公司"


def test_enrich_uses_detail_salary_when_listing_was_unparseable() -> None:
    """Symmetric case: if listing was unparseable (or absent) and detail
    is unparseable too, accept detail (no information loss, and detail
    raw text may be more informative)."""
    job = _make_listing_job()  # salary.raw="" → parsed=False
    enriched = _enrich_from_detail(
        job,
        {"company": "Z公司", "salary_raw": "面议"},
        source_name="testerhome",
    )
    assert enriched.salary == parse_salary("面议")
