"""Тикет 02: конвейер — этапы, взятие в работу, передача, сроки, внутренняя история.

Что проверяется помимо самой логики: клиентская сторона не изменилась ни одним полем,
а в чужих ручках сотрудника тела функций остались нетронутыми.
"""

import ast
import json
import pathlib

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.enums import Status
from app.models import Application, InfoRequest, utcnow
from app.staff_pipeline.enums import PipelineEventType, PipelineStage
from app.staff_pipeline.models import (
    ApplicationPipeline,
    PipelineEvent,
    PipelineHistoryIsAppendOnly,
)
from tests.conftest import Api, company_id, submitted

BACKEND = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = BACKEND.parents[0] / "docs" / "api-examples"


@pytest.fixture
def verifier(client):
    return Api(client, "verifier")


@pytest.fixture
def underwriter(client):
    return Api(client, "underwriter")


def pipeline_card(api: Api, app_id: int) -> dict:
    r = api.get(f"/staff/applications/{app_id}/pipeline")
    assert r.status_code == 200, r.text
    return r.json()


def error_of(response) -> tuple[int, str, str]:
    body = response.json()["error"]
    return response.status_code, body["code"], body["message"]


def history_types(api: Api, app_id: int) -> list[str]:
    return [e["type"] for e in pipeline_card(api, app_id)["history"]]


def shift_submitted(app_id: int, hours: int) -> None:
    """Сдвигает время подачи в прошлое — так проверяются нормативы без ожидания в тесте."""
    with SessionLocal() as db:
        app = db.get(Application, app_id)
        app.submitted_at = utcnow() - __import__("datetime").timedelta(hours=hours)
        app.created_at = app.submitted_at
        db.commit()


def claimed_by_verifier(verifier: Api, app_id: int) -> dict:
    r = verifier.post(f"/staff/applications/{app_id}/claim")
    assert r.status_code == 200, r.text
    return r.json()


def at_underwriting(verifier: Api, app_id: int) -> None:
    """Проводит заявку через верификацию: взять в работу и передать дальше."""
    claimed_by_verifier(verifier, app_id)
    r = verifier.post(f"/staff/applications/{app_id}/pass-to-underwriting",
                      {"comment": "Анкета полная, проверки пройдены"})
    assert r.status_code == 200, r.text


# ---------- приём в конвейер ----------

def test_application_is_accepted_to_pipeline_on_first_appearance(alexey, verifier):
    app = submitted(alexey, company_id(alexey, "ИП"))
    with SessionLocal() as db:
        assert db.get(ApplicationPipeline, app["id"]) is None, "до появления у сотрудника конвейера нет"

    queue = verifier.get("/staff/queue").json()
    assert [i["id"] for i in queue["items"]] == [app["id"]]
    block = queue["items"][0]["pipeline"]
    assert block["stage"] == PipelineStage.VERIFICATION and block["assignee"] is None
    assert block["claimable"] is True and block["is_mine"] is False

    card = pipeline_card(verifier, app["id"])
    assert card["history"][0]["type"] == PipelineEventType.ACCEPTED_TO_PIPELINE
    assert card["history"][0]["actor_name"] == "Система"
    assert card["history"][0]["label"] == "Заявка принята в обработку"


def test_existing_staff_queue_also_accepts_applications_to_pipeline(alexey, staff):
    app = submitted(alexey, company_id(alexey, "ИП"))
    assert staff.get("/staff/applications").status_code == 200
    with SessionLocal() as db:
        pl = db.get(ApplicationPipeline, app["id"])
        assert pl is not None and pl.stage == PipelineStage.VERIFICATION


# ---------- очередь: срезы, сроки, просрочка ----------

