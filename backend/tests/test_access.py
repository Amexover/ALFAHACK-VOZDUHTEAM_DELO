from tests.conftest import company_id, ready_draft, submitted


def test_login_and_roles(client, alexey, staff):
    assert client.post("/api/auth/login", json={"login": "alexey", "password": "x"}).status_code == 401
    assert client.get("/api/companies").status_code == 401
    assert alexey.get("/staff/applications").status_code == 403
    assert staff.get("/companies").status_code == 403


def test_cookie_session(client):
    client.post("/api/auth/login", json={"login": "alexey", "password": "demo"})
    assert client.get("/api/auth/me").json()["user"]["full_name"] == "Алексей Морозов"


def test_company_isolation(alexey, maria):
    names = [c["name"] for c in alexey.get("/companies").json()["items"]]
    assert len(names) == 3 and "ООО «Северный Склад»" not in names
    ip = company_id(alexey, "ИП")
    assert maria.get(f"/companies/{ip}/dashboard").status_code == 404
    draft = ready_draft(alexey, ip)
    assert maria.get(f"/applications/{draft['id']}").status_code == 404
    assert maria.patch(f"/applications/{draft['id']}", {"term_months": 10}).status_code == 404


def test_foreign_loan_cannot_be_selected(alexey):
    ip = company_id(alexey, "ИП")
    vector = company_id(alexey, "Вектор")
    vector_loan = alexey.get(f"/companies/{vector}/loans").json()["items"][0]
    draft = alexey.post(f"/companies/{ip}/applications", {"borrowing_mode": "REFINANCE"}).json()
    r = alexey.patch(f"/applications/{draft['id']}", {"existing_loan_id": vector_loan["id"]})
    assert r.status_code == 404


def test_add_company(alexey, maria):
    r = alexey.post("/companies", {"legal_form": "IP", "name": "ИП Тест", "registration_number": "123"})
    assert r.status_code == 422 and "registration_number" in r.json()["error"]["fields"]
    r = alexey.post("/companies", {"legal_form": "OOO", "name": "ООО Новое", "registration_number": "1234567890123"})
    assert r.status_code == 201
    cid = r.json()["id"]
    dash = alexey.get(f"/companies/{cid}/dashboard").json()
    assert dash["rating"]["score"] == 600 and dash["loans"] == []
    assert cid not in [c["id"] for c in maria.get("/companies").json()["items"]]


def test_dashboard(alexey):
    ip = alexey.get(f"/companies/{company_id(alexey, 'ИП')}/dashboard").json()
    assert ip["rating"]["score"] == 820 and ip["rating"]["band"] == "HIGH"
    assert ip["loans"][0]["balance"] == 600_000 and ip["loans"][0]["name"] == "Оборотный кредит"
    assert ip["news"][0]["tag"] == "IP"
    mayak = alexey.get(f"/companies/{company_id(alexey, 'Маяк')}/dashboard").json()
    assert mayak["loans"] == [] and mayak["news"][0]["tag"] == "OOO"


def test_rating_unavailable(alexey):
    from app.simulators import bureau
    bureau.set_available(False)
    d = alexey.get(f"/companies/{company_id(alexey, 'ИП')}/dashboard").json()
    assert d["rating"] is None and d["rating_unavailable_text"] == "Рейтинг пока недоступен"


def test_demo_tools_closed_by_default(client, alexey, staff):
    """Служебные демо-операции закрыты: прямой запрос без авторизации ничего не меняет."""
    from app.simulators import bureau

    app_id = submitted(alexey, company_id(alexey, "ИП"))["id"]
    for path, body in (("/api/demo/reset", {}), ("/api/demo/bureau", {"available": False})):
        r = client.post(path, json=body)
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert bureau.is_available() is True
    assert staff.get(f"/staff/applications/{app_id}").status_code == 200
