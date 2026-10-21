from tests.conftest import PROFILE, company_id, ready_draft, submitted


def test_draft_persists_and_recalculates(alexey):
    ip = company_id(alexey, "ИП")
    r = alexey.post(f"/companies/{ip}/applications", {"borrowing_mode": "NEW_CREDIT"})
    assert r.status_code == 201
    app_id = r.json()["id"]
    # повторное создание возвращает тот же черновик
    assert alexey.post(f"/companies/{ip}/applications", {"borrowing_mode": "NEW_CREDIT"}).json()["id"] == app_id
    r = alexey.patch(f"/applications/{app_id}", {"amount": 2_000_000, "term_months": 30, "current_step": "parameters"}).json()
    assert r["preliminary_rate"] == 20.0 and r["preliminary_payment"] > 0
    r = alexey.patch(f"/applications/{app_id}", {"product_id": "EQUIPMENT"}).json()
    assert r["amount"] == 2_000_000 and r["term_months"] == 30 and r["product_name"] == "Кредит на оборудование"
    assert alexey.get(f"/applications/{app_id}").json()["current_step"] == "parameters"
    assert alexey.patch(f"/applications/{app_id}", {"amount": 3_500_000}).status_code == 422
    assert alexey.patch(f"/applications/{app_id}", {"business_profile": {"monthly_revenue": -5}}).status_code == 422


def test_dashboard_news_follow_product(alexey):
    ip = company_id(alexey, "ИП")
    ready_draft(alexey, ip, product_id="EQUIPMENT")
    assert alexey.get(f"/companies/{ip}/dashboard").json()["news"][0]["tag"] == "EQUIPMENT"


def test_submit_validation_and_double_submit(alexey):
    ip = company_id(alexey, "ИП")
    draft = alexey.post(f"/companies/{ip}/applications", {"borrowing_mode": "NEW_CREDIT"}).json()
    r = alexey.post(f"/applications/{draft['id']}/submit", {"confirm_data": True})
    assert r.status_code == 422 and "product_id" in r.json()["error"]["fields"]
    alexey.patch(f"/applications/{draft['id']}", {"product_id": "WORKING_CAPITAL", "business_profile": PROFILE})
    assert alexey.post(f"/applications/{draft['id']}/submit", {}).status_code == 422  # нет подтверждения
    r1 = alexey.post(f"/applications/{draft['id']}/submit", {"confirm_data": True})
    r2 = alexey.post(f"/applications/{draft['id']}/submit", {"confirm_data": True})
    assert r1.status_code == 200 and r2.status_code == 409
    body = r1.json()
    assert body["number"].startswith("D-") and body["status"] == "IN_REVIEW"
    assert body["stage"]["active"] == "CHECK" and len(body["events"]) == 1
    assert alexey.patch(f"/applications/{draft['id']}", {"term_months": 10}).status_code == 409


def test_full_new_credit_path(alexey, staff):
    ip = company_id(alexey, "ИП")
    app = submitted(alexey, ip)
    aid = app["id"]
    # клиент не видит внутреннюю оценку
    assert "scoring" not in app
    card = staff.get(f"/staff/applications/{aid}").json()
    assert card["scoring"]["recommendation"] in ("APPROVE", "MANUAL", "REJECT") and len(card["checks"]) == 4

    r = staff.post(f"/staff/applications/{aid}/request-info",
                   {"message": "Уточните выручку", "requested_fields": ["monthly_revenue"]})
    assert r.json()["status"] == "NEED_INFO"
    view = alexey.get(f"/applications/{aid}").json()
    assert view["info_request"]["requested_fields"][0]["key"] == "monthly_revenue"
    assert view["available_actions"] == ["info_response"]
    assert alexey.post(f"/applications/{aid}/info-response", {"answer_text": "Вот"}).status_code == 422
    r = alexey.post(f"/applications/{aid}/info-response", {"answer_text": "Выручка выросла", "fields": {"monthly_revenue": 2_000_000}})
    assert r.json()["status"] == "IN_REVIEW" and r.json()["business_profile"]["monthly_revenue"] == 2_000_000
    assert alexey.post(f"/applications/{aid}/info-response", {"answer_text": "ещё"}).status_code == 409
    assert staff.get(f"/staff/applications/{aid}").json()["info_requests"][0]["answer_fields"] == {"monthly_revenue": 2_000_000}

    same = staff.post(f"/staff/applications/{aid}/counter-offer",
                      {"amount": app["amount"], "term_months": app["term_months"], "rate": app["preliminary_rate"], "comment": "x"})
    assert same.status_code == 422
    r = staff.post(f"/staff/applications/{aid}/counter-offer",
                   {"amount": 800_000, "term_months": 18, "rate": 19.5, "comment": "Снизили сумму по выручке"})
    assert r.json()["status"] == "COUNTER_OFFER"
    # второе решение — конфликт
    assert staff.post(f"/staff/applications/{aid}/approve", {}).status_code == 409

    view = alexey.get(f"/applications/{aid}").json()
    d = view["decision"]
    assert d["rate"] == 19.5 and d["requested"]["amount"] == 1_000_000 and "amount" in d["changed_fields"]
    assert set(view["available_actions"]) == {"accept", "supplement"}

    r = alexey.post(f"/applications/{aid}/accept")
    assert r.json()["status"] == "COMPLETED" and r.json()["stage"]["steps"][3]["state"] == "done"
    assert alexey.post(f"/applications/{aid}/accept").status_code == 409
    dash = alexey.get(f"/companies/{ip}/dashboard").json()
    assert len(dash["loans"]) == 1 and dash["past_applications"][0]["id"] == aid
    # после завершения можно начать новую заявку
    assert alexey.post(f"/companies/{ip}/applications", {"borrowing_mode": "NEW_CREDIT"}).json()["id"] != aid


