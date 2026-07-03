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


async def test_profession_less_user_never_calls_the_llm(monkeypatch):
    audience._llm_tag_cache.clear()
    counter = {"n": 0}
    monkeypatch.setattr(llm, "generate", _stub_generate(["finance"], counter))
    assert await audience.resolve_tags(None, user_id=1, persona_version=1) == set()
    assert await audience.resolve_tags("  ", user_id=1, persona_version=1) == set()
    assert counter["n"] == 0  # empty profession → no LLM call, no cache write


async def test_cache_is_isolated_per_user(monkeypatch):
    audience._llm_tag_cache.clear()
    counter = {"n": 0}

    async def _gen(prompt, *a, **k):
        counter["n"] += 1
        return {"tags": ["finance"] if "Actuary" in prompt else ["science"]}
    monkeypatch.setattr(llm, "generate", _gen)

    a = await audience.resolve_tags("Actuary", user_id=1, persona_version=1)
    b = await audience.resolve_tags("Sommelier", user_id=2, persona_version=1)  # same persona_version
    assert a == {"finance"} and b == {"science"}   # user 2 got ITS own tags, not user 1's cache
    assert counter["n"] == 2


async def test_llm_failure_is_not_negative_cached(monkeypatch):
    audience._llm_tag_cache.clear()
    calls = {"n": 0}

    async def _flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise llm.LLMUnavailable("transient")
        return {"tags": ["finance"]}
    monkeypatch.setattr(llm, "generate", _flaky)

    first = await audience.resolve_tags("Actuary", user_id=1, persona_version=1)
    assert first == set()                                   # transient failure → keyword-only
    second = await audience.resolve_tags("Actuary", user_id=1, persona_version=1)
    assert second == {"finance"}                            # retried (failure was NOT cached)


async def test_long_tail_profession_sees_gated_content_in_briefing(aclient, db_session, monkeypatch, fake_llm):
    """Briefing gate also flows through resolve_tags — an LLM-classified Actuary sees finance research."""
    import sqlalchemy as sa
    from datetime import datetime, timezone

    from app.models import Article, ClusterArticle, Source, SourceType, StoryCluster, User
    audience._llm_tag_cache.clear()

    async def _gen(prompt, *a, **k):
        return {"tags": ["finance"]}
    monkeypatch.setattr(llm, "generate", _gen)

    u = (await db_session.execute(sa.select(User).where(User.id == 1))).scalar_one_or_none()
    if u is None:
        u = User(id=1, locale="IN")
        db_session.add(u)
    u.profession = "Actuary"
    await db_session.flush()

    src = Source(name="Noahpinion", url="https://noahpinion.example", rss_url="https://noahpinion.example/rss",
                 source_type=SourceType.expert, region="global", category="business",
                 credibility_score=90, audience=["finance"])  # 90 >= briefing floor 70
    db_session.add(src)
    await db_session.flush()
    art = Article(title="Macro briefing", url="https://noahpinion.example/b1", source_id=src.id,
                  snippet="a snippet", published_at=datetime(2026, 7, 3, tzinfo=timezone.utc))
    db_session.add(art)
    await db_session.flush()
    cl = StoryCluster(title="Macro briefing", summary="cached summary", coherence=0.9)
    db_session.add(cl)
    await db_session.flush()
    db_session.add(ClusterArticle(cluster_id=cl.id, article_id=art.id))
    await db_session.flush()

    titles = {s["title"] for s in (await aclient.get("/briefing")).json()["stories"]}
    assert "Macro briefing" in titles
