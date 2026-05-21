from jma.domain.models import Location, WorkMode
from jma.domain.normalize import parse_location


def test_testerhome_city_district_brackets() -> None:
    loc = parse_location("【杭州·余杭】AI Agent Engineer")
    assert loc.city == "Hangzhou"
    assert loc.district == "余杭"
    assert loc.country == "CN"


def test_testerhome_city_only_brackets() -> None:
    loc = parse_location("【北京】Senior Backend")
    assert loc.city == "Beijing"
    assert loc.district is None
    assert loc.country == "CN"


def test_remote_chinese() -> None:
    loc = parse_location("【远程】Test Engineer")
    assert loc.work_mode is WorkMode.REMOTE


def test_remote_english() -> None:
    loc = parse_location("Remote · Test Engineer")
    assert loc.work_mode is WorkMode.REMOTE


def test_empty_input_returns_unknown_location() -> None:
    loc = parse_location("")
    assert loc == Location()


def test_no_brackets_no_city() -> None:
    loc = parse_location("Senior Backend at FooCorp")
    assert loc.city is None and loc.district is None
