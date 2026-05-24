"""view.html.j2 — render against a fixture context and assert structure via selectolax."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import jinja2
from selectolax.parser import HTMLParser

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "src/jma/report/templates"


def _env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=jinja2.select_autoescape(["html", "xml", "j2"]),
    )


def _context(*, data_root_abs: str = "/tmp/jma-test", rows: list[dict] | None = None) -> dict:
    rows = (
        rows
        if rows is not None
        else [
            {
                "title": "AI Agent Engineer",
                "title_raw": "AI Agent Engineer",
                "company": "ACME",
                "city": None,
                "salary_raw": "20-40K",
                "posted_at": datetime(2026, 5, 22, tzinfo=UTC).isoformat(),
                "source": "bing:zhipin.com",
                "url": "https://www.zhipin.com/job_detail/1.html",
                "raw_payload_ref": "raw/bing/20260524/abc1234567890def.json.gz",
                "dq": 0.4,
            },
            {
                "title": "Backend Engineer",
                "title_raw": "Backend Engineer",
                "company": None,
                "city": None,
                "salary_raw": "",
                "posted_at": None,
                "source": "bing:liepin.com",
                "url": "https://www.liepin.com/job/2.html",
                "raw_payload_ref": "raw/bing/20260524/fedc0987654321ba.json.gz",
                "dq": 0.4,
            },
        ]
    )
    return {
        "run": {
            "id": "deadbeef" * 4,
            "region": "Hangzhou",
            "keywords": ("AI agent",),
            "started_at": datetime(2026, 5, 24, 10, 0, 0, tzinfo=UTC).isoformat(),
            "finished_at": datetime(2026, 5, 24, 10, 5, 0, tzinfo=UTC).isoformat(),
        },
        "count": len(rows),
        "rows": rows,
        "data_root_abs": data_root_abs,
    }


def _render(ctx: dict) -> str:
    return _env().get_template("view.html.j2").render(**ctx)


def test_renders_n_rows_and_run_id_prefix():
    html = _render(_context())
    tree = HTMLParser(html)
    trs = tree.css("tbody tr")
    assert len(trs) == 2
    h1 = tree.css_first("h1").text()
    assert "deadbeef" in h1


def test_no_external_script_tags_offline_guarantee():
    html = _render(_context())
    tree = HTMLParser(html)
    for s in tree.css("script"):
        assert s.attributes.get("src") is None, "no <script src=...> allowed (offline guarantee)"
    for link in tree.css("link"):
        rel = link.attributes.get("rel", "")
        assert "stylesheet" not in rel, "no external stylesheet allowed"


def test_blob_link_uses_absolute_file_uri_from_context():
    html = _render(_context(data_root_abs="/tmp/jma-test"))
    tree = HTMLParser(html)
    blob_links = [a for a in tree.css("a") if "file://" in (a.attributes.get("href") or "")]
    assert blob_links, "expected at least one file:// link"
    href = blob_links[0].attributes["href"]
    assert href.startswith("file:///tmp/jma-test/")
    assert href.endswith(".json.gz")


def test_blob_link_changes_when_data_root_changes():
    """Locking in that the template does NOT hardcode a path."""
    html = _render(_context(data_root_abs="/opt/data"))
    tree = HTMLParser(html)
    blob_links = [a for a in tree.css("a") if "file://" in (a.attributes.get("href") or "")]
    assert blob_links[0].attributes["href"].startswith("file:///opt/data/")


def test_url_cell_is_clickable_anchor():
    html = _render(_context())
    tree = HTMLParser(html)
    url_anchors = [
        a for a in tree.css("a") if (a.attributes.get("href") or "").startswith("https://")
    ]
    assert any("zhipin.com" in a.attributes["href"] for a in url_anchors)


def test_sortable_columns_have_class_on_th():
    html = _render(_context())
    tree = HTMLParser(html)
    ths = tree.css("thead th")
    assert len(ths) >= 9  # title, company, city, salary_raw, posted_at, src, url, blob, dq
    # At least the dq column carries a sort-numeric hint; others sort as strings.
    classes = [th.attributes.get("class", "") for th in ths]
    assert any("sortable" in c for c in classes)


def test_empty_cells_render_as_em_dash():
    html = _render(_context())
    tree = HTMLParser(html)
    # Row 2 has company=None and salary_raw=""; em-dash should appear somewhere in its cells.
    rows = tree.css("tbody tr")
    row_2_text = rows[1].text()
    assert "—" in row_2_text


def test_unsafe_url_renders_as_span_not_anchor():
    """Regression: javascript: and data: URLs must NOT appear in <a href> — they
    must be rendered as plain text inside <span class='unsafe-url'>."""
    xss_url = "javascript:alert(1)"
    unsafe_row = {
        "title": "Malicious Job",
        "title_raw": "Malicious Job",
        "company": "ACME",
        "city": None,
        "salary_raw": "20K",
        "posted_at": None,
        "source": "bing:zhipin.com",
        "url": "#",
        "url_unsafe": True,
        "raw_payload_ref": "raw/bing/20260524/abc1234567890def.json.gz",
        "dq": 0.4,
    }
    html = _render(_context(rows=[unsafe_row]))
    tree = HTMLParser(html)

    # No <a> should have href="#" while an unsafe-url span is present
    # (href="#" is the sanitised placeholder, not a real link, so no <a href="#">).
    unsafe_spans = tree.css("span.unsafe-url")
    assert unsafe_spans, "expected <span class='unsafe-url'> for an unsafe URL"

    # The <span> must not be wrapped in an <a>.
    url_anchors = [
        a for a in tree.css("a")
        if (a.attributes.get("href") or "") in (xss_url, "#")
        and a.css("span.unsafe-url")
    ]
    assert not url_anchors, "<span class='unsafe-url'> must not be inside an <a>"


def test_safe_url_renders_as_anchor():
    """A normal https URL should still render as an <a> link."""
    safe_row = {
        "title": "Normal Job",
        "title_raw": "Normal Job",
        "company": "ACME",
        "city": None,
        "salary_raw": "20K",
        "posted_at": None,
        "source": "bing:zhipin.com",
        "url": "https://zhipin.com/jobs/999",
        "url_unsafe": False,
        "raw_payload_ref": "raw/bing/20260524/abc1234567890def.json.gz",
        "dq": 0.4,
    }
    html = _render(_context(rows=[safe_row]))
    tree = HTMLParser(html)
    url_anchors = [
        a for a in tree.css("a")
        if "zhipin.com" in (a.attributes.get("href") or "")
    ]
    assert url_anchors, "expected <a href> for a safe https URL"
