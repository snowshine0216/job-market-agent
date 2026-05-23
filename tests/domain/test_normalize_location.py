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


def test_unknown_native_city_with_district_in_brackets_yields_none_district() -> None:
    # 厦门·鼓楼: known shape (city·district) but city not in vocabulary.
    # _build_location must NOT pollute district with "鼓楼" or anything
    # else; both city and district stay None.
    loc = parse_location("【厦门·鼓楼】Senior QA")
    assert loc.city is None
    assert loc.district is None
    assert loc.country == "CN"


def test_base_prefix_city_followed_by_cjk() -> None:
    # Greedy regex over-captures "北京工作", but the post-match prefix
    # lookup resolves to "北京". Without the lookup, this returned
    # city=None silently — a regression caught in pre-landing review.
    loc = parse_location("APP测试工程师热招中！base 北京工作")
    assert loc.city == "Beijing"
    assert loc.country == "CN"


def test_base_prefix_unknown_city_followed_by_cjk() -> None:
    # 厦门 is not in _CITY_PINYIN yet. Even with the prefix-lookup, the
    # probe must NOT silently return Beijing or some other city.
    loc = parse_location("base 厦门总部招聘")
    assert loc.city is None
    assert loc.country == "CN"


# Issue #10 — first-known-city wins (paren/base/bracket probes fall through
# when the captured CJK token is not in _CITY_PINYIN). See ADR 0004.


def test_paren_role_descriptor_falls_through_to_base_prefix_beijing() -> None:
    # （高级）matches the paren shape but "高级" is not a city; the base-prefix
    # probe must win.
    loc = parse_location("（高级）测试工程师 base 北京")
    assert loc.city == "Beijing"
    assert loc.country == "CN"


def test_paren_senior_falls_through_to_base_prefix_shanghai() -> None:
    loc = parse_location("（资深）开发 base 上海")
    assert loc.city == "Shanghai"
    assert loc.country == "CN"


def test_paren_intern_falls_through_to_base_prefix_hangzhou() -> None:
    loc = parse_location("（实习）数据分析师 base 杭州")
    assert loc.city == "Hangzhou"
    assert loc.country == "CN"


def test_paren_parttime_falls_through_to_base_prefix_shenzhen() -> None:
    loc = parse_location("（兼职）前端 base 深圳")
    assert loc.city == "Shenzhen"
    assert loc.country == "CN"


def test_paren_parttime_or_intern_falls_through_to_base_prefix_guangzhou() -> None:
    # （兼职/实习）— the slash is inside the parens; the paren probe captures
    # only the leading CJK run via its [一-鿿]{2,4} shape, but "兼职" is not a
    # city. Base-prefix probe must win.
    loc = parse_location("（兼职/实习）后端 base 广州")
    assert loc.city == "Guangzhou"
    assert loc.country == "CN"


def test_bracket_non_city_falls_through_to_base_prefix_chengdu() -> None:
    # 【高级】matches the bracket shape but "高级" is not a city. Base-prefix
    # probe must win.
    loc = parse_location("【高级】QA base 成都")
    assert loc.city == "Chengdu"
    assert loc.country == "CN"


def test_base_prefix_non_city_falls_through_to_bare_scan_beijing() -> None:
    # base 团队: "团队" is not a city. Fall through to bare-scan, which finds
    # 北京 inside 北京站 (substring match is _scan_bare_city's documented
    # behaviour — see test_bare_city_at_start; unchanged by this task).
    loc = parse_location("base 团队 招聘 北京站")
    assert loc.city == "Beijing"
    assert loc.country == "CN"


def test_paren_role_descriptor_preserves_work_mode_when_no_city() -> None:
    # Regression guard: probe fall-through must NOT lose work_mode. The paren
    # captures a non-city token, every shape probe misses, bare-scan misses,
    # but "remote" is still in the string so work_mode stays REMOTE.
    loc = parse_location("（高级）Backend Engineer Remote")
    assert loc.city is None
    assert loc.work_mode is WorkMode.REMOTE
