from jma.sources.base import DetailConfig


def test_detail_config_defaults_to_disabled_and_empty() -> None:
    cfg = DetailConfig(body_selector=".topic-detail .markdown-body")
    assert cfg.enabled is False
    assert cfg.company_selectors == ()
    assert cfg.company_label_patterns == ()
    assert cfg.salary_selectors == ()
    assert cfg.salary_label_patterns == ()
