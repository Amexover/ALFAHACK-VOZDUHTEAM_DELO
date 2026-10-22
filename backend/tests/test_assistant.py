import asyncio
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app import pricing
from app.assistant.config import settings
from app.assistant.context import execute_tool, resolve_scope
from app.assistant.gateway import QwenGateway, VisibleText
from app.assistant.models import Conversation, Turn
from app.assistant.schemas import MessageIn
from app.assistant import service
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.models import Application, ApplicationEvent, User, utcnow
from tests.conftest import company_id, ready_draft, submitted


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "enabled", True)


@pytest.fixture
def inference(monkeypatch):
    calls = []
    rounds = []

    async def stream(self, messages, tools, allow_tools=True):
        calls.append(copy.deepcopy({"messages": messages, "tools": tools, "allow_tools": allow_tools}))
        result = rounds.pop(0) if rounds else {"text": "Рейтинг получен из бюро [rating]."}
        if "error" in result:
            raise result["error"]
        for text in result.get("deltas", [result.get("text", "")]):
            if text:
                yield {"type": "delta", "text": text}
        yield {"type": "result", "tool_calls": result.get("tool_calls", []),
               "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}

    monkeypatch.setattr(QwenGateway, "stream", stream)
    return calls, rounds


def conversation(api, **body):
    response = api.post("/assistant/conversations", body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def send(api, cid, content="Объясни рейтинг", **body):
    return api.post(f"/assistant/conversations/{cid}/messages", {
        "request_id": str(uuid4()), "content": content, **body})


def tool(name, arguments, id_="call_1"):
    return {"id": id_, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def test_auth_and_scope(client, alexey, maria, staff):
    assert client.get("/api/assistant/config").status_code == 401
    assert alexey.get("/assistant/config").json()["audience"] == "client"
    assert "application_review" not in alexey.get("/assistant/config").json()["intents"]
    cid = company_id(alexey, "ИП")
    other = company_id(maria, "Северный")
    assert alexey.post("/assistant/conversations", {"company_id": other}).status_code == 404
    chat = conversation(alexey, company_id=cid)
    assert maria.get(f"/assistant/conversations/{chat}").status_code == 404
    assert staff.get(f"/assistant/conversations/{chat}/messages").status_code == 404
    assert maria.c.delete(f"/api/assistant/conversations/{chat}", headers=maria.h).status_code == 404
    draft = ready_draft(alexey, cid)
    assert staff.post("/assistant/conversations", {"application_id": draft["id"]}).status_code == 404
    assert staff.post("/assistant/conversations", {"company_id": cid}).status_code == 422
    assert alexey.post("/assistant/conversations", {"company_id": other, "application_id": draft["id"]}).status_code == 404


def test_persist_history_idempotency_and_delete(alexey, inference):
    calls, _ = inference
    cid = conversation(alexey, company_id=company_id(alexey, "Маяк"))
    request_id = str(uuid4())
    response = send(alexey, cid, request_id=request_id, intent="rating")
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["status"] == "completed" and first["model"] == "Qwen/Qwen3.8-27B"
    assert first["usage"]["total_tokens"] == 30
    assert {s["id"] for s in first["sources"]} >= {"rating", "products"}
    assert '"score": 620' in calls[0]["messages"][0]["content"]
    assert send(alexey, cid, request_id=request_id, intent="rating").json() == first
    assert len(calls) == 1
    assert send(alexey, cid, "Другой вопрос", request_id=request_id).status_code == 409
    assert send(alexey, cid, "Продолжи").status_code == 200
    assert calls[1]["messages"][-3]["content"] == "Объясни рейтинг"
    assert calls[1]["messages"][-2]["role"] == "assistant"
    history = alexey.get(f"/assistant/conversations/{cid}/messages").json()
    assert len(history["items"]) == 2
    assert alexey.get("/assistant/conversations").json()["items"][0]["id"] == cid
    assert alexey.c.delete(f"/api/assistant/conversations/{cid}", headers=alexey.h).status_code == 204
    assert alexey.get(f"/assistant/conversations/{cid}").status_code == 404
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Turn)) == 0


def test_client_never_receives_internal_score(alexey, inference):
    calls, _ = inference
    aid = submitted(alexey, company_id(alexey, "ИП"))["id"]
    cid = conversation(alexey, application_id=aid)
    assert send(alexey, cid, "Расскажи про заявку").status_code == 200
    request = calls[0]["messages"][0]["content"]
    assert '"ruleset_version"' not in request
    assert '"scoring"' not in request and '"reject_reason_code"' not in request
    assert "get_queue" not in {t["function"]["name"] for t in calls[0]["tools"]}
    assert send(alexey, cid, intent="application_review").status_code == 403


def test_staff_uses_versioned_scoring_without_deciding(alexey, staff, inference):
    calls, rounds = inference
    aid = submitted(alexey, company_id(alexey, "ИП"))["id"]
    with SessionLocal() as db:
        before = db.get(Application, aid).status
        events = db.scalar(select(func.count()).select_from(ApplicationEvent))
    cid = conversation(staff, application_id=aid)
    rounds += [{"tool_calls": [tool("approve", {"application_id": aid})]}, {"text": "Черновик сводки [scoring]."}]
    response = send(staff, cid, "Разбери заявку", intent="application_review")
    assert response.status_code == 200, response.text
    assert '"ruleset_version"' in calls[0]["messages"][0]["content"]
    assert json.loads(calls[1]["messages"][-1]["content"])["error"] == "Инструмент недоступен"
    assert response.json()["tool_calls"] == [{"name": "approve", "ok": False}]
    assert all(t["function"]["name"] not in ("approve", "reject", "request_info") for t in calls[0]["tools"])
    with SessionLocal() as db:
        assert db.get(Application, aid).status == before
        assert db.scalar(select(func.count()).select_from(ApplicationEvent)) == events


def test_tool_math_and_scoped_arguments(alexey, inference):
    calls, rounds = inference
    cid = conversation(alexey, company_id=company_id(alexey, "ИП"))
    rounds += [{"tool_calls": [tool("calculate_quote", {"amount": 1000000, "term_months": 12,
                                                          "borrowing_mode": "NEW_CREDIT"})]},
               {"text": "Условия предварительные [quote]."}]
    response = send(alexey, cid, "Рассчитай миллион на год")
    assert response.status_code == 200, response.text
    result = json.loads(calls[1]["messages"][-1]["content"])
    assert result["rate"] == 18 and result["monthly_payment"] == pricing.annuity(1000000, 18, 12)
    assert any(s["id"] == "quote" for s in response.json()["sources"])
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.login == "alexey"))
        scope = resolve_scope(db, user, company_id(alexey, "ИП"), None)
        for name, args in [("get_company", {"company_id": 4}), ("get_queue", {}),
                           ("calculate_quote", {"amount": True, "term_months": 12, "borrowing_mode": "NEW_CREDIT"}),
                           ("calculate_quote", {"amount": 5000000, "term_months": 12, "borrowing_mode": "NEW_CREDIT"})]:
            assert "error" in execute_tool(db, scope, name, args)[0]


