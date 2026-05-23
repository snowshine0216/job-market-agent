from jma.domain.models import Salary, SalaryPeriod
from jma.domain.normalize import parse_salary


def test_simple_monthly_range() -> None:
    s = parse_salary("10-20K")
    assert s == Salary(
        min=10000,
        max=20000,
        currency="CNY",
        period=SalaryPeriod.MONTHLY,
        months_per_year=12,
        raw="10-20K",
        parsed=True,
    )


def test_monthly_with_14_months() -> None:
    s = parse_salary("15-30K·14薪")
    assert s.min == 15000 and s.max == 30000
    assert s.currency == "CNY"
    assert s.period is SalaryPeriod.MONTHLY
    assert s.months_per_year == 14
    assert s.parsed is True


def test_monthly_with_13_months_lowercase_k() -> None:
    s = parse_salary("15-30k·13薪")
    assert s.months_per_year == 13
    assert s.parsed is True


def test_annual_cny_wan() -> None:
    s = parse_salary("年薪 40-60万")
    assert s.period is SalaryPeriod.ANNUAL
    assert s.currency == "CNY"
    assert s.min == 400000 // 12
    assert s.max == 600000 // 12
    assert s.months_per_year == 12
    assert s.parsed is True


def test_unparseable_chinese_competitive() -> None:
    s = parse_salary("面议")
    assert s == Salary(raw="面议")
    assert s.disclosure == "unparseable"


def test_empty_string_is_absent() -> None:
    s = parse_salary("")
    assert s == Salary(raw="")
    assert s.disclosure == "absent"


def test_usd_annual_range() -> None:
    s = parse_salary("$120K-$160K")
    assert s.currency == "USD"
    assert s.period is SalaryPeriod.ANNUAL
    assert s.min == 120000 // 12
    assert s.max == 160000 // 12
    assert s.parsed is True


def test_whitespace_padded_input() -> None:
    s = parse_salary("  10-20K  ")
    assert s.min == 10000 and s.max == 20000
    assert s.parsed is True


def test_full_width_digits_via_nfkc() -> None:
    s = parse_salary("１０-２０Ｋ")
    assert s.min == 10000 and s.max == 20000
    assert s.parsed is True


def test_double_k_explicit() -> None:
    s = parse_salary("15K-30K·14薪")
    assert s.min == 15000 and s.max == 30000 and s.months_per_year == 14


def test_daily_keeps_period_no_minmax() -> None:
    s = parse_salary("日薪 800-1200")
    assert s.period is SalaryPeriod.DAILY
    assert s.currency == "CNY"
    assert s.min is None and s.max is None
    assert s.parsed is True


def test_hourly_keeps_period_no_minmax() -> None:
    s = parse_salary("时薪 50")
    assert s.period is SalaryPeriod.HOURLY
    assert s.currency == "CNY"
    assert s.min is None and s.max is None
    assert s.parsed is True
