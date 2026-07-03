"""LLM "lens" engine (E5 analysis · E6 WIIFM impact · E7 strategic · E8 trivia).

Each lens: build a prompt from a cluster's source articles -> llm.generate -> cache the
parsed JSON on the cluster's JSONB column, invalidated by the cluster's article-set hash and
a 24h TTL. On no key returns ``{"unavailable": True}`` (never raises to the caller).

Wave A: the impact lens is rebuilt to IMPACT_ENGINE_SPEC — a full per-persona contract
(StoryImpact) that is Pydantic-validated, guardrail-linted (no-advice / groundedness /
honesty / hype), and cached per persona_hash. Cache WRITES use a server-side JSONB merge so
concurrent writes to different subkeys of the same cluster row can't clobber each other.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import async_session
from app.models import Article, ArticleTopic, ClusterArticle, ClusterEdge, StoryCluster, Topic
from app.schemas import AskAnswer, FinancialDimension, StoryImpact
from app.services import frameworks as fw
from app.services import impact_guardrails, llm, retrieval

logger = structlog.get_logger()

_LENS_COLUMNS = {"analysis_json", "impact_json", "strategic_json", "trivia_json", "extra_json"}


def _utcnow() -> datetime:
    """Injectable clock — tests monkeypatch this to exercise the TTL."""
    return datetime.now(timezone.utc)


def profession_hash(profession: str | None) -> str:
    """Stable, normalized cache key for a (free-text) profession. Empty -> 'default'."""
    norm = (profession or "").strip().lower()
    if not norm:
        return "default"
    return hashlib.sha1(norm.encode()).hexdigest()[:12]


def persona_hash(persona: dict | None) -> str:
    """Stable hash over the impact-relevant persona fields (profession normalized for
    case/whitespace). Two readers with different interests/watchlist/region get different
    impacts; the same reader re-cased hits the same cache entry."""
    p = persona or {}
    blob = {
        "profession": (p.get("profession") or "").strip().lower(),
        "interests": sorted(p.get("interests") or []),
        "watchlist": p.get("watchlist") or [],
        "country": p.get("country"),
        "region": p.get("region"),
        "depth_pref": p.get("depth_pref") or "standard",
        "persona_version": p.get("persona_version") or 1,
    }
    return hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()[:16]


def _source_hash(articles: list[Article]) -> str:
    ids = sorted(a.id for a in articles)
    return hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()[:16]


def _cluster_text(
    cluster: StoryCluster, articles: list[Article], depth_pref: str = "standard"
) -> str:
    # Wave D1: route through the retrieval seam so lenses see full bodies, not snippet[:400].
    # depth_pref drives the retrieval budget ladder (brief/standard/expert).
    return retrieval.cluster_text(cluster, articles, depth_pref=depth_pref)


_DEPTH_STYLE = {
    "brief": "Answer for a general reader in a hurry: plainest language, shortest form, no jargon.",
    "expert": (
        "Answer for a domain-expert reader: precise terminology, concrete figures, mechanisms and "
        "second-order implications — skip basic explanations."
    ),
}


def _depth_suffix(depth_pref: str | None) -> str:
    """Depth instruction appended to lens prompts so brief/standard/expert visibly differ."""
    style = _DEPTH_STYLE.get(depth_pref or "standard")
    return f"\n\n{style}" if style else ""


# ── analysis / strategic / trivia prompt builders (unchanged) ──
def _prompt_key_facts(text_):
    return (
        f"{text_}\n\nExtract the 4-6 most important, concrete facts from the above coverage. "
        'Respond ONLY as JSON: {"facts": ["fact 1", "fact 2", ...]}'
    )


def _prompt_5ws(text_):
    return (
        f"{text_}\n\nAnswer the five Ws for this story. "
        'Respond ONLY as JSON: {"who": "...", "what": "...", "when": "...", '
        '"where": "...", "why": "..."}'
    )


def _prompt_profession(text_, profession):
    who = profession or "a curious generalist reader"
    return (
        f"{text_}\n\nExplain what this story means specifically for {who}. Be concrete and "
        'practical. Respond ONLY as JSON: {"headline": "one-line takeaway for them", '
        '"points": ["point 1", "point 2", "point 3"]}'
    )


def _prompt_strategic(text_):
    return (
        f"{text_}\n\nGive a game-theory / strategic read of this story. Identify the key actors "
        "and each one's incentives and likely next move; name the type of 'game' being played "
        "(e.g. zero-sum, coordination, chicken, prisoner's dilemma, signalling); list 2-3 "
        "second-order effects; and end with one non-obvious take. "
        'Respond ONLY as JSON: {"actors": [{"name": "...", "incentive": "...", '
        '"likely_move": "..."}], "game_type": "...", "second_order": ["...", "..."], '
        '"non_obvious_take": "..."}'
    )


def _prompt_trivia(text_, difficulty):
    return (
        f"{text_}\n\nWrite 3 {difficulty}-difficulty multiple-choice quiz questions testing "
        "understanding of this story. Each has exactly 4 options, one correct. "
        'Respond ONLY as JSON: {"questions": [{"question": "...", "options": ["a","b","c","d"], '
        '"answer_index": 0, "explanation": "...", "difficulty": "' + difficulty + '"}]}'
    )


def _prompt_impact_legacy(text_, profession, locale):
    """Pre-Wave-A flat impact (used only when impact_v2_enabled is False)."""
    who = profession or "a curious generalist reader"
    return (
        f"{text_}\n\nReader profile: profession='{who}', locale='{locale}'. "
        "Answer 'What's in it for me?' across Finance/markets, their Profession, Policy, and "
        'Daily life. Respond ONLY as JSON: {"headline": "...", "dimensions": ['
        '{"key": "finance", "label": "Finance", "body": "..."}, '
        '{"key": "profession", "label": "Your field", "body": "..."}, '
        '{"key": "policy", "label": "Policy", "body": "..."}, '
        '{"key": "daily", "label": "Daily life", "body": "..."}]}'
    )


# ── Wave A impact prompt (IMPACT_ENGINE_SPEC §5) ──
_IMPACT_SYSTEM = (
    "You are the Impact Analyst for NewsLens. Given a clustered news story and ONE reader's "
    "persona, explain precisely and calmly how this story actually touches that specific "
    "person across three dimensions: their PROFESSION, their MONEY, and their CIVIC/regional "
    "life. Voice: an exceptionally well-briefed analyst writing for one smart reader. Plain, "
    "concrete, declarative. No filler, no superlatives, no hype.\n"
    "HARD RULES:\n"
    "1. GROUND EVERYTHING in the provided story + sources. Never invent events, numbers, "
    "dates, or entities. Cite the outlet for each non-obvious claim in 'evidence'.\n"
    "2. HONESTY OVER COVERAGE. If a dimension does not genuinely apply to THIS reader, set "
    "'applicable': false and leave its fields empty. Most stories have one or two strong "
    "dimensions, not three.\n"
    "3. NO FINANCIAL ADVICE EVER. For the financial dimension describe exposure and signals "
    "to watch only. Never recommend buying, selling, holding, allocating, or timing any asset, "
    "and never imply a price direction as a recommendation.\n"
    "4. PERSONALISE via the persona — tie each impact to their role, an interest, a watchlist "
    "entity, or their region. If you cannot tie it to the persona, it is probably not applicable.\n"
    "5. CALIBRATE 'horizon' (now|weeks|quarter|year_plus) and 'confidence' (low|medium|high) "
    "independently and honestly. Low confidence and far horizons are fine.\n"
    "6. OUTPUT JSON ONLY, matching the requested shape exactly. No prose outside the JSON."
)

_IMPACT_SHAPE_HINT = (
    'Return ONLY this JSON shape:\n'
    '{"headline": "<one sentence>", '
    '"personal_relevance": {"score": <0-100 integer>, "one_liner": "<why it matters to you>"}, '
    '"dimensions": {'
    '"professional": {"applicable": <bool>, "relevance": "", "mechanism": "", '
    '"watch_items": [], "horizon": "now|weeks|quarter|year_plus", '
    '"confidence": "low|medium|high", "confidence_rationale": "", '
    '"evidence": [{"claim": "", "source": "<outlet>"}]}, '
    '"financial": {<same fields as professional>}, '
    '"civic": {<same fields as professional>}}, '
    '"caveats": "<what could change this read>"}\n'
    "Do NOT include a 'not_advice' field — it is set by the system."
)

_IMPACT_STRICTER = (
    "\n\nIMPORTANT: your previous draft broke a rule. The financial dimension must NEVER "
    "recommend buying/selling/holding/allocating or imply a price direction — describe "
    "exposure and signals to watch only. Use no hype words. Re-answer."
)


def _impact_source_lines(articles: list[Article], depth_pref: str = "standard") -> str:
    # Wave D1: full bodies, budgeted by depth, via the retrieval seam (was snippet[:240]).
    return retrieval.source_lines(articles, depth_pref=depth_pref)


def _impact_user(persona: dict, cluster: StoryCluster, articles: list[Article], source_lines: str) -> str:
    today = _utcnow().date().isoformat()
    interests = ", ".join(persona.get("interests") or []) or "—"
    watch = json.dumps(persona.get("watchlist") or [])
    return (
        f"Today: {today}. Reader locale: {persona.get('country') or '—'}/"
        f"{persona.get('region') or '—'}, depth preference: {persona.get('depth_pref') or 'standard'}.\n\n"
        f"<persona>\nProfession: {persona.get('profession')}\nInterests: {interests}\n"
        f"Watchlist: {watch}\n</persona>\n\n"
        f"<story id=\"{cluster.id}\">\nHeadline: {cluster.title}\n"
        f"Summary: {cluster.summary or ''}\n</story>\n\n"
        f"<sources>\n{source_lines}\n</sources>\n\n"
        f"{_IMPACT_SHAPE_HINT}\n"
        "Omit dimensions that do not truly apply (applicable=false). Ground strictly in the above."
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
            .options(selectinload(Article.source))
            .join(ClusterArticle, ClusterArticle.article_id == Article.id)
            .where(ClusterArticle.cluster_id == cluster_id)
        )
    ).scalars().all()
    return cluster, list(articles)


# ── cache helpers ──
def _cache_read(cluster: StoryCluster, column: str, subkey: str, sh: str):
    """Return cached lens data for (cluster, subkey) if fresh (matching source-hash + within
    TTL), else None. Old entries without a timestamp are treated as stale."""
    entry = (getattr(cluster, column) or {}).get(subkey)
    if not entry or entry.get("source_hash") != sh:
        return None
    gen = entry.get("generated_at")
    if not gen:
        return None
    try:
        ts = datetime.fromisoformat(gen)
    except (TypeError, ValueError):
        return None
    if (_utcnow() - ts) > timedelta(hours=settings.impact_cache_ttl_hours):
        return None
    return entry.get("data")


async def _cache_write(db: AsyncSession, cluster: StoryCluster, column: str, subkey: str, sh: str, data: dict):
    """Server-side JSONB merge — never a read-modify-write — so concurrent writes to different
    subkeys of the same cluster row can't clobber each other. We then expire just this column on
    the in-session object so a subsequent read in the same session re-fetches the merged value
    (the raw UPDATE bypasses the ORM identity map)."""
    assert column in _LENS_COLUMNS
    entry = {subkey: {"source_hash": sh, "data": data, "generated_at": _utcnow().isoformat()}}
    await db.execute(
        text(
            f"UPDATE story_clusters SET {column} = "
            f"COALESCE({column}, '{{}}'::jsonb) || CAST(:entry AS jsonb) WHERE id = :cid"
        ),
        {"entry": json.dumps(entry), "cid": cluster.id},
    )
    await db.commit()
    db.expire(cluster, [column])


# ── Discover tension line (#98) ──────────────────────────────────────────────────────
_TENSION_SYSTEM = (
    "You write the single sharpest 'tension line' for a news story: the core conflict in one clause "
    "— who or what is pitted against whom, and what is at stake. Neutral, specific, no hype, no "
    "clickbait, no trailing period. Maximum ~90 characters."
)


def _tension_prompt(cluster: StoryCluster, source_lines: str) -> str:
    return (
        f"Story: {cluster.title}\n\nSources:\n{source_lines}\n\n"
        f'Return JSON {{"tension_line": "<= 90 chars>"}} — the one-line core conflict of this story.'
    )


async def tension_line(db: AsyncSession, cluster_id: int) -> str | None:
    """The discover tension line for a cluster: cache-read, else generate + cache. Returns the string
    or None (unavailable). Cached on extra_json['tension'] keyed on the cluster source_hash."""
    cluster, articles = await _load(db, cluster_id)
    if cluster is None or not articles:
        return None
    sh = _source_hash(articles)
    cached = _cache_read(cluster, "extra_json", "tension", sh)
    if cached is not None:
        return cached.get("line")
    try:
        raw = await llm.generate(
            _tension_prompt(cluster, retrieval.source_lines(articles)),
            system=_TENSION_SYSTEM, schema={"tension_line": {}}, max_tokens=120,
            force_platform_key=True,
        )
    except llm.LLMUnavailable:
        return None
    except Exception as e:  # noqa: BLE001 — a bad LLM response must never break the backfill run
        logger.warning("tension_line_failed", cluster_id=cluster_id, error=str(e))
        return None
    line = ((raw.get("tension_line") if isinstance(raw, dict) else None) or "").strip()[:120]
    if not line:
        return None
    await _cache_write(db, cluster, "extra_json", "tension", sh, {"line": line})
    return line


async def backfill_tension_lines(session=None) -> int:
    """APScheduler job: generate tension lines for recent clusters lacking a fresh one. Gated by
    tension_lines_enabled; on-change via source_hash; no-op without a platform LLM key."""
    if not settings.tension_lines_enabled:
        return 0
    if session is not None:
        return await _backfill_tension(session)
    async with async_session() as s:
        return await _backfill_tension(s)


async def _backfill_tension(session) -> int:
    rows = (
        await session.execute(
            select(StoryCluster.id).order_by(StoryCluster.created_at.desc())
            .limit(settings.tension_batch_size)
        )
    ).all()
    made = 0
    for (cid,) in rows:
        if await tension_line(session, cid):
            made += 1
    logger.info("tension_backfill_complete", processed=len(rows), made=made)
    return made


def coherence_heuristic(source_count: int) -> float:
    """Source-overlap (breadth) fallback when no real agreement metric exists — a coverage proxy,
    not a learned score. The UI labels it honestly as 'source overlap', never 'agreement'."""
    if source_count >= 5:
        return 0.95
    if source_count >= 3:
        return 0.85
    if source_count >= 2:
        return 0.75
    return 0.65


def cluster_coherence(cluster: StoryCluster, articles: list[Article]) -> float:
    """Honest coherence for a cluster. Prefers the REAL source-agreement ratio (agree_count / total)
    from a cached consensus pass for the current sources — so a contested story can score below the
    heuristic floor — then the stored value, then the source-overlap heuristic. Pure read (no LLM, no
    extra query): it only inspects the already-loaded cluster + the consensus cache."""
    try:
        cons = _cache_read(cluster, "extra_json", "consensus", _source_hash(articles))
    except AttributeError:
        cons = None  # cluster-like object without the JSONB column → fall through (never crash a read)
    if isinstance(cons, dict):
        total = cons.get("total") or 0
        if total > 0:
            return max(0.0, min(1.0, (cons.get("agree_count") or 0) / total))
    if getattr(cluster, "coherence", None) is not None:
        return cluster.coherence
    return coherence_heuristic(len({a.source_id for a in articles}) or len(articles))


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
    if not force:
        cached = _cache_read(cluster, column, subkey, sh)
        if cached is not None:
            return {"cached": True, **cached}

    try:
        data = await llm.generate(prompt, schema=schema)
    except llm.LLMUnavailable:
        return {"unavailable": True, "reason": "no_llm_key"}
    except Exception as e:  # noqa: BLE001 — never 500 on an LLM/API failure
        logger.warning("lens_generate_failed", column=column, error=str(e))
        return {"unavailable": True, "reason": "llm_error"}
    if not isinstance(data, dict):
        data = {"result": data}

    await _cache_write(db, cluster, column, subkey, sh, data)
    return {"cached": False, **data}


# ── public API (used by routes) ──
async def analysis(
    db, cluster_id, lens: str, profession: str | None = None,
    depth_pref: str = "standard",
):
    cluster, articles = await _load(db, cluster_id)
    if cluster is None:
        return {"error": "cluster_not_found"}
    text_ = _cluster_text(cluster, articles, depth_pref=depth_pref) if articles else ""
    # Depth-scoped cache subkeys ONLY for non-standard depths: existing standard caches stay
    # valid, and brief/expert answers can never cross-serve (the 04-plan cache trap).
    dp = "" if depth_pref in (None, "", "standard") else f":{depth_pref}"
    ds = _depth_suffix(depth_pref)
    if lens == "key_facts":
        return await get_lens(db, cluster_id, column="analysis_json", subkey=f"key_facts{dp}",
                              prompt=_prompt_key_facts(text_) + ds, schema={"facts": []})
    if lens == "5ws":
        return await get_lens(db, cluster_id, column="analysis_json", subkey=f"5ws{dp}",
                              prompt=_prompt_5ws(text_) + ds, schema={"who": ""})
    if lens == "profession":
        return await get_lens(db, cluster_id, column="analysis_json",
                              subkey=f"prof:{profession_hash(profession)}{dp}",
                              prompt=_prompt_profession(text_, profession) + ds,
                              schema={"headline": ""})
    return {"error": "unknown_lens"}


async def strategic(db, cluster_id):
    cluster, articles = await _load(db, cluster_id)
    text_ = _cluster_text(cluster, articles) if cluster and articles else ""
    return await get_lens(db, cluster_id, column="strategic_json", subkey="default",
                          prompt=_prompt_strategic(text_), schema={"actors": []})


async def trivia(db, cluster_id, difficulty: str = "medium"):
    cluster, articles = await _load(db, cluster_id)
    text_ = _cluster_text(cluster, articles) if cluster and articles else ""
    return await get_lens(db, cluster_id, column="trivia_json", subkey=difficulty,
                          prompt=_prompt_trivia(text_, difficulty), schema={"questions": []})


async def impact(db, cluster_id, persona: dict, *, force: bool = False):
    """WIIFM impact (Wave A): per-persona, structured, validated, guardrail-linted.

    Flow (≤2 generations): generate -> StoryImpact.model_validate (regen on failure) ->
    stamp not_advice -> enforce_honesty + groundedness lint -> no-advice/hype lint (regen,
    else fail-safe drop the money dimension) -> JSONB-merge cache -> return.
    """
    profession = (persona.get("profession") or "").strip()
    # WIIFM is profession-specific — without one there is no meaningful answer.
    if not profession:
        return {"unavailable": True, "reason": "profession_unset"}

    if not settings.impact_v2_enabled:  # legacy flat lens
        cluster, articles = await _load(db, cluster_id)
        text_ = _cluster_text(cluster, articles) if cluster and articles else ""
        return await get_lens(db, cluster_id, column="impact_json",
                              subkey=f"prof:{profession_hash(profession)}",
                              prompt=_prompt_impact_legacy(text_, profession, persona.get("country") or "IN"),
                              schema={"headline": "", "dimensions": []})

    cluster, articles = await _load(db, cluster_id)
    if cluster is None:
        return {"error": "cluster_not_found"}
    if not articles:
        return {"unavailable": True, "reason": "no_sources"}

    sh = _source_hash(articles)
    subkey = f"persona:{persona_hash(persona)}"
    if not force:
        cached = _cache_read(cluster, "impact_json", subkey, sh)
        if cached is not None:
            return {"cached": True, **cached}

    outlets = [a.source.name for a in articles if a.source]
    user_prompt = _impact_user(
        persona, cluster, articles,
        _impact_source_lines(articles, persona.get("depth_pref") or "standard"),
    )

    MAX_GENS = 2
    payload: dict | None = None
    for attempt in range(1, MAX_GENS + 1):
        try:
            raw = await llm.generate(
                user_prompt, system=_IMPACT_SYSTEM, schema={"story_impact": True},
                max_tokens=settings.impact_max_tokens,
            )
        except llm.LLMUnavailable:
            return {"unavailable": True, "reason": "no_llm_key"}
        except Exception as e:  # noqa: BLE001 — transient; retry within budget
            logger.warning("impact_generate_failed", attempt=attempt, error=str(e))
            continue

        try:
            obj = StoryImpact.model_validate(raw if isinstance(raw, dict) else {})
        except Exception as e:  # noqa: BLE001 — invalid shape; regenerate within budget
            logger.info("impact_invalid", attempt=attempt, error=str(e)[:200])
            continue

        p = obj.model_dump(mode="json")
        p["cluster_id"] = str(cluster_id)
        p["dimensions"]["financial"]["not_advice"] = True  # stamped server-side
        impact_guardrails.enforce_honesty(p)
        impact_guardrails.lint_groundedness(p, outlets)
        advice = impact_guardrails.lint_no_advice(p["dimensions"]["financial"])
        hype = impact_guardrails.detect_hype(p)

        if (advice or hype) and attempt < MAX_GENS:
            user_prompt = user_prompt + _IMPACT_STRICTER
            continue
        if advice:  # budget exhausted but advice survives → fail safe: drop the money dimension
            p["dimensions"]["financial"] = FinancialDimension(applicable=False).model_dump(mode="json")
        payload = p
        break

    if payload is None:
        return {"unavailable": True, "reason": "impact_invalid"}

    await _cache_write(db, cluster, "impact_json", subkey, sh, payload)
    return {"cached": False, **payload}


# ── Ask this story (Wave B1) ──
_ASK_SYSTEM = (
    "You answer a reader's question about ONE news story using ONLY the provided sources. "
    "Ground every claim in those sources and cite the outlet for each. If the sources do not "
    "answer the question, do NOT guess — set refused=true and leave the answer empty. Never give "
    "financial or medical advice. Plain, concrete, no hype."
)


def _ask_user(question: str, cluster: StoryCluster, source_lines: str) -> str:
    return (
        f"<story>\nHeadline: {cluster.title}\nSummary: {cluster.summary or ''}\n</story>\n\n"
        f"<sources>\n{source_lines}\n</sources>\n\n"
        f'Reader question: "{question}"\n\n'
        'Answer ONLY from the sources. Respond ONLY as JSON: '
        '{"answer": "...", "citations": [{"claim": "...", "source": "<outlet>"}], '
        '"refused": false}. If the sources do not answer it, set refused=true and answer to "".'
    )


async def ask(db, cluster_id, question: str):
    """Grounded, cited Q&A over a single cluster's sources. Refuses (never fabricates) when the
    answer isn't supported; drops citations whose outlet isn't in the cluster."""
    cluster, articles = await _load(db, cluster_id)
    if cluster is None:
        return {"error": "cluster_not_found"}
    if not articles:
        return {"unavailable": True, "reason": "no_sources"}
    outlets = {(a.source.name or "").strip().lower() for a in articles if a.source}

    try:
        raw = await llm.generate(
            _ask_user(question, cluster, _impact_source_lines(articles)),
            system=_ASK_SYSTEM, schema={"answer": ""}, max_tokens=600,
        )
    except llm.LLMUnavailable:
        return {"unavailable": True, "reason": "no_llm_key"}
    except Exception as e:  # noqa: BLE001 — never 500 on an LLM/API failure
        logger.warning("ask_failed", error=str(e))
        return {"unavailable": True, "reason": "llm_error"}

    try:
        obj = AskAnswer.model_validate(raw if isinstance(raw, dict) else {})
    except Exception as e:  # noqa: BLE001
        logger.info("ask_invalid", error=str(e)[:200])
        return {"unavailable": True, "reason": "ask_invalid"}

    p = obj.model_dump(mode="json")
    # Groundedness: keep only citations whose outlet is one of the cluster's sources.
    p["citations"] = [
        c for c in p["citations"] if (c.get("source", "").strip().lower() in outlets)
    ]
    # No grounded answer text → treat as a refusal rather than an empty assertion.
    if not (p.get("answer") or "").strip():
        p["refused"] = True
    return p


# ── Frameworks (Wave B2): show-the-working, auto-selected, ≤20-word lines ──
_FRAMEWORKS_SYSTEM = (
    "You apply named analytical frameworks to a news story. For each requested framework, write "
    "ONE insight line of at most 20 words, grounded in the story. Forecast/game-theory lines must "
    "include a falsifiable condition; analogy/precedent lines must include the disanalogy. No hype, "
    "no financial or medical advice. Output JSON only."
)


def _frameworks_prompt(cluster: StoryCluster, selected: list[dict], source_lines: str) -> str:
    rows = "\n".join(
        f"- {f['id']} ({f['label']}): {fw.GUARDRAILS.get(f['id'], 'one grounded insight line')}"
        for f in selected
    )
    return (
        f"<story>\nHeadline: {cluster.title}\nSummary: {cluster.summary or ''}\n</story>\n\n"
        f"<sources>\n{source_lines}\n</sources>\n\n"
        f"Apply these frameworks (≤20 words each), grounded in the sources above:\n{rows}\n\n"
        'Respond ONLY as JSON: {"lines": {"<framework_id>": "<one-line insight>"}}.'
    )


async def frameworks(db, cluster_id):
    """Auto-selected analytical-framework one-liners for a cluster (≤4 chips, ≤20 words each)."""
    cluster, articles = await _load(db, cluster_id)
    if cluster is None:
        return {"error": "cluster_not_found"}
    if not articles:
        return {"unavailable": True, "reason": "no_sources"}

    topic_rows = (
        await db.execute(
            select(Topic.name)
            .join(ArticleTopic, ArticleTopic.topic_id == Topic.id)
            .join(ClusterArticle, ClusterArticle.article_id == ArticleTopic.article_id)
            .where(ClusterArticle.cluster_id == cluster_id)
        )
    ).all()
    story_type = fw.infer_story_type([r[0] for r in topic_rows])
    selected = fw.select_frameworks(story_type)
    if not selected:
        return {"frameworks": [], "story_type": story_type}

    sh = _source_hash(articles)
    subkey = f"frameworks:{story_type}"
    cached = _cache_read(cluster, "extra_json", subkey, sh)
    if cached is None:
        try:
            raw = await llm.generate(
                _frameworks_prompt(cluster, selected, retrieval.source_lines(articles)),
                system=_FRAMEWORKS_SYSTEM, schema={"lines": {}}, max_tokens=500,
            )
        except llm.LLMUnavailable:
            return {"unavailable": True, "reason": "no_llm_key"}
        except Exception as e:  # noqa: BLE001
            logger.warning("frameworks_failed", error=str(e))
            return {"unavailable": True, "reason": "llm_error"}
        raw_lines = (raw.get("lines") if isinstance(raw, dict) else None) or {}
        data = {"lines": {k: fw.clamp_words(str(v), 20) for k, v in raw_lines.items()}}
        await _cache_write(db, cluster, "extra_json", subkey, sh, data)
        cached = data

    lines = cached.get("lines", {})
    return {
        "story_type": story_type,
        "frameworks": [
            {"id": f["id"], "label": f["label"], "one_liner": lines.get(f["id"], "")}
            for f in selected
        ],
    }


# ── Consensus / divergence (Wave B3): the real "where they diverge" metric ──
_CONSENSUS_SYSTEM = (
    "You assess whether a story's sources AGREE or DIVERGE. Read the sources and report how many "
    "concur on the core claim and which outlets dissent and on what specific point. Ground strictly "
    "in the provided sources and use only their outlet names. No hype."
)


def _consensus_prompt(cluster: StoryCluster, source_lines: str) -> str:
    return (
        f"<story>\nHeadline: {cluster.title}\nSummary: {cluster.summary or ''}\n</story>\n\n"
        f"<sources>\n{source_lines}\n</sources>\n\n"
        'Respond ONLY as JSON: {"agree_count": <int>, '
        '"dissent": [{"outlet": "<name>", "point": "what they dispute"}], '
        '"summary": "<one line, e.g. 6 of 7 align>"}. Use only outlets from the sources.'
    )


async def consensus(db, cluster_id):
    """One grounded LLM pass → agree/dissent split + the disputed point. Cached; dissent whose
    outlet isn't a cluster source is dropped (groundedness)."""
    cluster, articles = await _load(db, cluster_id)
    if cluster is None:
        return {"error": "cluster_not_found"}
    if not articles:
        return {"unavailable": True, "reason": "no_sources"}
    outlets = {(a.source.name or "").strip().lower() for a in articles if a.source}
    sh = _source_hash(articles)
    cached = _cache_read(cluster, "extra_json", "consensus", sh)
    if cached is None:
        try:
            raw = await llm.generate(
                _consensus_prompt(cluster, _impact_source_lines(articles)),
                system=_CONSENSUS_SYSTEM, schema={"summary": ""}, max_tokens=400,
            )
        except llm.LLMUnavailable:
            return {"unavailable": True, "reason": "no_llm_key"}
        except Exception as e:  # noqa: BLE001
            logger.warning("consensus_failed", error=str(e))
            return {"unavailable": True, "reason": "llm_error"}
        d = raw if isinstance(raw, dict) else {}
        dissent = [
            x for x in (d.get("dissent") or [])
            if isinstance(x, dict) and (x.get("outlet", "").strip().lower() in outlets)
        ]
        try:
            agree = int(d.get("agree_count") or 0)
        except (TypeError, ValueError):
            agree = 0
        data = {
            "agree_count": agree,
            "total": len(articles),
            "dissent": dissent,
            "summary": str(d.get("summary") or ""),
        }
        await _cache_write(db, cluster, "extra_json", "consensus", sh, data)
        cached = data
    return cached


