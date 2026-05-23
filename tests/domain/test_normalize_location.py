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


# Four patterns from issue #6 ---------------------------------------------


def test_chinese_paren_city() -> None:
    loc = parse_location("招聘中高级测试工程师（武汉）")
    assert loc.city == "Wuhan"
    assert loc.country == "CN"
    assert loc.district is None


def test_chinese_paren_city_district() -> None:
    loc = parse_location("招聘高级开发（杭州·余杭）")
    assert loc.city == "Hangzhou"
    assert loc.district == "余杭"
    assert loc.country == "CN"


def test_base_prefix_city() -> None:
    loc = parse_location("APP测试工程师热招中！base 北京")
    assert loc.city == "Beijing"
    assert loc.country == "CN"


def test_bare_city_at_start() -> None:
    loc = parse_location("深圳招聘~AI独角兽急招测试")
    assert loc.city == "Shenzhen"
    assert loc.country == "CN"


# Guard tests — must NOT extract a city ----------------------------------


def test_english_paren_does_not_match() -> None:
    # ASCII parens around English content must not trip the paren probe.
    loc = parse_location("Senior Backend Engineer (Remote)")
    assert loc.city is None
    assert loc.district is None
    assert loc.country is None
    # work_mode is REMOTE via the existing English-remote token detection.
    assert loc.work_mode is WorkMode.REMOTE


def test_database_does_not_trigger_base_prefix() -> None:
    # "Database" contains "base" — the base-prefix probe must require a
    # non-letter boundary on the left.
    loc = parse_location("资深 Database 测试工程师")
    assert loc.city is None
    assert loc.district is None


def test_bare_scan_leftmost_city_wins() -> None:
    # Multiple known cities — leftmost in the string wins (not dict order).
    loc = parse_location("深圳/广州招聘 AI 工程师")
    assert loc.city == "Shenzhen"


def test_unknown_native_city_in_brackets_yields_none_district() -> None:
    # 厦门 is a real city but not yet in _CITY_PINYIN. The bracket shape
    # matches, but we must NOT stuff "厦门" into the district field.
    loc = parse_location("【厦门】Senior QA")
    assert loc.city is None
    assert loc.district is None
    assert loc.country == "CN"
