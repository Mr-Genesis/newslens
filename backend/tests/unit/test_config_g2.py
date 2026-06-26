"""G2 S0: the per-user-relevance config knobs exist with safe-off / hypothesis-grade defaults."""
from app.config import Settings, settings


def test_g2_config_defaults(monkeypatch):
    # Assert the SHIPPED default (the code literal), independent of any ambient UER_ENABLED override —
    # construct a fresh Settings with it unset.
    monkeypatch.delenv("UER_ENABLED", raising=False)
    assert Settings().uer_enabled is True  # personalization is ON by default (no-op without signal)
    # The numeric knobs have no env override in any environment, so the singleton is representative.
    assert settings.uer_half_life_days == 21.0
    assert settings.uer_follow_weight == 1.0
    assert settings.uer_rank_alpha == 0.6
    assert settings.uer_rank_beta == 0.4


def test_g2_surface_personalization_defaults():
    """Surface knobs (feed/briefing/search) — conservative defaults, active when uer_enabled."""
    assert settings.uer_feed_pool_size == 500
    assert settings.uer_feed_blend_ratio == 0.3
    assert settings.uer_briefing_blend_weight == 0.2
    assert settings.uer_search_rerank_boost == 10.0
    assert settings.uer_search_relevance_threshold == 0.3
    # Invariant: the search boost must stay below the keyword/semantic tier gap (100) or keyword
    # results could be overtaken by boosted semantic ones.
    assert settings.uer_search_rerank_boost < 100
