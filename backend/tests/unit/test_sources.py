"""E2 unit tests (pure, native): feed config + Google News builder + GDELT query."""
from app.config import settings
from app.services import fetcher


def test_google_news_rss_url_builder():
    url = fetcher.google_news_rss_url("RBI rate cut")
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "RBI" in url and "rate" in url
    assert "hl=en-IN" in url and "gl=IN" in url and "ceid=IN:en" in url


def test_load_feeds_has_india_and_global_and_no_bogus_reuters():
    feeds = fetcher.load_feeds()
    regions = {f.get("region") for f in feeds}
    assert "in" in regions and "global" in regions
    # the old bogus Reuters spec-page URL must be gone
    assert all("rss-specification" not in f["rss_url"] for f in feeds)
    assert all(f["rss_url"].startswith("http") for f in feeds)
    # India business desk present (the relevance payoff)
    names = {f["name"] for f in feeds}
    assert "Moneycontrol" in names and "The Hindu - National" in names


def test_gdelt_query_includes_country():
    assert "sourcecountry" in settings.gdelt_query
