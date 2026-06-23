"""E3 (profile) + E1 (gemini key) endpoint integration tests."""
import pytest


@pytest.mark.asyncio
async def test_put_and_get_profile_with_interests(aclient, db_session):
    r = await aclient.put(
        "/profile",
        json={"profession": "cardiologist", "locale": "IN", "interests": ["Health", "Science"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["profession"] == "cardiologist"
    assert body["locale"] == "IN"
    assert set(body["interests"]) == {"Health", "Science"}

    g = await aclient.get("/profile")
    assert g.json()["profession"] == "cardiologist"
    assert set(g.json()["interests"]) == {"Health", "Science"}


@pytest.mark.asyncio
async def test_profile_accepts_arbitrary_freetext_profession(aclient, db_session):
    r = await aclient.put("/profile", json={"profession": "marine biologist"})
    assert r.status_code == 200
    assert r.json()["profession"] == "marine biologist"


@pytest.mark.asyncio
async def test_set_and_clear_gemini_key(aclient, db_session):
    r = await aclient.put("/settings/gemini-key", json={"gemini_api_key": "test-key-123"})
    assert r.status_code == 200
    assert r.json()["has_gemini_key"] is True
    r2 = await aclient.put("/settings/gemini-key", json={"gemini_api_key": None})
    assert r2.status_code == 200
    assert r2.json()["has_gemini_key"] is False
