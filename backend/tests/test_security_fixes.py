"""Проверки трёх правок безопасности: демо-операции, серверная валидация, гонка заявок.

Интерфейс ограничивает корректный путь, поэтому здесь запросы идут прямо к API —
мимо интерфейса, как это сделал бы человек с curl.
"""

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.db import SessionLocal
from app.enums import BorrowingMode, Status
from app.models import Application
from app.services import applications as svc
from tests.conftest import PROFILE, company_id, submitted


def fields_of(response):
    return response.json()["error"]["fields"]


def profile_of(staff, application_id: int) -> dict:
    return staff.get(f"/staff/applications/{application_id}").json()["business_profile"]


# ---------- пункт 2: анкета проверяется на сервере ----------

def test_info_response_cannot_leave_profile_incomplete(alexey, staff):
    """Ответ на запрос банка не может стереть поле, которого банк не спрашивал."""
    aid = submitted(alexey, company_id(alexey, "ИП"))["id"]
    assert staff.post(f"/staff/applications/{aid}/request-info", {
        "message": "Уточните выручку", "requested_fields": ["monthly_revenue"],
    }).status_code == 200

    bad = alexey.post(f"/applications/{aid}/info-response", {
        "answer_text": "Выручка выросла", "fields": {"monthly_revenue": 2_000_000, "industry": "   "},
    })
    assert bad.status_code == 422
    assert fields_of(bad) == {"fields.industry": "Обязательное поле"}

    # предыдущая корректная версия сохранена: ни отрасль, ни выручка не записаны
    kept = profile_of(staff, aid)
    assert kept["industry"] == PROFILE["industry"]
    assert kept["monthly_revenue"] == PROFILE["monthly_revenue"]
    card = staff.get(f"/staff/applications/{aid}").json()
    assert card["status"] == Status.NEED_INFO
    assert card["info_requests"][-1]["answered_at"] is None

    good = alexey.post(f"/applications/{aid}/info-response", {
        "answer_text": "Выручка выросла", "fields": {"monthly_revenue": 2_000_000},
    })
    assert good.status_code == 200 and good.json()["status"] == Status.IN_REVIEW


def test_supplement_cannot_leave_profile_incomplete(alexey, staff):
    """«Вернуться к заявке» с пустым полем не аннулирует предложение банка."""
    aid = submitted(alexey, company_id(alexey, "ИП"))["id"]
    assert staff.post(f"/staff/applications/{aid}/counter-offer", {
        "amount": 800_000, "term_months": 18, "rate": 19.5, "comment": "Снизили сумму",
    }).status_code == 200

    bad = alexey.post(f"/applications/{aid}/supplement", {
        "answer_text": "Готов обсудить", "fields": {"purpose_details": ""},
    })
    assert bad.status_code == 422
    assert fields_of(bad) == {"fields.purpose_details": "Обязательное поле"}

    view = alexey.get(f"/applications/{aid}").json()
    assert view["status"] == Status.COUNTER_OFFER and view["decision"] is not None
    assert profile_of(staff, aid)["purpose_details"] == PROFILE["purpose_details"]


@pytest.mark.parametrize("action,body", [
    ("approve", {"comment": "Одобряю"}),
    ("counter-offer", {"amount": 800_000, "term_months": 18, "rate": 19.5, "comment": "Снизили сумму"}),
])
def test_staff_cannot_decide_on_incomplete_profile(alexey, staff, action, body):
    """Если анкета всё же оказалась неполной, положительное решение сервер не пропускает."""
    aid = submitted(alexey, company_id(alexey, "ИП"))["id"]
    with SessionLocal() as db:
        item = db.get(Application, aid)
        item.business_profile = {**PROFILE, "monthly_revenue": None}
        db.commit()

    response = staff.post(f"/staff/applications/{aid}/{action}", body)
    assert response.status_code == 422
    assert fields_of(response) == {"business_profile.monthly_revenue": "Обязательное поле"}
    assert "запросите сведения" in response.json()["error"]["message"]

    card = staff.get(f"/staff/applications/{aid}").json()
    assert card["status"] == Status.IN_REVIEW and card["decisions"] == []
    assert alexey.get(f"/applications/{aid}").json()["decision"] is None

    # отказать по неполной анкете по-прежнему можно: именно для этого причина и есть
    assert staff.post(f"/staff/applications/{aid}/reject", {"reason_code": "INSUFFICIENT_DATA"}).status_code == 200


