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
