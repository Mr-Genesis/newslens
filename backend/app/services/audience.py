"""Persona gating for the research/expert source tiers.

Maps a user's free-text profession to a set of audience tags. Gated sources (source_type
research/expert) only enter a user's feed/briefing when their `audience` array overlaps these
tags. A user with no profession set → empty tags → gated sources stay hidden (the feed is
byte-identical to the pre-expansion behaviour). Keyword-based and deliberately generous; a
future LLM classifier + follow-override are the escape hatches for the long tail.
"""

# tag -> substrings that imply it (matched case-insensitively against the profession text).
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "medicine": (
        "doctor", "physician", "mbbs", "surgeon", "nurse", "clinician", "medical",
        "medicine", "cardiolog", "oncolog", "neurolog", "radiolog", "psychiatr",
        "pediatric", "paediatric", "epidemiolog", "pharma", "health", "gp ",
    ),
    "ai": ("ai", "artificial intelligence", "machine learning", " ml", "ml ", "data scien", "nlp", "llm"),
    "software": (
        "engineer", "developer", "programmer", "software", "sde", "devops",
        "backend", "frontend", "full stack", "fullstack", "cto", "architect",
    ),
    "finance": (
        "trader", "investor", "cfa", "banker", "finance", "financial", "quant",
        "portfolio", "hedge", "equity", "wealth", "broker",
    ),
    "economics": ("economist", "econ", "macro"),
    "policy": ("policy", "government", "bureaucrat", "civil serv", "ias", "diplomat", "regulator"),
    "law": ("lawyer", "advocate", "attorney", "legal", "counsel", "judge", "solicitor", "barrister"),
    "science": (
        "scientist", "physicist", "biologist", "chemist", "researcher", "phd",
        "academic", "professor", "postdoc",
    ),
    "startup": ("founder", "entrepreneur", "startup", "co-founder"),
    "business": ("business", "manager", "consultant", "strategy", "operations", "product manager"),
    # Hardware / applied engineering — distinct from "software". Also carries the broad "technology"
    # tag so tech-tagged sources (IEEE Spectrum) reach any kind of engineer or technologist.
    "engineering": (
        "engineer", "mechanical", "electrical", "electronics", "hardware", "robotics",
        "aerospace", "civil eng", "semiconductor", "chip",
    ),
    "technology": ("engineer", "technolog", "hardware", "electronics", "semiconductor", "sysadmin", "it "),
}


def tags_for_profession(profession: str | None) -> set[str]:
    """Return the audience tags implied by a free-text profession (empty when unset/unmatched)."""
    if not profession or not profession.strip():
        return set()
    text = f" {profession.lower()} "
    return {tag for tag, kws in _KEYWORDS.items() if any(kw in text for kw in kws)}


# Phase 3 · #88 — LLM fallback for the long tail of professions the keyword map misses. Cached per
# user on persona_version (bumped on any profile edit), so the LLM runs at most once per profession.
# Process-local cache — a restart just re-classifies; no migration, no per-request cost on the hot path.
_llm_tag_cache: dict[tuple, frozenset] = {}
_TAG_SCHEMA = {
    "type": "object",
    "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
    "required": ["tags"],
}


async def classify_profession_llm(profession: str) -> set[str] | None:
    """Map a profession to the FIXED audience-tag vocabulary via the platform LLM.

    Returns the tag set on success (constrained to `_KEYWORDS` keys, so the model can never invent a
    tag no source uses), or None when the LLM CALL FAILED — the caller must not cache a failure as an
    empty result (that would permanently deny the user their sources until a profile edit / restart).
    """
    from app.services import llm

    vocab = sorted(_KEYWORDS.keys())
    prompt = (
        f"Map this profession to zero or more audience tags from EXACTLY this list: {vocab}. "
        f"Choose only tags whose news a person in that role would want. "
        f"Profession: {profession!r}. Return JSON {{\"tags\": [...]}} using only tags from the list."
    )
    try:
        result = await llm.generate(prompt, schema=_TAG_SCHEMA, force_platform_key=True)
    except Exception:  # noqa: BLE001 — call failed; signal None so resolve_tags degrades WITHOUT caching
        return None
    raw = result.get("tags") if isinstance(result, dict) else None
    # isinstance(str) guard: a malformed tags array (a dict/list element) would otherwise raise
    # TypeError on `t in _KEYWORDS` — on the feed/briefing HOT PATH. Non-string entries are dropped.
    return {t for t in (raw or []) if isinstance(t, str) and t in _KEYWORDS}