def test_unavailable_rating_is_not_replaced_with_old_score(alexey, inference):
    from app.simulators import bureau
    bureau.set_available(False)
    cid = conversation(alexey, company_id=company_id(alexey, "ИП"))
    assert send(alexey, cid, intent="rating").status_code == 200
    assert '"rating": null' in inference[0][0]["messages"][0]["content"]


def test_documents_privacy_news_and_validation(alexey, staff):
    payload = {"title": "Секретный регламент", "body": "Инструкция спецандеррайтинга zzzinternal", "audience": "staff"}
    url = "/api/assistant/knowledge/internal-policy"
    assert alexey.c.put(url, json=payload, headers=alexey.h).status_code == 403
    assert staff.c.put(url, json=payload, headers=staff.h).status_code == 200
    assert alexey.get("/assistant/knowledge/internal-policy").status_code == 404
    assert alexey.get("/assistant/knowledge?q=zzzinternal").json()["items"] == []
    assert staff.get("/assistant/knowledge?q=zzzinternal").json()["items"]
    assert alexey.get("/assistant/news").json()["has_real_news"] is False
    news = {"title": "Публикация для бизнеса", "body": "Тестовая подтверждённая редактором публикация.",
            "kind": "news", "source_url": "https://example.com/news", "published_at": "2026-01-01T09:00:00Z"}
    assert staff.c.put("/api/assistant/knowledge/business-news", headers=staff.h, json=news).status_code == 200
    found = alexey.get("/assistant/news").json()
    assert found["has_real_news"] and found["items"][0]["is_demo"] is False
    assert found["items"][0]["published_at"] and found["items"][0]["url"] == news["source_url"]
    for patch in ({"source_url": None}, {"published_at": None}, {"published_at": "2026-01-01T09:00:00"},
                  {"published_at": "2099-01-01T09:00:00Z"}):
        assert staff.c.put("/api/assistant/knowledge/bad-news", headers=staff.h, json={**news, **patch}).status_code == 422
    assert staff.c.put("/api/assistant/knowledge/pricing", headers=staff.h, json=payload).status_code == 409