def test_queue_is_filtered_by_scopes_with_counts(alexey, verifier):
    ip = submitted(alexey, company_id(alexey, "ИП"))
    mayak = submitted(alexey, company_id(alexey, "Маяк"))
    vector = submitted(alexey, company_id(alexey, "Вектор"))
    shift_submitted(vector["id"], hours=10)  # норматив верификации — 4 часа
    claimed_by_verifier(verifier, ip["id"])

    counts = verifier.get("/staff/queue").json()["counts"]
    assert counts == {"free": 2, "mine": 1, "overdue": 1, "all": 3}

    def ids(scope):
        return {i["id"] for i in verifier.get("/staff/queue", params={"scope": scope}).json()["items"]}

    assert ids("free") == {mayak["id"], vector["id"]}
    assert ids("mine") == {ip["id"]}
    assert ids("overdue") == {vector["id"]}
    assert ids("all") == {ip["id"], mayak["id"], vector["id"]}
    # просроченные идут первыми: очередь отсортирована по остатку времени
    assert verifier.get("/staff/queue", params={"scope": "all"}).json()["items"][0]["id"] == vector["id"]


def test_queue_is_filtered_by_stage_and_search(alexey, verifier):
    ip = submitted(alexey, company_id(alexey, "ИП"))
    mayak = submitted(alexey, company_id(alexey, "Маяк"))
    at_underwriting(verifier, mayak["id"])

    by_stage = verifier.get("/staff/queue", params={"scope": "all", "stage": "UNDERWRITING"}).json()
    assert [i["id"] for i in by_stage["items"]] == [mayak["id"]]
    found = verifier.get("/staff/queue", params={"scope": "all", "q": ip["number"]}).json()
    assert [i["id"] for i in found["items"]] == [ip["id"]]
    assert verifier.get("/staff/queue", params={"scope": "all", "q": "нет такой"}).json()["items"] == []
    assert verifier.get("/staff/queue", params={"scope": "unknown"}).status_code == 422


def test_deadline_and_overdue_are_visible_in_queue_and_card(alexey, verifier):
    app = submitted(alexey, company_id(alexey, "ИП"))
    shift_submitted(app["id"], hours=6)
    item = verifier.get("/staff/queue").json()["items"][0]["pipeline"]
    assert item["stage_limit_hours"] == 4
    assert item["deadline_at"] and item["stage_entered_at"]
    assert -180 <= item["time_left_minutes"] <= -110 and item["is_overdue"] is True

    card = pipeline_card(verifier, app["id"])
    assert card["is_overdue"] is True and card["time_left_minutes"] == item["time_left_minutes"]
    assert card["waiting_for_client"] is False and card["waiting_minutes_total"] == 0


def test_underwriting_has_its_own_norm(alexey, verifier):
    app = submitted(alexey, company_id(alexey, "ИП"))
    shift_submitted(app["id"], hours=6)
    at_underwriting(verifier, app["id"])
    card = pipeline_card(verifier, app["id"])
    assert card["stage"] == PipelineStage.UNDERWRITING and card["stage_limit_hours"] == 24
    # отсчёт нового этапа начинается заново, просрочка верификации на него не переносится
    assert card["is_overdue"] is False and card["time_left_minutes"] > 23 * 60


# ---------- взятие в работу ----------

def test_free_application_can_be_claimed_and_taken_one_is_refused(alexey, verifier, underwriter, staff):
    app = submitted(alexey, company_id(alexey, "ИП"))
    at_underwriting(verifier, app["id"])

    card = underwriter.post(f"/staff/applications/{app['id']}/claim").json()
    assert card["assignee"]["full_name"] == "Сергей Гущин"
    assert card["assignee"]["staff_role"] == "UNDERWRITER" and card["is_mine"] is True
    assert PipelineEventType.CLAIMED in history_types(underwriter, app["id"])

    status, code, message = error_of(staff.post(f"/staff/applications/{app['id']}/claim"))
    assert (status, code) == (409, "ALREADY_CLAIMED") and "Сергей Гущин" in message
    # и решение по занятой заявке другой сотрудник вынести не может
    status, code, message = error_of(staff.post(f"/staff/applications/{app['id']}/approve", {"comment": "Одобряю"}))
    assert (status, code) == (409, "ALREADY_CLAIMED") and "Сергей Гущин" in message
    assert alexey.get(f"/applications/{app['id']}").json()["status"] == Status.IN_REVIEW


