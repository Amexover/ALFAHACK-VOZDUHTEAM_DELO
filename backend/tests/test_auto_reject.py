"""Т4: узкая политика приёма, обратимость, права и клиентский контракт."""

import json

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.enums import Status
from app.models import Application, BureauRating, Company, Decision
from app.simulators import bureau
from app.staff_pipeline import auto_policy, scoring
from app.staff_pipeline.models import ApplicationPipeline, PipelineEvent, ScoreSnapshot
from app.staff_pipeline.seed import DEPARTMENT_APPLICATIONS, seed_department
from tests.conftest import Api, PROFILE, company_id, submitted


@pytest.fixture
def verifier(client):
    return Api(client, "verifier")


@pytest.fixture
def underwriter(client):
    return Api(client, "underwriter")


def risky(alexey):
    cid = company_id(alexey, "ИП")
    with SessionLocal() as db:
        db.get(BureauRating, cid).score = 299
        db.commit()
    return submitted(alexey, cid, business_profile={**PROFILE, "monthly_debt_payments": 2_000_000})


def card(api, aid):
    r = api.get(f"/staff/applications/{aid}/pipeline")
    assert r.status_code == 200, r.text
    return r.json()


def cancel(api, aid, **body):
    return api.post(f"/staff/applications/{aid}/cancel-auto-reject", body)


@pytest.mark.parametrize("score,load,incomplete,expected", [
    (299, 100.000001, False, True), (300, 101, False, False),
    (299, 100, False, False), (299, 99.999999, False, False),
    (0, 101, False, True), (None, 101, False, False),
    (299, None, False, False), (299, 101, True, False), (-1, 101, False, False),
])
def test_policy_boundaries(score, load, incomplete, expected):
    # Итоговый балл и рекомендация не участвуют в автоматической политике.
    assert auto_policy.matches({"facts": {"bureau_score": score, "debt_load_pct": load},
                                "data_incomplete": incomplete, "total_score": 100,
                                "recommendation": "APPROVE"}) is expected


@pytest.mark.parametrize("entry", ["/staff/queue", "/staff/applications", "pipeline", "card", "scoring"])
def test_intake_rejects_once_and_keeps_client_contract(alexey, underwriter, entry):
    app = risky(alexey)
    aid = app["id"]
    assert app["status"] == "IN_REVIEW"
    before_events = app["events"]
    url = {"pipeline": f"/staff/applications/{aid}/pipeline",
           "card": f"/staff/applications/{aid}",
           "scoring": f"/staff/applications/{aid}/scoring"}.get(entry, entry)
    assert underwriter.get(url).status_code == 200
    block = card(underwriter, aid)
    assert block["stage"] == "DONE" and block["auto_rejected"]
    assert block["assignee"] is None and block["time_left_minutes"] is None
    assert block["available_actions"] == ["cancel_auto_reject"]
    assert not underwriter.get("/staff/queue").json()["items"]
    for _ in range(2):
        assert underwriter.get(url).status_code == 200
    with SessionLocal() as db:
        decisions = db.scalars(select(Decision).where(Decision.application_id == aid)).all()
        snapshots = db.scalars(select(ScoreSnapshot).where(ScoreSnapshot.application_id == aid)).all()
        events = db.scalars(select(PipelineEvent).where(PipelineEvent.application_id == aid)).all()
        assert len(decisions) == 1 and decisions[0].is_active
        assert decisions[0].reject_reason_code == "LOW_RATING"
        assert [s.reason for s in snapshots] == ["ON_INTAKE", "ON_DECISION"]
        assert [e.type for e in events] == ["ACCEPTED_TO_PIPELINE", "AUTO_REJECTED"]
        payload = events[-1].payload
        assert payload["score_snapshot_id"] == snapshots[-1].id
        assert payload["ruleset_version"] == snapshots[-1].ruleset_version
        assert payload["policy_version"] == auto_policy.POLICY_VERSION
    client = alexey.get(f"/applications/{aid}").json()
    assert client["status"] == "REJECTED" and client["decision"]["reason_text"]
    assert client["events"] == before_events
    assert set(client) == set(app)
    serialized = json.dumps(client)
    for hidden in ("AUTO_REJECT", "LOW_RATING", "total_score", "ruleset_version", "pipeline"):
        assert hidden not in serialized


