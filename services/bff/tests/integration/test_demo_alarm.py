"""PRD-0019: real ASGI contract with Telegram replaced by an HTTP boundary fake."""
import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from bff.main import create_app
from tests.account_fakes import FakeAccounts
from tests.conftest import AUTH_USERS
from tests.conftest import FakeClock, ORIGIN, login, make_settings

URL = "/api/alarms/demo"
TOKEN = "123456:unit-test-token-not-a-real-secret"


@pytest.fixture
def demo():
    clock = FakeClock()
    calls = []
    response = {"status": 200, "body": {"ok": True, "result": {"message_id": 7, "chat": {"id": 123}}}}
    def transport(req):
        calls.append(req)
        if response.get("timeout"):
            raise httpx.ReadTimeout("private URL " + TOKEN, request=req)
        return httpx.Response(response["status"], json=response["body"])
    app = create_app(account_repository=FakeAccounts(AUTH_USERS), settings=make_settings(telegram_bot_token=TOKEN, telegram_chat_id="123"),
                     telegram_transport=httpx.MockTransport(transport), clock=clock)
    with TestClient(app, base_url=ORIGIN) as c:
        yield c, calls, response, clock


def post(c, key=None, **extra):
    return c.post(URL, json={"request_id": key or str(uuid4()), **extra}, headers={"Origin": ORIGIN})


def test_ops_and_csrf_before_any_external_call(demo):
    c, calls, _, _ = demo
    assert c.get(URL).status_code == 401
    assert post(c).status_code == 401
    login(c, "view_user", "view-pw")
    assert post(c).status_code == 403
    login(c, "ing_user", "ing-pw")
    assert post(c).status_code == 403
    login(c, "ops_user", "ops-pw")
    assert c.post(URL, json={"request_id": str(uuid4())}).status_code == 403
    assert not calls


def test_success_idempotency_cooldown_and_redaction(demo, caplog):
    c, calls, _, clock = demo
    caplog.set_level("INFO")
    login(c, "ops_user", "ops-pw")
    assert c.get(URL).json()["configured"] is True
    key = str(uuid4())
    sent = post(c, key)
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == "sent"
    assert sent.json()["event_id"] == key
    assert post(c, key).json()["event_id"] == key
    blocked = post(c)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert len(calls) == 1
    payload = json.loads(calls[0].content)
    assert payload["chat_id"] == "123"
    assert "DEMO" in payload["text"] and "無需處置" in payload["text"]
    assert "parse_mode" not in payload
    assert calls[0].url.host == "api.telegram.org"
    assert TOKEN not in sent.text + c.get(URL).text + caplog.text
    assert len(c.get(URL).json()["recent"]) == 1
    clock.advance(31)
    assert post(c).status_code == 200
    assert len(calls) == 2


@pytest.mark.parametrize("extra", [{"chat_id": "999"}, {"text": "arbitrary"}, {"token": "x"}])
def test_no_arbitrary_destination_or_message(demo, extra):
    c, calls, _, _ = demo
    login(c, "ops_user", "ops-pw")
    assert post(c, **extra).status_code == 422
    assert c.get(URL + "?chat_id=999").status_code == 422
    assert c.post(URL + "?x=1", json={"request_id":str(uuid4())}, headers={"Origin":ORIGIN}).status_code == 422
    assert post(c, "bad-id").status_code == 422
    assert not calls


@pytest.mark.parametrize("failure", [
    {"status": 403, "body": {"ok":False,"description":TOKEN}},
    {"status": 200, "body": {"ok":False}},
    {"status": 200, "body": {"ok":True}},
    {"status": 200, "body": {"ok":True,"result":{"message_id":7,"chat":{"id":999}}}},
    {"status": 200, "body": ["bad"]},
    {"timeout": True},
])
def test_failure_is_honest_and_same_id_never_retries(demo, failure):
    c, calls, response, clock = demo
    login(c, "ops_user", "ops-pw")
    response.update(failure)
    key = str(uuid4())
    result = post(c, key)
    assert result.status_code == 502
    assert TOKEN not in result.text
    clock.advance(31)
    assert post(c, key).status_code == 502
    assert len(calls) == 1
    assert c.get(URL).json()["recent"] == []


def test_missing_config_fails_closed(client, recorder):
    login(client, "ops_user", "ops-pw")
    assert client.get(URL).json()["configured"] is False
    assert post(client).status_code == 503
    assert not recorder.requests


def test_concurrent_clicks_make_only_one_provider_call():
    import asyncio
    from fastapi import HTTPException
    from bff.demo_alarms import DemoAlarms

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def provider(request):
            calls.append(request)
            entered.set()
            await release.wait()
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 8, "chat": {"id": 123}}})
        service = DemoAlarms(make_settings(telegram_bot_token=TOKEN, telegram_chat_id="123"), FakeClock())
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
            key = str(uuid4())
            task = asyncio.create_task(service.send(key, client))
            await asyncio.wait_for(entered.wait(), 1)
            try:
                with pytest.raises(HTTPException) as duplicate:
                    await service.send(key, client)
                assert duplicate.value.status_code == 409
                with pytest.raises(HTTPException) as second:
                    await service.send(str(uuid4()), client)
                assert second.value.status_code == 429
            finally:
                release.set()
                result = await task
            assert result["status"] == "sent"
            assert len(calls) == 1
    asyncio.run(scenario())