def test_claim_is_refused_on_another_role_stage(alexey, verifier, underwriter):
    app = submitted(alexey, company_id(alexey, "ИП"))
    status, code, message = error_of(underwriter.post(f"/staff/applications/{app['id']}/claim"))
    assert (status, code) == (403, "STAGE_FORBIDDEN") and "верификатор" in message
    assert verifier.get("/staff/queue").json()["items"][0]["pipeline"]["claimable"] is True


def test_claimed_application_can_be_released_back_to_the_queue(alexey, verifier):
    app = submitted(alexey, company_id(alexey, "ИП"))
    claimed_by_verifier(verifier, app["id"])
    card = verifier.post(f"/staff/applications/{app['id']}/release", {"comment": "Передаю смене"}).json()
    assert card["assignee"] is None and card["is_mine"] is False
    assert card["history"][-1]["type"] == PipelineEventType.RELEASED
    assert card["history"][-1]["comment"] == "Передаю смене"
    assert verifier.get("/staff/queue").json()["counts"] == {"free": 1, "mine": 0, "overdue": 0, "all": 1}
    status, code, _ = error_of(verifier.post(f"/staff/applications/{app['id']}/release"))
    assert (status, code) == (409, "NOT_ASSIGNED")


# ---------- права этапов ----------

def test_verifier_requests_info_and_passes_application_to_underwriting(alexey, verifier):
    app = submitted(alexey, company_id(alexey, "ИП"))
    claimed_by_verifier(verifier, app["id"])
    r = verifier.post(f"/staff/applications/{app['id']}/request-info",
                      {"message": "Подтвердите выручку", "requested_fields": ["monthly_revenue"]})
    assert r.status_code == 200 and r.json()["status"] == Status.NEED_INFO

    card = pipeline_card(verifier, app["id"])
    assert card["waiting_for_client"] is True and card["is_overdue"] is False
    requested = next(e for e in card["history"] if e["type"] == PipelineEventType.INFO_REQUESTED)
    assert requested["comment"] == "Подтвердите выручку"
    assert requested["actor_staff_role"] == "VERIFIER" and requested["payload"]["fields"] == ["monthly_revenue"]

    alexey.post(f"/applications/{app['id']}/info-response",
                {"answer_text": "Выросла", "fields": {"monthly_revenue": 2_000_000}})
    passed = verifier.post(f"/staff/applications/{app['id']}/pass-to-underwriting",
                           {"comment": "Сведения получены"}).json()
    assert passed["stage"] == PipelineStage.UNDERWRITING and passed["assignee"] is None
    assert passed["history"][-1]["type"] == PipelineEventType.PASSED_TO_UNDERWRITING
    assert passed["history"][-1]["comment"] == "Сведения получены"


def test_verifier_cannot_decide(alexey, verifier):
    app = submitted(alexey, company_id(alexey, "ИП"))
    claimed_by_verifier(verifier, app["id"])
    calls = {
        "approve": {"comment": "Одобряю"},
        "counter-offer": {"amount": 800_000, "term_months": 18, "rate": 19.5, "comment": "Снизили"},
        "reject": {"reason_code": "LOW_RATING"},
    }
    for action, body in calls.items():
        status, code, message = error_of(verifier.post(f"/staff/applications/{app['id']}/{action}", body))
        assert (status, code) == (403, "STAGE_FORBIDDEN"), action
        assert "андеррайтер" in message, action
    assert alexey.get(f"/applications/{app['id']}").json()["status"] == Status.IN_REVIEW
    assert "approve" not in pipeline_card(verifier, app["id"])["available_actions"]


