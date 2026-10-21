import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["BUREAU_AVAILABLE"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import init_db  # noqa: E402
from app.simulators import bureau  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    init_db(reset=True)
    bureau.set_available(True)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class Api:
    """Клиент от имени конкретного пользователя (через Bearer-токен)."""

    def __init__(self, client: TestClient, login: str):
        r = client.post("/api/auth/login", json={"login": login, "password": "demo"})
        assert r.status_code == 200, r.text
        client.cookies.clear()  # работаем через токен, общий клиент не должен «помнить» последнего вошедшего
        self.c = client
        self.h = {"Authorization": f"Bearer {r.json()['token']}"}

    def get(self, url, **kw):
        return self.c.get("/api" + url, headers=self.h, **kw)

    def post(self, url, json=None):
        return self.c.post("/api" + url, headers=self.h, json=json or {})

    def patch(self, url, json):
        return self.c.patch("/api" + url, headers=self.h, json=json)


@pytest.fixture
def alexey(client):
    return Api(client, "alexey")


@pytest.fixture
def maria(client):
    return Api(client, "maria")


@pytest.fixture
def staff(client):
    return Api(client, "staff")


def company_id(api: Api, name_part: str) -> int:
    return next(c["id"] for c in api.get("/companies").json()["items"] if name_part in c["name"])


PROFILE = {
    "industry": "Оптовая торговля",
    "months_operating": 36,
    "monthly_revenue": 1_800_000,
    "monthly_debt_payments": 120_000,
    "purpose_details": "Закупка товаров к зимнему сезону",
}


def ready_draft(api: Api, cid: int, mode: str = "NEW_CREDIT", **patch) -> dict:
    r = api.post(f"/companies/{cid}/applications", {"borrowing_mode": mode})
    assert r.status_code in (200, 201), r.text
    app_id = r.json()["id"]
    body = {"business_profile": PROFILE, **patch}
    if mode == "NEW_CREDIT":
        body.setdefault("product_id", "WORKING_CAPITAL")
    r = api.patch(f"/applications/{app_id}", body)
    assert r.status_code == 200, r.text
    return r.json()


def submitted(api: Api, cid: int, mode: str = "NEW_CREDIT", **patch) -> dict:
    app = ready_draft(api, cid, mode, **patch)
    r = api.post(f"/applications/{app['id']}/submit", {"confirm_data": True})
    assert r.status_code == 200, r.text
    return r.json()
