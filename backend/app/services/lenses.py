"""LLM "lens" engine (E5 analysis · E6 WIIFM impact · E7 strategic/game-theory · E8 trivia).

Each lens: build a prompt from a cluster's source articles -> llm.generate(schema=...) ->
cache the parsed JSON on the cluster's JSONB column (sub-keyed by sub-lens / profession /
difficulty), invalidated by a hash of the cluster's article set. Returns a typed dict;
on no key returns ``{"unavailable": True}`` (never raises to the caller).
"""
import hashlib

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Article, ClusterArticle, StoryCluster, User
from app.services import llm

logger = structlog.get_logger()


def profession_hash(profession: str | None) -> str:
    """Stable, normalized cache key for a (free-text) profession. Empty -> 'default'."""
    norm = (profession or "").strip().lower()
    if not norm:
        return "default"
    return hashlib.sha1(norm.encode()).hexdigest()[:12]


def _source_hash(articles: list[Article]) -> str:
    ids = sorted(a.id for a in articles)
    return hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()[:16]


def _cluster_text(cluster: StoryCluster, articles: list[Article]) -> str:
    lines = [f"STORY: {cluster.title}"]
    for i, a in enumerate(articles, 1):
        lines.append(f"\n{i}. {a.title}")
        if a.snippet:
            lines.append(f"   {a.snippet[:400]}")
    return "\n".join(lines)


# ── prompt builders (each returns (prompt, schema_flag)) ──
def _prompt_key_facts(text):
    return (
        f"{text}\n\nExtract the 4-6 most important, concrete facts from the above coverage. "
        'Respond ONLY as JSON: {"facts": ["fact 1", "fact 2", ...]}'
    )


def _prompt_5ws(text):
    return (
        f"{text}\n\nAnswer the five Ws for this story. "
        'Respond ONLY as JSON: {"who": "...", "what": "...", "when": "...", '
        '"where": "...", "why": "..."}'
    )


def _prompt_profession(text, profession):
    who = profession or "a curious generalist reader"
    return (
        f"{text}\n\nExplain what this story means specifically for {who}. Be concrete and "
        'practical. Respond ONLY as JSON: {"headline": "one-line takeaway for them", '
        '"points": ["point 1", "point 2", "point 3"]}'
    )


def _prompt_impact(text, profession, locale):
    who = profession or "a curious generalist reader"
    return (
        f"{text}\n\nReader profile: profession='{who}', locale='{locale}'. "
        "Answer 'What's in it for me?' — how this news may affect this reader across "
        "Finance/markets, their Profession, Policy & regulation, and Daily life. Lead with a "
        "single sharp headline verdict (what it means + what, if anything, to consider). "
        'Respond ONLY as JSON: {"headline": "...", "dimensions": ['
        '{"key": "finance", "label": "Finance", "body": "..."}, '
        '{"key": "profession", "label": "Your field", "body": "..."}, '
        '{"key": "policy", "label": "Policy", "body": "..."}, '
        '{"key": "daily", "label": "Daily life", "body": "..."}]}'
    )


def _prompt_strategic(text):
    return (
        f"{text}\n\nGive a game-theory / strategic read of this story. Identify the key actors "
        "and each one's incentives and likely next move; name the type of 'game' being played "
        "(e.g. zero-sum, coordination, chicken, prisoner's dilemma, signalling); list 2-3 "
        "second-order effects; and end with one non-obvious take. "
        'Respond ONLY as JSON: {"actors": [{"name": "...", "incentive": "...", '
        '"likely_move": "..."}], "game_type": "...", "second_order": ["...", "..."], '
        '"non_obvious_take": "..."}'
    )


def _prompt_trivia(text, difficulty):
    return (
        f"{text}\n\nWrite 3 {difficulty}-difficulty multiple-choice quiz questions testing "
        "understanding of this story. Each has exactly 4 options, one correct. "
        'Respond ONLY as JSON: {"questions": [{"question": "...", "options": ["a","b","c","d"], '
        '"answer_index": 0, "explanation": "...", "difficulty": "' + difficulty + '"}]}'
    )


