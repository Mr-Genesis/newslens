"""G2 S0: the per-user-relevance config knobs exist with safe-off / hypothesis-grade defaults."""
from app.config import Settings, settings


def test_g2_config_defaults(monkeypatch):
    # Assert the SHIPPED default (the code literal), independent of any ambient UER_ENABLED that a
    # local docker-compose.override.yml may set for dev — construct a fresh Settings with it unset.
    monkeypatch.delenv("UER_ENABLED", raising=False)
    assert Settings().uer_enabled is False  # overlay ships dark
    # The numeric knobs have no env override in any environment, so the singleton is representative.
    assert settings.uer_half_life_days == 21.0
    assert settings.uer_follow_weight == 1.0
    assert settings.uer_rank_alpha == 0.6
    assert settings.uer_rank_beta == 0.4
