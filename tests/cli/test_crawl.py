from typer.testing import CliRunner

from jma.cli import app


def test_crawl_help_lists_with_detail_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["crawl", "--help"])
    assert result.exit_code == 0
    assert "--with-detail" in result.stdout