def test_underwriter_cannot_decide_before_verification(alexey, underwriter):
    app = submitted(alexey, company_id(alexey, "ИП"))
    status, code, message = error_of(underwriter.post(f"/staff/applications/{app['id']}/approve", {"comment": "Одобряю"}))
    assert (status, code) == (409, "WRONG_STAGE") and "верификацию" in message


def test_underwriter_cannot_decide_without_claiming(alexey, verifier, underwriter):
    app = submitted(alexey, company_id(alexey, "ИП"))
    at_underwriting(verifier, app["id"])
    status, code, message = error_of(underwriter.post(f"/staff/applications/{app['id']}/approve", {"comment": "Одобряю"}))
    assert (status, code) == (409, "NOT_ASSIGNED") and "возьмите заявку в работу" in message

    underwriter.post(f"/staff/applications/{app['id']}/claim")
    assert underwriter.post(f"/staff/applications/{app['id']}/approve", {"comment": "Одобряю"}).status_code == 200
    card = pipeline_card(underwriter, app["id"])
    assert card["stage"] == PipelineStage.DONE and card["available_actions"] == []
    decision = card["history"][-1]
    assert decision["type"] == PipelineEventType.DECISION_MADE
    assert decision["payload"]["action"] == "approve" and decision["actor_name"] == "Сергей Гущин"


def test_available_actions_match_the_server_rules(alexey, verifier, underwriter):
    app = submitted(alexey, company_id(alexey, "ИП"))
    assert pipeline_card(verifier, app["id"])["available_actions"] == ["claim"]
    assert pipeline_card(underwriter, app["id"])["available_actions"] == []
    claimed_by_verifier(verifier, app["id"])
    assert pipeline_card(verifier, app["id"])["available_actions"] == [
        "release", "request_info", "pass_to_underwriting"]
    verifier.post(f"/staff/applications/{app['id']}/pass-to-underwriting")
    assert pipeline_card(underwriter, app["id"])["available_actions"] == ["claim"]
    underwriter.post(f"/staff/applications/{app['id']}/claim")
    assert pipeline_card(underwriter, app["id"])["available_actions"] == [
        "release", "request_info", "approve", "counter_offer", "reject"]
    assert pipeline_card(verifier, app["id"])["available_actions"] == [], "чужую заявку не тронуть"


# ---------- ожидание ответа клиента ----------

def test_client_answer_returns_application_to_the_stage_it_left(alexey, verifier, underwriter):
    app = submitted(alexey, company_id(alexey, "ИП"))
    at_underwriting(verifier, app["id"])
    underwriter.post(f"/staff/applications/{app['id']}/claim")
    underwriter.post(f"/staff/applications/{app['id']}/request-info",
                     {"message": "Нужна выручка", "requested_fields": ["monthly_revenue"]})
    assert pipeline_card(underwriter, app["id"])["stage"] == PipelineStage.UNDERWRITING

    alexey.post(f"/applications/{app['id']}/info-response",
                {"answer_text": "Вот", "fields": {"monthly_revenue": 2_500_000}})
    card = pipeline_card(underwriter, app["id"])
    # заявка вернулась на андеррайтинг, а не в начало конвейера
    assert card["stage"] == PipelineStage.UNDERWRITING and card["waiting_for_client"] is False
    assert card["is_mine"] is True
    assert history_types(underwriter, app["id"]).count(PipelineEventType.INFO_PROVIDED) == 1
    assert PipelineEventType.RETURNED_TO_VERIFICATION not in history_types(underwriter, app["id"])