async def _load(db: AsyncSession, cluster_id: int):
    cluster = (
        await db.execute(select(StoryCluster).where(StoryCluster.id == cluster_id))
    ).scalar_one_or_none()
    if not cluster:
        return None, []
    articles = (
        await db.execute(
            select(Article)
            .join(ClusterArticle, ClusterArticle.article_id == Article.id)
            .where(ClusterArticle.cluster_id == cluster_id)
        )
    ).scalars().all()
    return cluster, list(articles)


async def get_lens(
    db: AsyncSession,
    cluster_id: int,
    *,
    column: str,
    subkey: str,
    prompt: str,
    schema: dict,
    force: bool = False,
):
    """Return cached lens JSON for (cluster, subkey) or generate + cache it."""
    cluster, articles = await _load(db, cluster_id)
    if cluster is None:
        return {"error": "cluster_not_found"}
    if not articles:
        return {"unavailable": True, "reason": "no_sources"}

    sh = _source_hash(articles)
    cache = dict(getattr(cluster, column) or {})
    entry = cache.get(subkey)
    if entry and entry.get("source_hash") == sh and not force:
        return {"cached": True, **entry["data"]}

    try:
        data = await llm.generate(prompt, schema=schema)
    except llm.LLMUnavailable:
        return {"unavailable": True, "reason": "no_llm_key"}
    except Exception as e:  # noqa: BLE001 — never 500 on an LLM/API failure
        logger.warning("lens_generate_failed", column=column, error=str(e))
        return {"unavailable": True, "reason": "llm_error"}
    if not isinstance(data, dict):
        data = {"result": data}

    cache[subkey] = {"source_hash": sh, "data": data}
    setattr(cluster, column, cache)
    await db.commit()
    return {"cached": False, **data}


# ── public API (used by routes) ──
async def analysis(db, cluster_id, lens: str, profession: str | None = None):
    cluster, articles = await _load(db, cluster_id)
    if cluster is None:
        return {"error": "cluster_not_found"}
    text = _cluster_text(cluster, articles) if articles else ""
    if lens == "key_facts":
        return await get_lens(db, cluster_id, column="analysis_json", subkey="key_facts",
                              prompt=_prompt_key_facts(text), schema={"facts": []})
    if lens == "5ws":
        return await get_lens(db, cluster_id, column="analysis_json", subkey="5ws",
                              prompt=_prompt_5ws(text), schema={"who": ""})
    if lens == "profession":
        return await get_lens(db, cluster_id, column="analysis_json",
                              subkey=f"prof:{profession_hash(profession)}",
                              prompt=_prompt_profession(text, profession),
                              schema={"headline": ""})
    return {"error": "unknown_lens"}


async def impact(db, cluster_id, profession: str | None, locale: str = "IN"):
    # WIIFM impact is profession-specific — without a profession there is no
    # meaningful answer, so surface that explicitly instead of defaulting to a
    # generalist read (and before any LLM/get_lens call).
    if not (profession or "").strip():
        return {"unavailable": True, "reason": "profession_unset"}
    cluster, articles = await _load(db, cluster_id)
    text = _cluster_text(cluster, articles) if cluster and articles else ""
    return await get_lens(db, cluster_id, column="impact_json",
                          subkey=f"prof:{profession_hash(profession)}",
                          prompt=_prompt_impact(text, profession, locale),
                          schema={"headline": "", "dimensions": []})


async def strategic(db, cluster_id):
    cluster, articles = await _load(db, cluster_id)
    text = _cluster_text(cluster, articles) if cluster and articles else ""
    return await get_lens(db, cluster_id, column="strategic_json", subkey="default",
                          prompt=_prompt_strategic(text), schema={"actors": []})


async def trivia(db, cluster_id, difficulty: str = "medium"):
    cluster, articles = await _load(db, cluster_id)
    text = _cluster_text(cluster, articles) if cluster and articles else ""
    return await get_lens(db, cluster_id, column="trivia_json", subkey=difficulty,
                          prompt=_prompt_trivia(text, difficulty), schema={"questions": []})
