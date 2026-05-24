from typer.testing import CliRunner

from jma.cli import app


def test_crawl_help_lists_source_default_bing() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["crawl", "--help"])
    assert result.exit_code == 0
    assert "bing" in result.stdout
    # --with-detail is gone in Phase 2 (dropped per spec §5.4)
    assert "--with-detail" not in result.stdout