def test_waiting_for_client_does_not_make_application_overdue(alexey, verifier):
    app = submitted(alexey, company_id(alexey, "ИП"))
    claimed_by_verifier(verifier, app["id"])
    verifier.post(f"/staff/applications/{app['id']}/request-info",
                  {"message": "Подтвердите выручку", "requested_fields": ["monthly_revenue"]})
    # заявка подана 50 часов назад и 48 часов ждёт клиента — норматив этапа 4 часа
    import datetime as dt
    with SessionLocal() as db:
        now = utcnow()
        a = db.get(Application, app["id"])
        a.submitted_at = now - dt.timedelta(hours=50)
        request = db.scalar(select(InfoRequest).where(InfoRequest.application_id == app["id"]))
        request.created_at = now - dt.timedelta(hours=48)
        pl = db.get(ApplicationPipeline, app["id"])
        pl.stage_entered_at = now - dt.timedelta(hours=50)
        pl.waiting_since = now - dt.timedelta(hours=48)
        db.commit()

    card = pipeline_card(verifier, app["id"])
    assert card["waiting_for_client"] is True and card["is_overdue"] is False
    assert 110 <= card["time_left_minutes"] <= 121, "в норматив идут только 2 часа до запроса"
    assert verifier.get("/staff/queue", params={"scope": "overdue"}).json()["items"] == []

    alexey.post(f"/applications/{app['id']}/info-response",
                {"answer_text": "Подтверждаю", "fields": {"monthly_revenue": 2_100_000}})
    after = pipeline_card(verifier, app["id"])
    assert after["waiting_for_client"] is False and after["is_overdue"] is False
    assert after["waiting_minutes_total"] >= 48 * 60
    assert 110 <= after["time_left_minutes"] <= 121, "48 часов ожидания в норматив не вошли"


def test_client_supplement_after_decision_returns_application_to_verification(alexey, verifier, underwriter):
    app = submitted(alexey, company_id(alexey, "ИП"))
    at_underwriting(verifier, app["id"])
    underwriter.post(f"/staff/applications/{app['id']}/claim")
    underwriter.post(f"/staff/applications/{app['id']}/counter-offer",
                     {"amount": 800_000, "term_months": 18, "rate": 19.5, "comment": "Снизили сумму"})
    assert pipeline_card(underwriter, app["id"])["stage"] == PipelineStage.DONE

    alexey.post(f"/applications/{app['id']}/supplement",
                {"answer_text": "Добавлю выручку", "fields": {"monthly_revenue": 3_000_000}})
    card = pipeline_card(verifier, app["id"])
    assert card["stage"] == PipelineStage.VERIFICATION and card["assignee"] is None
    assert card["history"][-1]["type"] == PipelineEventType.RETURNED_TO_VERIFICATION


# ---------- внутренняя история ----------

def test_internal_history_is_never_in_the_client_response(alexey, verifier):
    app = submitted(alexey, company_id(alexey, "ИП"))
    claimed_by_verifier(verifier, app["id"])
    verifier.post(f"/staff/applications/{app['id']}/request-info",
                  {"message": "Подтвердите выручку", "requested_fields": ["monthly_revenue"]})

    client_view = alexey.get(f"/applications/{app['id']}")
    assert not {"history", "pipeline", "stage_entered_at", "assignee"} & set(client_view.json())
    for marker in ("ACCEPTED_TO_PIPELINE", "CLAIMED", "VERIFICATION", "Наталья Белова"):
        assert marker not in client_view.text, marker
    assert alexey.get(f"/staff/applications/{app['id']}/pipeline").status_code == 403

    staff_card = verifier.get(f"/staff/applications/{app['id']}").json()
    assert "history" not in staff_card, "внутренняя история отдаётся отдельной ручкой"
    assert len(pipeline_card(verifier, app["id"])["history"]) == 3


def test_history_records_cannot_be_edited_or_deleted(alexey, verifier):
    app = submitted(alexey, company_id(alexey, "ИП"))
    claimed_by_verifier(verifier, app["id"])
    with SessionLocal() as db:
        event = db.scalars(select(PipelineEvent).where(
            PipelineEvent.application_id == app["id"])).first()
        event.comment = "переписанная история"
        with pytest.raises(PipelineHistoryIsAppendOnly):
            db.commit()
        db.rollback()
    with SessionLocal() as db:
        event = db.scalars(select(PipelineEvent).where(
            PipelineEvent.application_id == app["id"])).first()
        db.delete(event)
        with pytest.raises(PipelineHistoryIsAppendOnly):
            db.commit()
        db.rollback()
    assert len(pipeline_card(verifier, app["id"])["history"]) == 2


