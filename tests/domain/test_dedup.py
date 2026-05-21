from jma.domain.dedup import canonical_id, job_id


def test_job_id_deterministic_with_internal_id() -> None:
    a = job_id(source="testerhome", internal_id="123", title="X", company="Y", city="Hangzhou")
    b = job_id(source="testerhome", internal_id="123", title="X", company="Y", city="Hangzhou")
    assert a == b


def test_job_id_source_scoped() -> None:
    a = job_id(source="testerhome", internal_id="123", title="X", company="Y", city="Hangzhou")
    b = job_id(source="bing:zhaopin.com", internal_id="123", title="X", company="Y", city="Hangzhou")
    assert a != b


def test_job_id_fallback_when_internal_id_missing() -> None:
    a = job_id(source="testerhome", internal_id=None,
               title="AI Engineer", company="Foo", city="Hangzhou")
    b = job_id(source="testerhome", internal_id="",
               title="AI Engineer", company="Foo", city="Hangzhou")
    assert a == b  # both fall back to title|company|city
    c = job_id(source="testerhome", internal_id=None,
               title="AI Engineer", company="Foo", city="Shanghai")
    assert a != c


def test_job_id_fallback_nfkc_and_whitespace_collapse() -> None:
    # Full-width title + extra whitespace should collapse to the same id.
    a = job_id(source="testerhome", internal_id=None,
               title="AI Engineer", company="Foo", city="Hangzhou")
    b = job_id(source="testerhome", internal_id=None,
               title="ＡＩ  Engineer", company="foo", city=" Hangzhou ")
    assert a == b


def test_canonical_id_deterministic() -> None:
    a = canonical_id(title="AI Engineer", company="Foo", city="Hangzhou")
    b = canonical_id(title="AI Engineer", company="Foo", city="Hangzhou")
    assert a == b


def test_canonical_id_source_independent() -> None:
    # Two observations from two sources of the *same* posting share canonical id.
    obs_testerhome = canonical_id(title="AI Engineer", company="Foo", city="Hangzhou")
    obs_bing = canonical_id(title="AI Engineer", company="Foo", city="Hangzhou")
    assert obs_testerhome == obs_bing


def test_canonical_id_normalises_inputs() -> None:
    a = canonical_id(title="AI Engineer", company="Foo", city="Hangzhou")
    b = canonical_id(title="ai engineer", company="FOO", city=" hangzhou ")
    c = canonical_id(title="ＡＩ engineer", company="foo", city="Hangzhou")
    assert a == b == c


def test_canonical_id_handles_none() -> None:
    a = canonical_id(title="AI Engineer", company=None, city=None)
    b = canonical_id(title="ai engineer", company="", city="")
    assert a == b
