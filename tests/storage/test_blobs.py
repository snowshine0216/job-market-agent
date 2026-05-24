from datetime import UTC, datetime
from pathlib import Path

from jma.storage.blobs import read, write


def test_write_uses_correct_path_scheme(tmp_path: Path) -> None:
    ref = write(
        root=tmp_path,
        source="testerhome",
        url="https://testerhome.com/jobs?page=1",
        body="<html>hi</html>",
        now=datetime(2026, 5, 21, 10, 0, tzinfo=UTC),
    )
    assert ref.startswith("raw/testerhome/20260521/")
    assert ref.endswith(".html.gz")
    # Path: 16-char sha1 prefix
    fname = Path(ref).name
    assert len(fname) == len("0123456789abcdef.html.gz")  # 24
    assert (tmp_path / ref).exists()


def test_round_trip(tmp_path: Path) -> None:
    payload = "<html><body>" + ("ABCD" * 1000) + "</body></html>"
    ref = write(
        root=tmp_path,
        source="testerhome",
        url="https://x/page",
        body=payload,
        now=datetime(2026, 5, 21, tzinfo=UTC),
    )
    out = read(root=tmp_path, ref=ref)
    assert out == payload


def test_same_url_same_day_same_path(tmp_path: Path) -> None:
    ts = datetime(2026, 5, 21, tzinfo=UTC)
    a = write(root=tmp_path, source="testerhome", url="https://x/y", body="a", now=ts)
    b = write(root=tmp_path, source="testerhome", url="https://x/y", body="b", now=ts)
    assert a == b  # path is deterministic
    # body 'b' overwrote 'a'
    assert read(root=tmp_path, ref=a) == "b"


def test_write_with_json_gz_suffix(tmp_path):
    """Bing source writes SerpAPI JSON page payloads with .json.gz (spec §3.6, §5.4)."""
    from jma.storage import blobs

    ref = blobs.write(
        root=tmp_path,
        source="bing",
        url="https://serpapi.com/search?q=foo&start=0",
        body='{"organic_results":[]}',
        suffix=".json.gz",
    )
    assert ref.endswith(".json.gz")
    assert "raw/bing/" in ref
    # Round-trip read.
    assert blobs.read(root=tmp_path, ref=ref) == '{"organic_results":[]}'