# ── "How we got here" timeline (Wave D2) ──
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _timeline_prompt(cluster: StoryCluster, articles: list[Article], neighbours: list[str]) -> str:
    ordered = sorted(articles, key=lambda a: (a.published_at or a.fetched_at or _EPOCH))
    chron = "\n".join(f"- {(a.published_at or a.fetched_at or '?')}: {a.title}" for a in ordered)
    nbr = "\n".join(f"- {t}" for t in neighbours) or "—"
    return (
        f"<story>\nHeadline: {cluster.title}\n</story>\n\n"
        f"<chronology>\n{chron}\n</chronology>\n\n"
        f"<related_prior_stories>\n{nbr}\n</related_prior_stories>\n\n"
        'Write a brief "how we got here". Respond ONLY as JSON: '
        '{"how_we_got_here": "...", "timeline": [{"when": "...", "what": "..."}]}.'
    )


async def timeline(db, cluster_id):
    """'How we got here' — within-cluster chronology + prior related clusters (cluster_edges)."""
    cluster, articles = await _load(db, cluster_id)
    if cluster is None:
        return {"error": "cluster_not_found"}
    if not articles:
        return {"unavailable": True, "reason": "no_sources"}
    neighbours = [
        r[0]
        for r in (
            await db.execute(
                select(StoryCluster.title)
                .join(ClusterEdge, ClusterEdge.dst_cluster_id == StoryCluster.id)
                .where(ClusterEdge.src_cluster_id == cluster_id)
            )
        ).all()
    ]
    return await get_lens(
        db, cluster_id, column="extra_json", subkey="timeline",
        prompt=_timeline_prompt(cluster, articles, neighbours), schema={"how_we_got_here": ""},
    )