async def resolve_tags(profession: str | None, *, user_id=None, persona_version=None) -> set[str]:
    """Audience tags for a profession: keyword map first (fast, offline), LLM fallback for the tail.

    A keyword hit never calls the LLM. A successful LLM result is cached on (user_id, persona_version);
    a transient LLM failure is NOT cached, so the next request retries.
    """
    base = tags_for_profession(profession)
    if base:
        return base
    if not profession or not profession.strip():
        return set()
    key = (user_id, persona_version)
    if key in _llm_tag_cache:
        return set(_llm_tag_cache[key])
    tags = await classify_profession_llm(profession)
    if tags is None:
        return set()  # LLM call failed → keyword-only this time, do not poison the cache
    _llm_tag_cache[key] = frozenset(tags)
    return tags


def gated_source_types():
    """The source tiers subject to the audience/credibility gate. official = regulator/gov notices
    (audience-gated like research); filing = per-company disclosures (audience=[] ⇒ only ever
    admitted via the follow/watchlist branch). One constant so the feed/briefing/filter call sites
    can never drift apart. NOTE: the discover deck deliberately samples a NARROWER set (no filing) —
    see routes.get_discover_deck."""
    from app.models import SourceType

    return (SourceType.research, SourceType.expert, SourceType.official, SourceType.filing)


def allowed_source_ids(user_tags: set[str], *, floor: int, followed_source_ids=None):
    """A subquery of source ids a user may see, given their audience tags.

    News (non-gated) sources are always allowed. A gated (research/expert) source is allowed only
    when it clears the credibility floor AND its audience overlaps the user's tags (or has no
    audience). A user with no tags sees no audience-tagged gated sources — the pre-expansion feed.

    `followed_source_ids` (#81) is the opt-in escape hatch: a source the user explicitly follows is
    allowed unconditionally — bypassing BOTH the floor and the audience match — on the same
    "explicit intent" principle by which search is never gated. Empty/None ⇒ no override (the feed
    stays byte-identical for a user with no source-follows).
    """
    from sqlalchemy import and_, or_, select

    from app.models import Source

    if user_tags:
        audience_ok = or_(Source.audience.is_(None), Source.audience.overlap(sorted(user_tags)))
    else:
        # Empty tags: only audience-less gated sources could pass — asyncpg can't bind an empty
        # text[] for overlap, so express it directly.
        audience_ok = Source.audience.is_(None)

    gated_ok = and_(
        or_(Source.credibility_score.is_(None), Source.credibility_score >= floor),
        audience_ok,
    )
    branches = [
        Source.source_type.notin_(list(gated_source_types())),
        gated_ok,
    ]
    if followed_source_ids:
        branches.append(Source.id.in_(sorted(followed_source_ids)))
    return select(Source.id).where(or_(*branches))


async def followed_source_ids(db, user_id: int) -> set[int]:
    """The set of source ids this user follows (follows.kind == "source", value = the id string).

    FILING sources are excluded here on purpose: a filing source is one exchange firehose of
    thousands of companies, and the follow branch in `allowed_source_ids` admits a followed source
    UNCONDITIONALLY (bypassing floor + audience). Letting a filing source through it would flood the
    user with every watchlisted company's filings and defeat the per-company scoping in get_feed. So
    filings are admissible ONLY via the per-article watchlist branch — never as a followed source.
    This one exclusion closes the leak on every surface that consumes followed_source_ids (feed,
    briefing, digest) at once.
    """
    from sqlalchemy import select

    from app.models import Follow, Source, SourceType

    rows = (
        await db.execute(
            select(Follow.value).where(Follow.user_id == user_id, Follow.kind == "source")
        )
    ).scalars().all()
    ids = set()
    for v in rows:
        try:
            ids.add(int(v))
        except (TypeError, ValueError):
            continue
    if not ids:
        return ids
    filing_ids = set(
        (
            await db.execute(
                select(Source.id).where(
                    Source.id.in_(sorted(ids)), Source.source_type == SourceType.filing
                )
            )
        ).scalars().all()
    )
    return ids - filing_ids