def test_disabled_and_upstream_failure_release_lease(alexey, inference, monkeypatch):
    cid = conversation(alexey)
    monkeypatch.setattr(settings, "enabled", False)
    assert send(alexey, cid).json()["error"]["code"] == "ASSISTANT_DISABLED"
    monkeypatch.setattr(settings, "enabled", True)
    inference[1].append({"error": ApiError(504, "ASSISTANT_TIMEOUT", "Модель не ответила вовремя")})
    assert send(alexey, cid).status_code == 504
    history = alexey.get(f"/assistant/conversations/{cid}/messages").json()["items"]
    assert history[0]["status"] == "failed" and history[0]["assistant_content"] is None
    assert send(alexey, cid).status_code == 200
    assert len(inference[0][1]["messages"]) == 2  # failed messages excluded from model history


def test_sse_deltas_and_replay(alexey, inference):
    cid = conversation(alexey)
    inference[1].append({"deltas": ["Здравствуйте", "! Как помочь?"]})
    body = {"request_id": str(uuid4()), "content": "Привет"}
    result = alexey.post(f"/assistant/conversations/{cid}/messages/stream", body)
    assert result.status_code == 200 and result.headers["content-type"].startswith("text/event-stream")
    assert "event: delta" in result.text and "event: done" in result.text
    assert '"text": "Здравствуйте"' in result.text
    replay = alexey.post(f"/assistant/conversations/{cid}/messages/stream", body)
    assert '"replayed": true' in replay.text and len(inference[0]) == 1


def test_busy_rate_limit_and_expired_worker(alexey, inference, monkeypatch):
    cid = conversation(alexey)
    request_id = uuid4()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.login == "alexey"))
        turn_id, _ = service.reserve_turn(db, user, cid, MessageIn(request_id=request_id, content="Первое"))
    assert send(alexey, cid).status_code == 409
    assert alexey.c.delete(f"/api/assistant/conversations/{cid}", headers=alexey.h).status_code == 409
    with SessionLocal() as db:
        conv = db.get(Conversation, cid)
        conv.lease_until = utcnow() - timedelta(seconds=1)
        db.commit()
    stale = send(alexey, cid, "Первое", request_id=str(request_id))
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "ASSISTANT_INTERRUPTED"
    assert send(alexey, cid).status_code == 200
    assert service.finish_turn(turn_id, content="Поздний ответ старого процесса") is None
    with SessionLocal() as db:
        assert db.get(Turn, turn_id).error_code == "ASSISTANT_INTERRUPTED"
    monkeypatch.setattr(settings, "requests_per_minute", 1)
    assert send(alexey, cid).status_code == 429


def test_role_change_and_company_transfer_revoke_history(alexey, inference):
    cid = conversation(alexey, company_id=company_id(alexey, "ИП"))
    assert send(alexey, cid).status_code == 200
    with SessionLocal() as db:
        from app.models import Company
        conv = db.get(Conversation, cid)
        company = db.get(Company, conv.company_id)
        company.owner_id = db.scalar(select(User.id).where(User.login == "maria"))
        db.commit()
    assert alexey.get(f"/assistant/conversations/{cid}/messages").status_code == 404
    assert alexey.get("/assistant/conversations").json()["items"] == []


