"""Link-aggregator sources (Hacker News) submit external links with no article body of their own.
When a source is flagged credibility_meta.fetch_full_content, the fetcher detects the thin (link-only)
content and fetches+extracts the LINKED article's body instead of storing a bare URL."""
import feedparser
import pytest
from sqlalchemy import select

from app.models import Article, Source, SourceType
from app.services import fetcher


def _feed(description: str, link="https://example.com/real-article", title="Cool external article"):
    xml = (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>HN</title>'
        f"<item><title>{title}</title><link>{link}</link><description>{description}</description></item>"
        "</channel></rss>"
    )
    return feedparser.parse(xml)


@pytest.mark.parametrize(
    "text,thin",
    [
        ("https://news.ycombinator.com/item?id=123", True),  # bare link
        ("Comments", True),  # too short
        ("", True),
        (None, True),
        ("A" * 400, False),  # long real text
        (
            "Here is a full paragraph of real article text that carries actual meaning and context, "
            "with a trailing link https://example.com/x that is a small fraction of it.",
            False,
        ),
    ],
)
def test_is_thin_content(text, thin):
    assert fetcher._is_thin_content(text) is thin


@pytest.mark.asyncio
async def test_extract_linked_content_skips_hn_discussion_links():
    # An HN comments page is not the article — must return empty WITHOUT fetching.
    assert await fetcher._extract_linked_content("https://news.ycombinator.com/item?id=99") == (None, None)


@pytest.mark.asyncio
async def test_flagged_source_fetches_linked_article_body(db_session, monkeypatch):
    calls = []

    async def fake_extract(url):
        calls.append(url)
        return ("Rich snippet.", "Full rich body text extracted from the linked article. " * 20)

    monkeypatch.setattr(fetcher, "_extract_linked_content", fake_extract)

    src = Source(
        name="HN test", url="https://news.ycombinator.com", rss_url="https://hnrss.org/frontpage",
        source_type=SourceType.other, per_fetch_cap=10, credibility_meta={"fetch_full_content": True},
    )
    db_session.add(src)
    await db_session.flush()

    feed = _feed("https://news.ycombinator.com/item?id=123")  # thin: content is a bare link
    n = await fetcher._ingest_feed_entries(db_session, src, feed)

    assert n == 1
    assert calls == ["https://example.com/real-article"]  # fetched the EXTERNAL article, not the HN page
    art = (await db_session.execute(select(Article).where(Article.source_id == src.id))).scalar_one()
    assert art.extracted_text.startswith("Full rich body text")  # real body, not the bare link


@pytest.mark.asyncio
async def test_unflagged_source_does_not_fetch_linked_content(db_session, monkeypatch):
    calls = []

    async def fake_extract(url):
        calls.append(url)
        return ("x", "y")

    monkeypatch.setattr(fetcher, "_extract_linked_content", fake_extract)

    src = Source(
        name="Plain test", url="https://plain.example", rss_url="https://plain.example/rss",
        source_type=SourceType.other, per_fetch_cap=10,  # NO fetch_full_content flag
    )
    db_session.add(src)
    await db_session.flush()

    feed = _feed("https://news.ycombinator.com/item?id=123", link="https://plain.example/a")
    await fetcher._ingest_feed_entries(db_session, src, feed)

    assert calls == []  # feature is off for this source → never fetched


@pytest.mark.asyncio
async def test_duplicate_item_is_not_refetched(db_session, monkeypatch):
    # Review #4: the linked fetch runs AFTER dedup, so an already-ingested item isn't re-downloaded
    # on every fetch cycle.
    calls = []

    async def fake_extract(url):
        calls.append(url)
        return ("s", "Full body text " * 20)

    monkeypatch.setattr(fetcher, "_extract_linked_content", fake_extract)
    src = Source(
        name="HN dup", url="https://news.ycombinator.com", rss_url="https://hnrss.org/frontpage",
        source_type=SourceType.other, per_fetch_cap=10, credibility_meta={"fetch_full_content": True},
    )
    db_session.add(src)
    await db_session.flush()
    feed = _feed("https://news.ycombinator.com/item?id=1", link="https://example.com/dup-article")

    await fetcher._ingest_feed_entries(db_session, src, feed)  # first: new → fetched
    await fetcher._ingest_feed_entries(db_session, src, feed)  # second: duplicate → skipped before fetch

    assert calls == ["https://example.com/dup-article"]  # fetched exactly once
