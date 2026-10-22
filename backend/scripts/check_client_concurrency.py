"""Конкурентный HTTP-прогон клиентского пути на отдельном PostgreSQL-стенде, без reset.

Проверяет три гонки, которые нельзя воспроизвести на SQLite (нет настоящих блокировок):

1. два одновременных создания заявки (две вкладки, двойной клик) — остаётся одна заявка;
2. две одновременные отправки одного черновика — один переход и одна запись в истории;
3. два одновременных принятия предложения — одно принятие и одна запись в истории.

Скрипт создаёт себе отдельную компанию и ничего не сбрасывает. Запуск:
    python -m scripts.check_client_concurrency --isolated --base http://frontend
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json

import httpx
from sqlalchemy import func, select

from app.main import app  # noqa: F401
from app.core.db import SessionLocal, engine
from app.enums import ACTIVE_STATUSES, EventType, Status
from app.models import Application, ApplicationEvent

PROFILE = {"industry": "Оптовая торговля", "months_operating": 36, "monthly_revenue": 1_800_000,
           "monthly_debt_payments": 120_000, "purpose_details": "Проверка одновременных запросов"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolated", required=True, action="store_true",
                        help="подтверждение: стенд отдельный, не общий сервер")
    parser.add_argument("--base", default="http://frontend")
    parser.add_argument("--client", default="alexey")
    parser.add_argument("--staff", default="staff")
    args = parser.parse_args()
    assert engine.dialect.name == "postgresql", "Эта проверка требует настоящие блокировки PostgreSQL"

    def login(name):
        r = httpx.post(args.base + "/api/auth/login", json={"login": name, "password": "demo"})
        r.raise_for_status()
        return {"Authorization": "Bearer " + r.json()["token"]}

    client, staff = login(args.client), login(args.staff)

    created = httpx.post(args.base + "/api/companies", headers=client, json={
        "legal_form": "OOO", "name": "ООО «Гонка клиента»", "registration_number": "3999999999999"})
    created.raise_for_status()
    cid = created.json()["id"]

    def race(count, method, url, headers, body=None):
        def call(_):
            return httpx.request(method, args.base + url, headers=headers, json=body, timeout=30)
        with ThreadPoolExecutor(max_workers=count) as pool:
            return list(pool.map(call, range(count)))

    # 1. создание заявки
    creations = race(2, "POST", f"/api/companies/{cid}/applications", client,
                     {"borrowing_mode": "NEW_CREDIT"})
    assert all(r.status_code in (200, 201) for r in creations), [r.text for r in creations]
    ids = {r.json()["id"] for r in creations}
    assert len(ids) == 1, [r.json() for r in creations]
    aid = ids.pop()
    with SessionLocal() as db:
        active = db.scalar(select(func.count()).select_from(Application).where(
            Application.company_id == cid, Application.status.in_(ACTIVE_STATUSES)))
        assert active == 1, f"активных заявок {active}, ожидалась одна"

    # 2. отправка заявки
    filled = httpx.patch(args.base + f"/api/applications/{aid}", headers=client,
                         json={"product_id": "WORKING_CAPITAL", "amount": 900_000,
                               "term_months": 18, "business_profile": PROFILE})
    filled.raise_for_status()
    submits = race(2, "POST", f"/api/applications/{aid}/submit", client, {"confirm_data": True})
    assert sorted(r.status_code for r in submits) == [200, 409], [r.text for r in submits]

    def events(type_: EventType) -> int:
        with SessionLocal() as db:
            return db.scalar(select(func.count()).select_from(ApplicationEvent).where(
                ApplicationEvent.application_id == aid, ApplicationEvent.type == type_))

    assert events(EventType.SUBMITTED) == 1, "в истории два события отправки"

    # 3. принятие предложения
    approved = httpx.post(args.base + f"/api/staff/applications/{aid}/approve", headers=staff,
                          json={"comment": "Проверка одновременных запросов"})
    assert approved.status_code == 200, approved.text
    accepts = race(2, "POST", f"/api/applications/{aid}/accept", client)
    assert sorted(r.status_code for r in accepts) == [200, 409], [r.text for r in accepts]
    assert events(EventType.ACCEPTED) == 1, "в истории два события принятия"
    with SessionLocal() as db:
        assert db.get(Application, aid).status == Status.COMPLETED

    print(json.dumps({"result": "PASS", "database": "PostgreSQL", "company_id": cid,
                      "application_id": aid,
                      "create": sorted(r.status_code for r in creations),
                      "submit": sorted(r.status_code for r in submits),
                      "accept": sorted(r.status_code for r in accepts),
                      "active_applications": 1, "submitted_events": 1, "accepted_events": 1},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