def test_approve_and_reject(alexey, staff):
    ip = company_id(alexey, "ИП")
    a = submitted(alexey, ip)
    r = staff.post(f"/staff/applications/{a['id']}/approve", {"comment": "Всё в порядке"}).json()
    assert r["decision"]["amount"] == a["amount"] and r["decision"]["rate"] == a["preliminary_rate"]

    vector = company_id(alexey, "Вектор")
    b = submitted(alexey, vector)
    assert staff.post(f"/staff/applications/{b['id']}/reject", {"reason_code": "NOPE"}).status_code == 422
    staff.post(f"/staff/applications/{b['id']}/reject", {"reason_code": "LOW_RATING"})
    view = alexey.get(f"/applications/{b['id']}").json()
    assert view["status"] == "REJECTED" and view["decision"]["reason_text"] and view["available_actions"] == []
    assert alexey.post(f"/applications/{b['id']}/accept").status_code == 409


def test_supplement_returns_to_review(alexey, staff):
    ip = company_id(alexey, "ИП")
    a = submitted(alexey, ip)
    staff.post(f"/staff/applications/{a['id']}/counter-offer", {"amount": 500_000, "term_months": 12, "rate": 18, "comment": "x"})
    r = alexey.post(f"/applications/{a['id']}/supplement", {"answer_text": "Добавлю выручку", "fields": {"monthly_revenue": 3_000_000}})
    assert r.json()["status"] == "IN_REVIEW" and r.json()["decision"] is None
    assert alexey.post(f"/applications/{a['id']}/accept").status_code == 409


def test_refinance_path(alexey, staff):
    ip = company_id(alexey, "ИП")
    loan = alexey.get(f"/companies/{ip}/loans").json()["items"][0]
    mayak = company_id(alexey, "Маяк")
    r = alexey.post(f"/companies/{mayak}/applications", {"borrowing_mode": "REFINANCE"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "NO_LOANS_TO_REFINANCE"

    draft = ready_draft(alexey, ip, "REFINANCE", existing_loan_id=loan["id"], term_months=24)
    assert draft["amount"] == 600_000 and draft["preliminary_rate"] == 17.0 and draft["comparison"]["is_better"]
    assert alexey.patch(f"/applications/{draft['id']}", {"amount": 700_000}).status_code == 422
    assert alexey.patch(f"/applications/{draft['id']}", {"product_id": "EQUIPMENT"}).status_code == 422
    # новый кредит и рефинансирование могут идти параллельно
    assert alexey.post(f"/companies/{ip}/applications", {"borrowing_mode": "NEW_CREDIT"}).status_code == 201

    a = alexey.post(f"/applications/{draft['id']}/submit", {"confirm_data": True}).json()
    assert a["existing_loan"]["id"] == loan["id"] and a["product_id"] is None
    r = staff.post(f"/staff/applications/{a['id']}/counter-offer", {"amount": 700_000, "term_months": 24, "rate": 17, "comment": "x"})
    assert r.status_code == 422
    r = staff.post(f"/staff/applications/{a['id']}/counter-offer", {"amount": 500_000, "term_months": 24, "rate": 17, "comment": "Частично"})
    view = alexey.get(f"/applications/{a['id']}").json()
    assert view["decision"]["refinance_remainder"] == 100_000


def test_staff_queue(alexey, staff):
    ip = company_id(alexey, "ИП")
    ready_draft(alexey, company_id(alexey, "Маяк"))  # черновик не виден сотруднику
    submitted(alexey, ip)
    q = staff.get("/staff/applications").json()
    assert len(q["items"]) == 1 and q["counts"]["IN_REVIEW"] == 1
    assert staff.get("/staff/applications", params={"status": "NEED_INFO"}).json()["items"] == []
