"""Pure parsers for salary, experience, location strings (spec §1)."""
from __future__ import annotations

import re
import unicodedata

from jma.domain.models import Experience, Location, Salary, SalaryPeriod, WorkMode


def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def _normalize_for_match(s: str) -> str:
    """NFKC + lowercase + whitespace collapse + strip (shared helper, also used by dedup)."""
    folded = _nfkc(s).lower()
    return re.sub(r"\s+", " ", folded).strip()


normalize_for_match = _normalize_for_match

# -- salary --------------------------------------------------------------

_RE_MONTHLY_K = re.compile(
    r"(?P<min>\d+)\s*[Kk]?\s*[-–]\s*(?P<max>\d+)\s*[Kk](?:\s*·\s*(?P<months>\d+)\s*薪)?"
)
_RE_ANNUAL_WAN = re.compile(r"年薪\s*(?P<min>\d+)\s*[-–]\s*(?P<max>\d+)\s*万")
_RE_USD_ANNUAL = re.compile(
    r"\$\s*(?P<min>\d+)\s*K\s*[-–]\s*\$?\s*(?P<max>\d+)\s*K", re.IGNORECASE
)
_RE_DAILY = re.compile(r"日薪\s*(?P<min>\d+)(?:\s*[-–]\s*(?P<max>\d+))?")
_RE_HOURLY = re.compile(r"时薪\s*(?P<min>\d+)(?:\s*[-–]\s*(?P<max>\d+))?")


def _try_annual_cny(s: str, raw: str) -> Salary | None:
    """Return a Salary for CNY annual format (年薪 X-Y万), or None if no match."""
    m = _RE_ANNUAL_WAN.search(s)
    if not m:
        return None
    lo = int(m["min"]) * 10000
    hi = int(m["max"]) * 10000
    return Salary(min=lo // 12, max=hi // 12, currency="CNY",
                  period=SalaryPeriod.ANNUAL, months_per_year=12,
                  raw=raw, parsed=True)


def _try_monthly_k(s: str, raw: str) -> Salary | None:
    """Return a Salary for CNY monthly format (X-YK[·N薪]), or None if no match."""
    m = _RE_MONTHLY_K.search(s)
    if not m:
        return None
    months = int(m["months"]) if m["months"] else 12
    return Salary(min=int(m["min"]) * 1000, max=int(m["max"]) * 1000,
                  currency="CNY", period=SalaryPeriod.MONTHLY,
                  months_per_year=months, raw=raw, parsed=True)


def parse_salary(raw: str) -> Salary:
    if raw == "":
        return Salary(raw="")

    s = _nfkc(raw).strip()
    if s == "":
        return Salary(raw=raw)

    # USD annual — check first because it has its own currency.
    m = _RE_USD_ANNUAL.search(s)
    if m:
        lo = int(m["min"]) * 1000
        hi = int(m["max"]) * 1000
        return Salary(min=lo // 12, max=hi // 12, currency="USD",
                      period=SalaryPeriod.ANNUAL, months_per_year=12,
                      raw=raw, parsed=True)

    result = _try_annual_cny(s, raw)
    if result:
        return result

    # CNY daily (日薪 X[-Y]).
    m = _RE_DAILY.search(s)
    if m:
        return Salary(min=None, max=None, currency="CNY",
                      period=SalaryPeriod.DAILY, months_per_year=None,
                      raw=raw, parsed=True)

    # CNY hourly (时薪 X[-Y]).
    m = _RE_HOURLY.search(s)
    if m:
        return Salary(min=None, max=None, currency="CNY",
                      period=SalaryPeriod.HOURLY, months_per_year=None,
                      raw=raw, parsed=True)

    result = _try_monthly_k(s, raw)
    if result:
        return result

    return Salary(raw=raw)


# -- experience ----------------------------------------------------------

_RE_EXP_RANGE = re.compile(r"(?P<min>\d+)\s*[-–]\s*(?P<max>\d+)\s*年")
_RE_EXP_OPEN = re.compile(r"(?P<min>\d+)\s*年以上")
_FRESH_TOKENS = ("应届", "fresh graduate", "fresh-grad")


def parse_experience(text: str) -> Experience:
    if text == "":
        return Experience(raw="")
    s = _nfkc(text)
    lower = s.lower()
    if any(tok in lower for tok in _FRESH_TOKENS):
        return Experience(min_years=0, max_years=0, raw=text)
    m = _RE_EXP_RANGE.search(s)
    if m:
        return Experience(min_years=int(m["min"]), max_years=int(m["max"]), raw=text)
    m = _RE_EXP_OPEN.search(s)
    if m:
        return Experience(min_years=int(m["min"]), max_years=None, raw=text)
    return Experience(raw=text)


# -- location ------------------------------------------------------------

_CITY_PINYIN: dict[str, str] = {
    "北京": "Beijing",
    "上海": "Shanghai",
    "杭州": "Hangzhou",
    "深圳": "Shenzhen",
    "广州": "Guangzhou",
    "南京": "Nanjing",
    "成都": "Chengdu",
    "苏州": "Suzhou",
    "武汉": "Wuhan",
    "西安": "Xi'an",
    "重庆": "Chongqing",
}

_RE_BRACKET = re.compile(r"【\s*(?P<inside>[^】]+?)\s*】")
_REMOTE_TOKENS_CN = ("远程",)
_REMOTE_TOKENS_EN = ("remote",)


def parse_location(text: str) -> Location:
    if text == "":
        return Location()
    s = _nfkc(text)
    lower = s.lower()

    work_mode = WorkMode.UNKNOWN
    if any(tok in s for tok in _REMOTE_TOKENS_CN) or any(tok in lower for tok in _REMOTE_TOKENS_EN):
        work_mode = WorkMode.REMOTE

    m = _RE_BRACKET.search(s)
    if not m:
        return Location(work_mode=work_mode)

    inside = m["inside"].strip()
    # Inside is either "city" or "city·district" or "远程".
    if inside in _REMOTE_TOKENS_CN:
        return Location(work_mode=WorkMode.REMOTE)

    parts = [p.strip() for p in inside.split("·") if p.strip()]
    city_native = parts[0] if parts else ""
    district = parts[1] if len(parts) > 1 else None
    city = _CITY_PINYIN.get(city_native)
    if city is None:
        # Unknown native city: keep native form in district, leave city blank.
        return Location(country="CN", city=None, district=city_native, work_mode=work_mode)
    return Location(country="CN", city=city, district=district, work_mode=work_mode)
