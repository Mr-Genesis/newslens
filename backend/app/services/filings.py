"""India stock-exchange corporate filings (Phase 3).

The NSE per-company feeds (Board Meetings, Financial Results, Insider Trading, Voting Results) at
nsearchives.nseindia.com carry the company identity ONLY as a full legal name in <title> — there
is no stock symbol, ticker, or BSE scrip code in any structured field (verified live 2026-07-04).
So the whole feature keys on a normalized company NAME, produced by `norm_company` — the single
canonical key shared by the ingest filter, the entity alias, and the read-path visibility lookup
so they can never drift apart.
"""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Article, ArticleEntity, Entity, EntityAlias, Follow, User

# Watchlist entry types that name a company (region/topic don't).
_COMPANY_WATCH_TYPES = {"ticker", "entity"}

# Legal-form suffix words dropped from the match key, so "Reliance Industries Limited",
# "Reliance Industries Ltd." and "Reliance Industries" all collapse to one key. Kept deliberately
# small + unambiguous — never drop a token that could be part of a real name.
_SUFFIXES = {
    "limited", "ltd", "plc", "inc", "incorporated", "corp", "corporation",
    "co", "company", "llp", "lp", "pvt", "private",
}
# Drop punctuation by REMOVING it (not replacing with a space) so intra-word marks collapse:
# "D.K." → "dk" matches a watchlist "DK". Whitespace is preserved so words stay separate.
_PUNCT = re.compile(r"[^a-z0-9\s]+")


def norm_company(name: str | None) -> str:
    """Canonical match key for a company name: lowercased, punctuation → spaces, trailing legal-form
    suffix words dropped, whitespace collapsed. Empty string when there is nothing left (empty input,
    or a bare suffix like "Limited") — an empty key must never match anything.

    Examples: "Reliance Industries Limited" → "reliance industries"; "Dr. Lal Path Labs Ltd." →
    "dr lal path labs"; "D.K. Enterprises Global Limited" → "dk enterprises global".
    """
    if not name:
        return ""
    tokens = _PUNCT.sub("", name.lower()).split()
    # Strip trailing suffix tokens only (a leading "Co" — as in "Coal India" — must survive).
    while tokens and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def filing_company_name(entry, parser: str) -> str | None:
    """The verbatim company name for a filing feed item, or None when it isn't a real company.

    A seam keyed on the source's `credibility_meta.filing_parser`: the live NSE per-company feeds
    ("nse_name") put the clean full legal name directly in <title>, so we return the trimmed title
    (raw, for the entity's display name). Returns None when the title is empty or normalizes to
    nothing (a bare legal suffix) — those must never be ingested or attached. Unknown parsers fall
    back to the same title heuristic rather than silently dropping every item.
    """
    title = (getattr(entry, "title", "") or "").strip()
    if not title or not norm_company(title):
        return None
    return title


async def aggregate_watch_keys(db: AsyncSession) -> set[str]:
    """The union of `norm_company` keys across EVERY user's company watchlist + entity follows — the
    set the global ingest filter admits (ingestion has no per-user context). Empty when nobody
    watchlists anything, so the exchange firehose ingests NOTHING by default and the corpus is
    protected. Per-user isolation is enforced later at read time, not here.
    """
    keys: set[str] = set()
    wl_rows = (
        await db.execute(select(User.watchlist).where(User.watchlist.isnot(None)))
    ).scalars().all()
    for wl in wl_rows:
        for item in (wl or []):
            if isinstance(item, dict) and item.get("type") in _COMPANY_WATCH_TYPES:
                k = norm_company(item.get("value"))
                if k:
                    keys.add(k)
    follow_vals = (
        await db.execute(select(Follow.value).where(Follow.kind == "entity"))
    ).scalars().all()
    for v in follow_vals:
        k = norm_company(v)
        if k:
            keys.add(k)
    return keys


