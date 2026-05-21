from jma.domain.models import Experience
from jma.domain.normalize import parse_experience


def test_range_years() -> None:
    e = parse_experience("3-5年经验")
    assert e.min_years == 3 and e.max_years == 5 and e.raw == "3-5年经验"


def test_open_ended_lower_bound() -> None:
    e = parse_experience("5年以上")
    assert e.min_years == 5 and e.max_years is None


def test_fresh_grad() -> None:
    e = parse_experience("应届")
    assert e.min_years == 0 and e.max_years == 0


def test_empty_string() -> None:
    e = parse_experience("")
    assert e == Experience(raw="")


def test_unparseable_keeps_raw() -> None:
    e = parse_experience("经验不限")
    assert e.min_years is None and e.max_years is None
    assert e.raw == "经验不限"
