"""Phase 3 · #88 — LLM profession→tags classifier (keyword fast-path, LLM fallback, cached on persona_version)."""
from app.services import audience, llm


def _stub_generate(tags, counter):
    async def _gen(*a, **k):
        counter["n"] += 1
        return {"tags": tags}
    return _gen


async def test_keyword_hit_skips_the_llm(monkeypatch):
    audience._llm_tag_cache.clear()
    counter = {"n": 0}
    monkeypatch.setattr(llm, "generate", _stub_generate(["finance"], counter))
    tags = await audience.resolve_tags("Cardiologist", user_id=1, persona_version=1)
    assert "medicine" in tags
    assert counter["n"] == 0  # keyword map answered → no LLM call


async def test_keyword_miss_falls_back_to_llm(monkeypatch):
    audience._llm_tag_cache.clear()
    counter = {"n": 0}
    monkeypatch.setattr(llm, "generate", _stub_generate(["finance"], counter))
    tags = await audience.resolve_tags("Actuary", user_id=1, persona_version=1)
    assert tags == {"finance"} and counter["n"] == 1


async def test_classification_cached_on_persona_version(monkeypatch):
    audience._llm_tag_cache.clear()
    counter = {"n": 0}
    monkeypatch.setattr(llm, "generate", _stub_generate(["finance"], counter))
    await audience.resolve_tags("Actuary", user_id=1, persona_version=1)
    await audience.resolve_tags("Actuary", user_id=1, persona_version=1)  # cache hit
    assert counter["n"] == 1
    await audience.resolve_tags("Actuary", user_id=1, persona_version=2)  # profession changed
    assert counter["n"] == 2


async def test_llm_is_constrained_to_the_tag_vocabulary(monkeypatch):
    audience._llm_tag_cache.clear()
    counter = {"n": 0}
    monkeypatch.setattr(llm, "generate", _stub_generate(["finance", "cooking", "astrology"], counter))
    tags = await audience.resolve_tags("Actuary", user_id=1, persona_version=1)
    assert tags == {"finance"}  # invented tags dropped


async def test_no_llm_key_returns_keyword_result(monkeypatch):
    audience._llm_tag_cache.clear()

    async def _raise(*a, **k):
        raise llm.LLMUnavailable("no key")
    monkeypatch.setattr(llm, "generate", _raise)
    assert await audience.resolve_tags("Actuary", user_id=1, persona_version=1) == set()


async def test_long_tail_profession_sees_gated_content_in_feed(aclient, db_session, monkeypatch):
    """End-to-end: a profession the keyword map misses ("Actuary") is LLM-classified to `finance`, so
    the feed gate now admits a finance-tagged expert source for that user."""
    import sqlalchemy as sa

    from app.models import Article, Source, SourceType, User
    audience._llm_tag_cache.clear()
    counter = {"n": 0}
    monkeypatch.setattr(llm, "generate", _stub_generate(["finance"], counter))

    u = (await db_session.execute(sa.select(User).where(User.id == 1))).scalar_one_or_none()
    if u is None:
        u = User(id=1, locale="IN")
        db_session.add(u)
    u.profession = "Actuary"  # keyword map returns nothing → LLM fallback
    await db_session.flush()

    src = Source(name="Noahpinion", url="https://noahpinion.example", rss_url="https://noahpinion.example/rss",
                 source_type=SourceType.expert, region="global", category="business",
                 credibility_score=90, audience=["finance"])
    db_session.add(src)
    await db_session.flush()
    db_session.add(Article(title="Macro outlook", url="https://noahpinion.example/a1", source_id=src.id,
                           snippet="A long enough snippet for the feed card body text.",
                           published_at=__import__("datetime").datetime(2026, 7, 3, tzinfo=__import__("datetime").timezone.utc)))
    await db_session.flush()

    titles = {a["title"] for a in (await aclient.get("/feed?per_page=50")).json()["articles"]}
    assert "Macro outlook" in titles  # visible thanks to the LLM-classified `finance` tag