def test_cancel_requires_reason_and_underwriter_and_preserves_history(alexey, verifier, underwriter, client, monkeypatch):
    aid = risky(alexey)["id"]
    initial = card(underwriter, aid)
    assert "cancel_auto_reject" not in card(verifier, aid)["available_actions"]
    for body in ({}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 2001}, {"reason": "ok", "extra": 1}):
        assert cancel(underwriter, aid, **body).status_code == 422
    assert cancel(verifier, aid, reason="Проверено").status_code == 403
    assert cancel(alexey, aid, reason="Проверено").status_code == 403
    assert client.post(f"/api/staff/applications/{aid}/cancel-auto-reject", json={"reason": "ok"}).status_code == 401
    assert card(underwriter, aid) == initial
    frozen = underwriter.get(f"/staff/applications/{aid}/scoring").json()
    monkeypatch.setattr(scoring, "RULESET_VERSION", "RS-next")
    assert underwriter.get(f"/staff/applications/{aid}/scoring").json() == frozen
    reason = "  Проверили подтверждение выручки  "
    result = cancel(underwriter, aid, reason=reason)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["status"] == "IN_REVIEW" and data["reason"] == reason.strip()
    assert not data["cancelled_decision"]["is_active"]
    pl = data["pipeline"]
    assert pl["stage"] == "UNDERWRITING" and not pl["auto_rejected"] and pl["is_mine"]
    assert pl["assignee"]["staff_role"] == "UNDERWRITER"
    assert pl["history"][:-1] == initial["history"]
    assert pl["history"][-1]["comment"] == reason.strip()
    assert pl["history"][-1]["type"] == "AUTO_REJECT_CANCELLED"
    assert cancel(underwriter, aid, reason="Повтор").status_code == 409
    view = alexey.get(f"/applications/{aid}").json()
    assert view["status"] == "IN_REVIEW" and view["decision"] is None
    assert reason.strip() not in json.dumps(view, ensure_ascii=False)
    # Повторные открытия не применяют политику заново, даже при тех же плохих фактах.
    assert card(underwriter, aid)["stage"] == "UNDERWRITING"
    live = underwriter.get(f"/staff/applications/{aid}/scoring").json()
    assert not live["is_snapshot"] and live["ruleset_version"] == "RS-next"
    assert live["snapshots"] == frozen["snapshots"]
    # Человек вправе принять решение вопреки рекомендации; добавляется новый снимок.
    assert underwriter.post(f"/staff/applications/{aid}/approve", {"comment": "Проверено вручную"}).status_code == 200
    with SessionLocal() as db:
        decisions = db.scalars(select(Decision).where(Decision.application_id == aid).order_by(Decision.id)).all()
        assert len(decisions) == 2 and not decisions[0].is_active and decisions[1].is_active
        assert db.get(Application, aid).status == Status.APPROVED


def test_manual_reject_cannot_be_cancelled(alexey, staff, underwriter):
    aid = submitted(alexey, company_id(alexey, "ИП"))["id"]
    assert staff.post(f"/staff/applications/{aid}/reject", {"reason_code": "LOW_RATING"}).status_code == 200
    assert cancel(underwriter, aid, reason="Пересмотр").status_code == 409


def test_cancel_does_not_reopen_alongside_new_active_application(alexey, underwriter):
    app = risky(alexey)
    card(underwriter, app["id"])
    new = alexey.post(f"/companies/{app['company_id']}/applications", {"borrowing_mode": "NEW_CREDIT"})
    assert new.status_code == 201
    r = cancel(underwriter, app["id"], reason="Пересмотр")
    assert r.status_code == 409 and r.json()["error"]["code"] == "ACTIVE_APPLICATION_EXISTS"
    assert card(underwriter, app["id"])["auto_rejected"]


def test_unavailable_bureau_does_not_auto_reject(alexey, underwriter):
    aid = risky(alexey)["id"]
    bureau.set_available(False)
    assert not card(underwriter, aid)["auto_rejected"]
    bureau.set_available(True)
    assert not card(underwriter, aid)["auto_rejected"], "политика проверяется только на приёме"


def test_all_demo_companies_are_safe(alexey, maria, underwriter):
    # Три исходные компании + собственные компании/шесть заявок отдела.
    original_count = 0
    for api in (alexey, maria):
        for company in api.get("/companies").json()["items"]:
            submitted(api, company["id"])
            original_count += 1
    with SessionLocal() as db:
        seed_department(db, with_queue=True)
    rows = underwriter.get("/staff/queue", params={"scope": "all"}).json()["items"]
    assert original_count >= 3 and len(rows) == original_count + len(DEPARTMENT_APPLICATIONS)
    assert all(not r["pipeline"]["auto_rejected"] for r in rows)


def test_preview_does_not_trigger_policy(alexey, underwriter):
    aid = risky(alexey)["id"]
    assert underwriter.post(f"/staff/applications/{aid}/scoring/preview", {"amount": 800_000}).status_code == 200
    with SessionLocal() as db:
        assert db.get(Application, aid).status == Status.IN_REVIEW
        assert db.get(ApplicationPipeline, aid) is None