async def watchlisted_entity_ids(db: AsyncSession, user_id: int | None) -> set[int]:
    """The company entity ids THIS user may see filings for — their own watchlist (ticker/entity) +
    entity follows, resolved by the same `norm_company` key the ingest filter and attach use, so a
    watchlisted filing is never ingested-but-invisible. Returns empty when the feature is off, there
    is no user, or the user has no company watchlist/follows → the feed read-path is then a no-op
    (byte-identical). This is the PER-USER isolation control (aggregate keys gate ingest; this scopes
    visibility to the caller).
    """
    from app.config import settings

    if not settings.exchange_filings_enabled or user_id is None:
        return set()

    keys: set[str] = set()
    ids: set[int] = set()

    u = await db.get(User, user_id)
    for item in (u.watchlist or []) if u else []:
        if isinstance(item, dict) and item.get("type") in _COMPANY_WATCH_TYPES:
            k = norm_company(item.get("value"))
            if k:
                keys.add(k)

    frows = (
        await db.execute(
            select(Follow.value, Follow.entity_id).where(Follow.user_id == user_id, Follow.kind == "entity")
        )
    ).all()
    for value, eid in frows:
        if eid is not None:
            ids.add(eid)  # trustworthy id from a tapped chip
        k = norm_company(value)
        if k:
            keys.add(k)

    if keys:
        sorted_keys = sorted(keys)
        # A company whose legal name has no suffix stores no norm alias (key == name_norm), so match
        # BOTH the entity name_norm and the norm_company alias.
        name_ids = (
            await db.execute(select(Entity.id).where(Entity.name_norm.in_(sorted_keys)))
        ).scalars().all()
        alias_ids = (
            await db.execute(select(EntityAlias.entity_id).where(EntityAlias.alias_norm.in_(sorted_keys)))
        ).scalars().all()
        ids.update(name_ids)
        ids.update(alias_ids)
    return ids


async def attach_filing_entity(db: AsyncSession, article: Article, company_name: str) -> int | None:
    """Deterministically link a filing article to its company's `org` entity — no LLM, the company
    is known verbatim from <title>. Mirrors entities.resolve_and_persist's resolution order (exact
    name_norm → norm_company alias → create) so a filing shares the entity a news mention would use,
    and stores the `norm_company` key as an alias so a user's watchlist value resolves back to it.
    Idempotent (uq_entity_alias + uq_article_entity). Flushes only; the caller owns the commit.
    Returns the entity id, or None when the name normalizes to nothing.
    """
    canonical = (company_name or "").strip()
    name_norm = canonical.lower()
    key = norm_company(canonical)
    if not name_norm or not key:
        return None

    # 1. exact (org, name_norm)
    entity = (
        await db.execute(select(Entity).where(Entity.kind == "org", Entity.name_norm == name_norm))
    ).scalar_one_or_none()
    # 2. the norm_company key is a known alias of an existing entity
    if entity is None:
        ea = (
            await db.execute(select(EntityAlias).where(EntityAlias.alias_norm == key))
        ).scalars().first()
        if ea is not None:
            entity = await db.get(Entity, ea.entity_id)
    # 3. create
    if entity is None:
        entity = Entity(canonical_name=canonical, name_norm=name_norm, kind="org")
        db.add(entity)
        await db.flush()

    # Store the norm_company key as an alias (unless it equals the entity's own name_norm) so the
    # read-path can resolve a watchlist value to this entity by the same key the ingest filter uses.
    if key != entity.name_norm:
        dup = (
            await db.execute(
                select(EntityAlias).where(
                    EntityAlias.entity_id == entity.id, EntityAlias.alias_norm == key
                )
            )
        ).scalar_one_or_none()
        if dup is None:
            db.add(EntityAlias(entity_id=entity.id, alias=canonical, alias_norm=key, source="filing"))

    link = (
        await db.execute(
            select(ArticleEntity).where(
                ArticleEntity.article_id == article.id, ArticleEntity.entity_id == entity.id
            )
        )
    ).scalar_one_or_none()
    if link is None:
        db.add(ArticleEntity(article_id=article.id, entity_id=entity.id, salience=1.0, confidence=1.0))
    await db.flush()
    return entity.id
