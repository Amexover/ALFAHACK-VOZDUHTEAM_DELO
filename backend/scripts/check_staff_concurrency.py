"""Конкурентный HTTP-прогон на отдельном PostgreSQL-стенде, без reset."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json

import httpx
from sqlalchemy import select

from app.main import app  # noqa: F401
from app.core.db import SessionLocal, engine
from app.core.security import hash_password
from app.enums import BorrowingMode, DecisionKind, LegalForm, Role, Status
from app.models import Application, BureauRating, Company, Decision, User, utcnow
from app.staff_pipeline.enums import StaffRole
from app.staff_pipeline.models import PipelineEvent, ScoreSnapshot, StaffProfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolated", required=True, action="store_true")
    parser.add_argument("--base", default="http://frontend")
    args = parser.parse_args()
    assert engine.dialect.name == "postgresql", "Эта проверка требует настоящие блокировки PostgreSQL"
    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.login == "alexey"))
        for login in ("t4-race-a", "t4-race-b"):
            user = db.scalar(select(User).where(User.login == login))
            if user is None:
                user = User(login=login, password_hash=hash_password("demo"),
                            full_name=login, first_name=login, role=Role.EMPLOYEE)
                db.add(user)
                db.flush()
                db.add(StaffProfile(user_id=user.id, staff_role=StaffRole.UNDERWRITER, pipeline_enforced=True))
        company = Company(owner_id=owner.id, legal_form=LegalForm.OOO,
                          name="ООО «Конкурентная приёмка Т4»", ogrn="3888888888888")
        db.add(company)
        db.flush()
        db.add(BureauRating(company_id=company.id, score=299, updated_at=utcnow()))
        item = Application(company_id=company.id, borrowing_mode=BorrowingMode.NEW_CREDIT,
                           product_id="WORKING_CAPITAL", amount=900000, term_months=18,
                           preliminary_rate=30, preliminary_payment=62703,
                           business_profile={"industry": "Торговля", "months_operating": 36,
                                             "monthly_revenue": 100000, "monthly_debt_payments": 100001,
                                             "purpose_details": "Проверка гонки"},
                           status=Status.IN_REVIEW, submitted_at=utcnow())
        db.add(item)
        db.flush()
        aid = item.id
        item.number = f"T4-RACE-{aid}"
        db.commit()

    def login(name):
        r = httpx.post(args.base + "/api/auth/login", json={"login": name, "password": "demo"})
        r.raise_for_status()
        return {"Authorization": "Bearer " + r.json()["token"]}

    headers = [login("t4-race-a"), login("t4-race-b")]
    path = args.base + f"/api/staff/applications/{aid}"

    def race(method, endpoint, body=None):
        def call(h):
            return httpx.request(method, path + endpoint, headers=h, json=body, timeout=30)
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(call, headers))

    intake = race("GET", "/pipeline")
    assert [r.status_code for r in intake] == [200, 200], [r.text for r in intake]
    assert all(r.json()["auto_rejected"] for r in intake)
    with SessionLocal() as db:
        assert len(db.scalars(select(Decision).where(Decision.application_id == aid)).all()) == 1
        assert len(db.scalars(select(ScoreSnapshot).where(ScoreSnapshot.application_id == aid)).all()) == 2
        assert len(db.scalars(select(PipelineEvent).where(PipelineEvent.application_id == aid)).all()) == 2
    cancellation = race("POST", "/cancel-auto-reject", {"reason": "Конкурентный пересмотр"})
    assert sorted(r.status_code for r in cancellation) == [200, 409], [r.text for r in cancellation]
    decisions = race("POST", "/approve", {"comment": "Ручная проверка"})
    assert sorted(r.status_code for r in decisions) == [200, 409], [r.text for r in decisions]
    with SessionLocal() as db:
        active = db.scalars(select(Decision).where(Decision.application_id == aid, Decision.is_active.is_(True))).all()
        assert len(active) == 1 and active[0].kind == DecisionKind.APPROVED
        assert len(db.scalars(select(ScoreSnapshot).where(ScoreSnapshot.application_id == aid)).all()) == 3
    print(json.dumps({"result": "PASS", "database": "PostgreSQL", "application_id": aid,
                      "intake": [r.status_code for r in intake],
                      "cancel": sorted(r.status_code for r in cancellation),
                      "decision": sorted(r.status_code for r in decisions),
                      "active_decisions": 1, "snapshots": 3}))


if __name__ == "__main__":
    main()
