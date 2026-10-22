"""Реальные примеры ответов ручек отдела → docs/api-examples/department/.

Запуск: python -m scripts.gen_department_examples
Примеры снимаются с живого приложения на демонстрационных данных отдела,
поэтому расходиться с кодом они не могут.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "department-ex.db")
os.environ["DEPARTMENT_DEMO_QUEUE"] = "true"
os.environ.pop("PYTEST_CURRENT_TEST", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import init_db  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "api-examples" / "department"
OUT.mkdir(parents=True, exist_ok=True)


def dump(name, resp):
    (OUT / f"{name}.json").write_text(
        json.dumps(resp.json(), ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    print(f"{name}.json  <- {resp.status_code}")
    return resp.json()


init_db(reset=True)
with TestClient(app) as c:
    def login(u):
        r = c.post("/api/auth/login", json={"login": u, "password": "demo"})
        assert r.status_code == 200, r.text
        c.cookies.clear()
        return {"Authorization": "Bearer " + r.json()["token"]}

    V = login("verifier")
    U = login("underwriter")
    A = login("alexey")

    dump("staff_me_verifier", c.get("/api/staff/me", headers=V))
    dump("staff_me_underwriter", c.get("/api/staff/me", headers=U))
    dump("staff_me_forbidden_403", c.get("/api/staff/me", headers=A))
    dump("staff_me_unauthorized_401", c.get("/api/staff/me"))

    queue = dump("staff_queue_with_department_demo", c.get("/api/staff/applications", headers=U))
    first = queue["items"][0]["id"]
    dump("staff_card_department_demo", c.get(f"/api/staff/applications/{first}", headers=U))

    # ---------- конвейер (тикет 02) ----------
    dump("queue_free", c.get("/api/staff/queue", headers=V))
    dump("queue_overdue", c.get("/api/staff/queue", headers=V, params={"scope": "overdue"}))

    # заявка проходит конвейер: верификатор берёт её в работу и передаёт на андеррайтинг
    target = c.get("/api/staff/queue", headers=V).json()["items"][0]["id"]
    dump("pipeline_claimed", c.post(f"/api/staff/applications/{target}/claim", headers=V))
    dump("pipeline_stage_forbidden_403",
         c.post(f"/api/staff/applications/{target}/approve", headers=V, json={}))
    dump("pipeline_passed_to_underwriting",
         c.post(f"/api/staff/applications/{target}/pass-to-underwriting", headers=V,
                json={"comment": "Анкета полная, проверки пройдены"}))
    dump("pipeline_stage_forbidden_claim_403",
         c.post(f"/api/staff/applications/{target}/claim", headers=V))
    dump("pipeline_not_assigned_409",
         c.post(f"/api/staff/applications/{target}/approve", headers=U, json={}))
    fresh = c.get("/api/staff/queue", headers=V).json()["items"][0]["id"]
    dump("pipeline_wrong_stage_409",
         c.post(f"/api/staff/applications/{fresh}/approve", headers=U, json={}))
    c.post(f"/api/staff/applications/{target}/claim", headers=U)
    S = login("staff")
    dump("pipeline_already_claimed_409", c.post(f"/api/staff/applications/{target}/claim", headers=S))
    dump("pipeline_card", c.get(f"/api/staff/applications/{target}/pipeline", headers=U))
    dump("queue_mine", c.get("/api/staff/queue", headers=U, params={"scope": "mine"}))

    # вторая заявка: взята в работу и освобождена обратно в очередь
    other = c.get("/api/staff/queue", headers=V).json()["items"][0]["id"]
    c.post(f"/api/staff/applications/{other}/claim", headers=V)
    dump("pipeline_released", c.post(f"/api/staff/applications/{other}/release", headers=V,
                                     json={"comment": "Передаю смене"}))
print(f"\nготово: {OUT}")