# ---------- прежняя учётная запись сотрудника ----------

def test_existing_staff_account_keeps_the_previous_behaviour(alexey, staff):
    """Контракт: поведение прежней учётной записи не меняется."""
    assert staff.get("/staff/me").json()["department"]["pipeline_enforced"] is False
    app = submitted(alexey, company_id(alexey, "ИП"))
    # ни взятия в работу, ни верификации не требуется — как было до отдела
    assert staff.post(f"/staff/applications/{app['id']}/request-info",
                      {"message": "Уточните выручку", "requested_fields": ["monthly_revenue"]}).status_code == 200
    alexey.post(f"/applications/{app['id']}/info-response",
                {"answer_text": "Вот", "fields": {"monthly_revenue": 2_000_000}})
    assert staff.post(f"/staff/applications/{app['id']}/approve", {"comment": "Всё в порядке"}).status_code == 200
    # при этом её действия тоже попадают во внутреннюю историю
    assert history_types(staff, app["id"]) == [
        PipelineEventType.ACCEPTED_TO_PIPELINE, PipelineEventType.INFO_REQUESTED,
        PipelineEventType.INFO_PROVIDED, PipelineEventType.DECISION_MADE]


# ---------- клиентская сторона и чужие файлы ----------

def _skeleton(value):
    """Структура ответа без значений: имена полей и вложенность."""
    if isinstance(value, dict):
        return {k: _skeleton(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_skeleton(value[0])] if value else []
    return None


@pytest.mark.parametrize("example,status", [
    ("application_submitted", Status.IN_REVIEW),
    ("application_need_info", Status.NEED_INFO),
])
def test_client_application_response_did_not_change(alexey, staff, example, status):
    """Сверка с примерами ответов, записанными до наших работ."""
    app = submitted(alexey, company_id(alexey, "ИП"))
    if status == Status.NEED_INFO:
        staff.post(f"/staff/applications/{app['id']}/request-info",
                   {"message": "Уточните выручку", "requested_fields": ["monthly_revenue"]})
    current = alexey.get(f"/applications/{app['id']}").json()
    recorded = json.loads((EXAMPLES / f"{example}.json").read_text(encoding="utf-8"))
    assert current["status"] == status
    assert _skeleton(current) == _skeleton(recorded)


def test_staff_endpoints_changed_only_in_signatures():
    """Проверки врезаны зависимостями: тела чужих функций нас не знают."""
    source = (BACKEND / "app" / "api" / "staff.py").read_text(encoding="utf-8")
    assert source.count("from app.staff_pipeline import deps as pipeline_deps") == 1
    assert source.count("Depends(pipeline_deps.") == 6

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        used = {n.id for n in ast.walk(ast.Module(body=node.body, type_ignores=[]))
                if isinstance(n, ast.Name)}
        assert "pipeline_deps" not in used, f"тело {node.name} ссылается на наш модуль"


def test_no_background_tasks_or_schedulers_added():
    """Проект по-прежнему поднимается одной командой: сроки считаются в момент запроса."""
    requirements = (BACKEND / "requirements.txt").read_text(encoding="utf-8").lower()
    for library in ("apscheduler", "celery", "rq", "arq", "huey", "redis"):
        assert library not in requirements, library
    for module in sorted((BACKEND / "app" / "staff_pipeline").glob("*.py")):
        source = module.read_text(encoding="utf-8")
        for marker in ("threading", "asyncio.create_task", "BackgroundTasks", "subprocess"):
            assert marker not in source, f"{module.name}: {marker}"