def test_cancelled_generation_marks_failed(alexey, monkeypatch):
    cid = conversation(alexey)

    async def waiting(self, *args, **kwargs):
        await asyncio.sleep(1000)
        yield {"type": "delta", "text": "never"}

    monkeypatch.setattr(QwenGateway, "stream", waiting)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.login == "alexey"))
        uid = user.id
        tid, _ = service.reserve_turn(db, user, cid, MessageIn(request_id=uuid4(), content="Привет"))

    async def cancel():
        events = service.generate(uid, cid, tid)
        await anext(events)
        await events.aclose()

    asyncio.run(cancel())
    with SessionLocal() as db:
        assert db.get(Turn, tid).error_code == "ASSISTANT_INTERRUPTED"
        assert db.get(Conversation, cid).lease_token is None


def test_concurrent_identical_requests_reserve_one_turn(alexey):
    cid = conversation(alexey)
    with SessionLocal() as db:
        uid = db.scalar(select(User.id).where(User.login == "alexey"))
    request = MessageIn(request_id=uuid4(), content="Один вопрос из двух вкладок")
    barrier = Barrier(2)

    def reserve():
        with SessionLocal() as db:
            user = db.get(User, uid)
            barrier.wait(timeout=10)
            try:
                tid, cached = service.reserve_turn(db, user, cid, request)
                return tid
            except ApiError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: reserve(), range(2)))
    assert results.count("ASSISTANT_BUSY") == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Turn).where(Turn.conversation_id == cid)) == 1
        tid = db.scalar(select(Turn.id).where(Turn.conversation_id == cid))
    assert service.finish_turn(tid, content="Завершено")["status"] == "completed"


def test_visible_text_handles_split_reasoning_tags():
    visible = VisibleText()
    text = "".join(visible.feed(t) for t in ["<thi", "nk>секрет", "</th", "ink>От", "вет"])
    text += visible.feed("", final=True)
    assert text == "Ответ"


def test_actual_http_protocol_and_split_tool_calls(monkeypatch):
    seen = []
    packets = [
        {"choices": [{"delta": {"reasoning_content": "hidden", "content": "<think>hidden</think>Ответ"}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "get_news", "arguments": "{"}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "}"}}]}, "finish_reason": "tool_calls"}]},
        {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}},
    ]

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, text="\n\n".join("data: " + json.dumps(p) for p in packets) + "\n\ndata: [DONE]\n\n")

    monkeypatch.setattr(QwenGateway, "client", lambda self: httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://inference/v1/"))

    async def collect():
        return [event async for event in QwenGateway().stream([{"role": "user", "content": "Привет"}], [])]

    events = asyncio.run(collect())
    assert events[0] == {"type": "delta", "text": "Ответ"}
    assert events[-1]["tool_calls"][0]["function"]["arguments"] == "{}"
    assert seen[0]["model"] == "Qwen/Qwen3.8-27B"
    assert seen[0]["chat_template_kwargs"]["enable_thinking"] is False


@pytest.mark.parametrize("response,expected", [
    (httpx.Response(429, text="secret upstream key"), "ASSISTANT_OVERLOADED"),
    (httpx.Response(500, text="secret upstream key"), "ASSISTANT_UPSTREAM_ERROR"),
    (httpx.Response(200, text="data: not-json\n\n"), "ASSISTANT_INVALID_RESPONSE"),
    (httpx.Response(200, text='data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n'), "ASSISTANT_OUTPUT_LIMIT"),
])
def test_actual_http_errors_are_sanitized(monkeypatch, response, expected):
    monkeypatch.setattr(QwenGateway, "client", lambda self: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: response), base_url="http://inference/v1/"))

    async def collect():
        return [event async for event in QwenGateway().stream([], [])]

    with pytest.raises(ApiError) as exc:
        asyncio.run(collect())
    assert exc.value.code == expected and "secret" not in exc.value.message


@pytest.mark.parametrize("model_id,expected", [("Qwen/Qwen3.8-27B", "ready"), ("other-model", "ASSISTANT_MODEL_MISSING")])
def test_inference_readiness_checks_exact_model(monkeypatch, model_id, expected):
    monkeypatch.setattr(QwenGateway, "client", lambda self: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [{"id": model_id}]})),
        base_url="http://inference/v1/"))
    if expected == "ready":
        assert asyncio.run(QwenGateway().health()) == {"status": "ready", "model": model_id}
    else:
        with pytest.raises(ApiError) as exc:
            asyncio.run(QwenGateway().health())
        assert exc.value.code == expected
