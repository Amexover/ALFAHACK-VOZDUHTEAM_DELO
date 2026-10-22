"""Regression checks for the staff department review findings."""

from datetime import timedelta

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.settings import settings
from app.models import Application, InfoRequest, utcnow
from app.staff_pipeline.models import ApplicationPipeline
from tests.conftest import Api, company_id, submitted


def prepare_application(alexey, client):
    verifier = Api(client, "verifier")
    application = submitted(alexey, company_id(alexey, "ИП"))
    path = f"/staff/applications/{application['id']}"
    assert verifier.post(path + "/claim").status_code == 200
    return application["id"], path, verifier


@pytest.mark.parametrize("action,body", [
    ("approve", {"comment": "Одобряю"}),
    ("reject", {"reason_code": "LOW_RATING"}),
    ("counter-offer", {"amount": 800_000, "term_months": 18, "rate": 19.5, "comment": "Lower amount"}),
    ("request-info", {"message": "Confirm revenue", "requested_fields": ["monthly_revenue"]}),
])
def test_staff_action_locks_before_reading_pipeline(alexey, client, action, body):
    _, path, verifier = prepare_application(alexey, client)
    assert verifier.post(path + "/pass-to-underwriting").status_code == 200
    underwriter = Api(client, "underwriter")
    assert underwriter.post(path + "/claim").status_code == 200
    reads = []

    def record_application_read(state):
        if state.is_select and state.bind_mapper and state.bind_mapper.class_ is Application:
            # SQLite omits row locks; check the SQL sent by this same query on PostgreSQL.
            reads.append(str(state.statement.compile(dialect=postgresql.dialect())))

    event.listen(Session, "do_orm_execute", record_application_read)
    try:
        response = underwriter.post(path + "/" + action, body)
    finally:
        event.remove(Session, "do_orm_execute", record_application_read)

    assert response.status_code == 200, response.text
    assert reads and "FOR UPDATE" in reads[0], "Authorization must read the application under a row lock"


@pytest.mark.parametrize("pass_while_waiting", [False, True])
def test_delayed_staff_read_does_not_extend_client_wait(alexey, client, pass_while_waiting):
    application_id, path, verifier = prepare_application(alexey, client)
    assert verifier.post(path + "/request-info", {
        "message": "Confirm revenue", "requested_fields": ["monthly_revenue"],
    }).status_code == 200
    if pass_while_waiting:
        assert verifier.post(path + "/pass-to-underwriting").status_code == 200
    assert alexey.post(f"/applications/{application_id}/info-response", {
        "answer_text": "Confirmed", "fields": {"monthly_revenue": 2_000_000},
    }).status_code == 200

    with SessionLocal() as db:
        now = utcnow()
        pl = db.get(ApplicationPipeline, application_id)
        pl.stage_entered_at = now - timedelta(hours=50)
        pl.waiting_since = now - timedelta(hours=48)
        request = db.scalar(select(InfoRequest).where(InfoRequest.application_id == application_id))
        request.created_at = now - timedelta(hours=49 if pass_while_waiting else 48)
        request.answered_at = now - timedelta(hours=24)
        db.commit()

    card = verifier.get(path + "/pipeline").json()
    # Only the 24 hours before the answer are excluded; 26 hours count against the norm.
    assert card["waiting_minutes_total"] == 24 * 60
    assert card["waiting_for_client"] is False
    assert card["is_overdue"] is True
    expected_left = (24 if pass_while_waiting else 4) * 60 - 26 * 60
    assert expected_left - 1 <= card["time_left_minutes"] <= expected_left
    assert verifier.get(path + "/pipeline").json()["waiting_minutes_total"] == 24 * 60


@pytest.mark.parametrize("with_queue", [False, True])
def test_demo_reset_restores_department(client, monkeypatch, with_queue):
    monkeypatch.setattr(settings, "demo_tools_enabled", True)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("DEPARTMENT_DEMO_QUEUE", "true" if with_queue else "false")

    for _ in range(2):
        assert client.post("/api/demo/reset").status_code == 200
        for login, role in (("verifier", "VERIFIER"), ("underwriter", "UNDERWRITER"), ("staff", "UNDERWRITER")):
            member = Api(client, login).get("/staff/me").json()["department"]
            assert member["staff_role"] == role
            assert member["pipeline_enforced"] is (login != "staff")
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(Application)) == (6 if with_queue else 0)
