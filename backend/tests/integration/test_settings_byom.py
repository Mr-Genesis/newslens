"""Wave E S4: settings API — anthropic key (masked), active_provider + model_prefs, no-clobber,
error redaction. Real DB harness (touches the new user_settings columns)."""
import pytest


@pytest.mark.asyncio
async def test_set_and_get_anthropic_key_masked(aclient, db_session):
    r = await aclient.put("/settings/anthropic-key", json={"anthropic_api_key": "sk-ant-secret123"})
    assert r.status_code == 200 and r.json()["has_anthropic_key"] is True
    got = (await aclient.get("/settings")).json()
    assert got["has_anthropic_key"] is True
    assert got["anthropic_key_last4"] == "t123"          # last-4 only
    assert "sk-ant-secret123" not in str(got)            # raw key never returned


@pytest.mark.asyncio
async def test_set_active_provider_and_model_prefs(aclient, db_session):
    r = await aclient.put(
        "/settings", json={"active_provider": "anthropic", "model_prefs": {"anthropic": "claude-sonnet-4-6"}}
    )
    assert r.status_code == 200
    got = (await aclient.get("/settings")).json()
    assert got["active_provider"] == "anthropic"
    assert got["model_prefs"]["anthropic"] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_invalid_active_provider_rejected(aclient, db_session):
    r = await aclient.put("/settings", json={"active_provider": "bogus"})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_changing_provider_does_not_clobber_openai_key(aclient, db_session):
    await aclient.put("/settings", json={"openai_api_key": "sk-openai-xyz"})
    await aclient.put("/settings", json={"active_provider": "gemini"})  # no key in this request
    got = (await aclient.get("/settings")).json()
    assert got["has_openai_key"] is True       # key preserved (omitted field untouched)
    assert got["active_provider"] == "gemini"


@pytest.mark.asyncio
async def test_test_anthropic_key_redacts_errors(aclient, db_session, monkeypatch):
    await aclient.put("/settings/anthropic-key", json={"anthropic_api_key": "sk-ant-LEAKME"})
    import anthropic

    class _Msgs:
        async def create(self, **kw):
            raise RuntimeError("boom for key sk-ant-LEAKME at https://api.example/x")

    class _Client:
        def __init__(self, api_key=None):
            self.messages = _Msgs()

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _Client)
    body = (await aclient.post("/settings/test-anthropic-key")).json()
    assert body["success"] is False
    assert body["error"] == "Anthropic key test failed"      # fixed string
    assert "sk-ant-LEAKME" not in str(body) and "boom" not in str(body)  # no leak
