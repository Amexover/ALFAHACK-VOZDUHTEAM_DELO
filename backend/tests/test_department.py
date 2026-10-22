"""Тикет 01: отдел сотрудников — роли, сид отдела, неизменность клиентской стороны.

Демонстрационная очередь отдела в тестах не создаётся автоматически
(иначе изменился бы baseline чужих тестов), поэтому здесь она сеется явно.
"""

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.enums import Role, Status
from app.models import Application, Company, User
from app.staff_pipeline.enums import StaffRole
from app.staff_pipeline.models import StaffProfile
from app.staff_pipeline.seed import DEPARTMENT_APPLICATIONS, seed_department
from tests.conftest import Api


@pytest.fixture
def department(client):
    """Сеет отдел вместе с демонстрационной очередью."""
    with SessionLocal() as db:
        return seed_department(db, with_queue=True)


@pytest.fixture
def verifier(client):
    return Api(client, "verifier")


@pytest.fixture
def underwriter(client):
    return Api(client, "underwriter")


def _count(model, *where) -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(model).where(*where))


# ---------- роли внутри отдела ----------

def test_verifier_and_underwriter_can_log_in_and_know_their_role(verifier, underwriter):
    v = verifier.get("/staff/me").json()
    u = underwriter.get("/staff/me").json()
    assert v["department"]["staff_role"] == "VERIFIER"
    assert v["department"]["staff_role_label"] == "Верификатор"
    assert v["department"]["is_verifier"] and not v["department"]["is_underwriter"]
    assert u["department"]["staff_role"] == "UNDERWRITER"
    assert u["department"]["is_underwriter"] and not u["department"]["is_verifier"]
    assert v["user"]["login"] == "verifier" and u["user"]["login"] == "underwriter"


def test_existing_staff_account_becomes_underwriter_and_keeps_rights(staff):
    me = staff.get("/staff/me").json()
    assert me["user"]["login"] == "staff" and me["user"]["full_name"] == "Ирина Котова"
    assert me["department"]["staff_role"] == "UNDERWRITER"
    # прежние ручки сотрудника продолжают работать
    assert staff.get("/staff/applications").status_code == 200
    assert staff.get("/staff/reject-reasons").status_code == 200


def test_department_contract_for_frontend(verifier):
    body = verifier.get("/staff/me").json()["department"]
    assert set(body) == {"staff_role", "staff_role_label", "is_verifier", "is_underwriter",
                         "pipeline_enforced", "permissions", "stage_norms", "stages"}
    assert body["pipeline_enforced"] is True
    assert "application:pass_to_underwriting" in body["permissions"]
    assert "application:decide" not in body["permissions"]
    norms = {n["stage"]: n for n in body["stage_norms"]}
    assert norms["VERIFICATION"]["limit_hours"] == 4 and norms["VERIFICATION"]["owner_staff_role"] == "VERIFIER"
    assert norms["UNDERWRITING"]["limit_hours"] == 24 and norms["UNDERWRITING"]["owner_staff_role"] == "UNDERWRITER"


def test_department_me_is_closed_for_clients_and_guests(client, alexey):
    assert alexey.get("/staff/me").status_code == 403
    assert client.get("/api/staff/me").status_code == 401


def test_staff_without_profile_does_not_break_the_endpoint(staff):
    """Если профиля отдела нет, ручка отвечает, а не падает."""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.login == "staff"))
        db.delete(db.get(StaffProfile, user.id))
        db.commit()
    body = staff.get("/staff/me").json()
    assert body["department"]["staff_role"] is None
    assert body["department"]["staff_role_label"] == "Сотрудник банка"
    assert body["department"]["permissions"] == ["queue:view"]


# ---------- клиентская сторона не затронута ----------

def test_common_roles_are_unchanged(verifier, underwriter, staff, alexey):
    for api in (verifier, underwriter, staff):
        assert api.get("/auth/me").json()["user"]["role"] == Role.EMPLOYEE
    assert alexey.get("/auth/me").json()["user"]["role"] == Role.CLIENT
    assert _count(User, User.role.notin_([Role.CLIENT, Role.EMPLOYEE])) == 0


def test_client_still_sees_bank_instead_of_staff_name(client, department):
    """История заявки у клиента по-прежнему маскирует сотрудника под «Банк»."""
    with SessionLocal() as db:
        app = db.scalar(select(Application).where(Application.status == Status.NEED_INFO))
        owner_login = app.company.owner.login
        app_id = app.id
    owner = Api(client, owner_login)
    view = owner.get(f"/applications/{app_id}").json()
    employee_events = [e for e in view["events"] if e["actor_role"] == Role.EMPLOYEE]
    assert employee_events and all(e["actor"] == "Банк" for e in employee_events)
    assert "Наталья Белова" not in owner.get(f"/applications/{app_id}").text
    # внутренних блоков сотрудника в клиентском ответе нет
    assert not {"scoring", "checks", "rating", "client"} & set(view)


def test_department_seed_does_not_touch_the_existing_seed(department, alexey):
    with SessionLocal() as db:
        for login, full_name in (("alexey", "Алексей Морозов"), ("maria", "Мария Ковалёва"),
                                 ("staff", "Ирина Котова")):
            user = db.scalar(select(User).where(User.login == login))
            assert user is not None and user.full_name == full_name
    names = [c["name"] for c in alexey.get("/companies").json()["items"]]
    assert len(names) == 3 and "ООО «Хлебный Двор»" not in names


# ---------- сид отдела ----------

def test_department_seed_is_idempotent(department):
    assert department["created_applications"] == len(DEPARTMENT_APPLICATIONS)
    before = (_count(User), _count(Company), _count(Application), _count(StaffProfile))
    with SessionLocal() as db:
        again = seed_department(db, with_queue=True)
    assert again == {"promoted_staff": 0, "created_staff": 0, "created_applications": 0}
    assert (_count(User), _count(Company), _count(Application), _count(StaffProfile)) == before


def test_department_seed_creates_staff_and_queue(department):
    with SessionLocal() as db:
        roles = dict(db.execute(select(StaffProfile.staff_role, func.count()).group_by(StaffProfile.staff_role)).all())
    assert roles == {StaffRole.VERIFIER: 1, StaffRole.UNDERWRITER: 2}
    assert 5 <= _count(Application) <= 6
    with SessionLocal() as db:
        submitted = db.scalars(select(Application.submitted_at)).all()
    assert all(s is not None for s in submitted)
    assert len(set(submitted)) == len(submitted), "заявки поданы в разное время"


def test_queue_returns_department_applications(department, staff):
    queue = staff.get("/staff/applications").json()
    assert len(queue["items"]) == len(DEPARTMENT_APPLICATIONS)
    assert all(item["number"] and item["company_name"] for item in queue["items"])
    assert queue["counts"]["IN_REVIEW"] == 5 and queue["counts"]["NEED_INFO"] == 1
    # карточка каждой демо-заявки открывается
    for item in queue["items"]:
        card = staff.get(f"/staff/applications/{item['id']}")
        assert card.status_code == 200, card.text
        assert card.json()["scoring"]["recommendation"] in ("APPROVE", "REJECT", "MANUAL")


def test_department_queue_is_disabled_under_pytest():
    """Защита чужого baseline: при автоматическом старте в тестах демо-очередь не сеется."""
    from app.staff_pipeline.seed import demo_queue_enabled

    assert demo_queue_enabled() is False