def test_approve_requires_reason(alexey, staff):
    """Причина одобрения обязательна и на API, а не только в интерфейсе."""
    aid = submitted(alexey, company_id(alexey, "ИП"))["id"]
    without = staff.post(f"/staff/applications/{aid}/approve", {})
    assert without.status_code == 422 and "comment" in fields_of(without)
    blank = staff.post(f"/staff/applications/{aid}/approve", {"comment": "   "})
    assert blank.status_code == 422 and fields_of(blank) == {"comment": "Укажите причину одобрения"}

    card = staff.get(f"/staff/applications/{aid}").json()
    assert card["status"] == Status.IN_REVIEW and card["decisions"] == []
    assert not [e for e in card["events"] if e["type"] == "APPROVED"]

    ok = staff.post(f"/staff/applications/{aid}/approve", {"comment": "Показатели в норме"})
    assert ok.status_code == 200 and ok.json()["decision"]["comment"] == "Показатели в норме"


# ---------- пункт 3: активная заявка одна ----------

def test_database_refuses_second_active_application(alexey):
    """Правило «одна активная заявка на способ займа» закреплено индексом, а не только кодом."""
    cid = company_id(alexey, "ИП")
    assert alexey.post(f"/companies/{cid}/applications", {"borrowing_mode": "NEW_CREDIT"}).status_code == 201

    def add(status: str) -> None:
        with SessionLocal() as db:
            db.add(Application(company_id=cid, borrowing_mode=BorrowingMode.NEW_CREDIT, term_months=12,
                               business_profile={}, status=status))
            db.commit()

    with pytest.raises(IntegrityError):
        add(Status.DRAFT)
    # завершённые и отклонённые заявки под правило не попадают
    add(Status.REJECTED)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Application)) == 2


def test_parallel_create_keeps_one_application(alexey, monkeypatch):
    """Второй одновременный запрос получает тот же черновик, а не свой собственный."""
    cid = company_id(alexey, "ИП")
    first = alexey.post(f"/companies/{cid}/applications", {"borrowing_mode": "NEW_CREDIT"})
    assert first.status_code == 201

    real, seen = svc.active_application, []

    def blind_once(db, company_id_, mode):
        """Повторяет гонку: второй запрос ещё не видит черновик первого."""
        if not seen:
            seen.append(1)
            return None
        return real(db, company_id_, mode)

    monkeypatch.setattr(svc, "active_application", blind_once)
    second = alexey.post(f"/companies/{cid}/applications", {"borrowing_mode": "NEW_CREDIT"})
    assert second.status_code == 200 and second.json()["id"] == first.json()["id"]
    assert seen, "гонка не воспроизвелась"

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Application)) == 1


def test_accept_twice_keeps_one_history_record(alexey, staff):
    """Повторное принятие предложения не создаёт второй записи в истории."""
    aid = submitted(alexey, company_id(alexey, "ИП"))["id"]
    assert staff.post(f"/staff/applications/{aid}/approve", {"comment": "Показатели в норме"}).status_code == 200
    assert alexey.post(f"/applications/{aid}/accept").status_code == 200
    again = alexey.post(f"/applications/{aid}/accept")
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_ACCEPTED"

    view = alexey.get(f"/applications/{aid}").json()
    assert view["status"] == Status.COMPLETED
    assert len([e for e in view["events"] if e["type"] == "ACCEPTED"]) == 1
