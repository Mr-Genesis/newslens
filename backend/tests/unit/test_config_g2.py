"""G2 S0: the per-user-relevance config knobs exist with safe-off / hypothesis-grade defaults."""
from app.config import settings


def test_g2_config_defaults():
    assert settings.uer_enabled is False  # overlay ships dark
    assert settings.uer_half_life_days == 21.0
    assert settings.uer_follow_weight == 1.0
    assert settings.uer_rank_alpha == 0.6
    assert settings.uer_rank_beta == 0.4
