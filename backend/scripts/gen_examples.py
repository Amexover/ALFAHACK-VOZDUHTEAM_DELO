"""Генерирует реальные примеры ответов API в docs/api-examples/. Запуск: python -m scripts.gen_examples"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "ex.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import init_db  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "api-examples"
OUT.mkdir(parents=True, exist_ok=True)


def dump(name, resp):
    (OUT / f"{name}.json").write_text(json.dumps(resp.json(), ensure_ascii=False, indent=2, default=str))
    return resp.json()


init_db(reset=True)
with TestClient(app) as c:
    def login(u):
        r = c.post("/api/auth/login", json={"login": u, "password": "demo"})
        c.cookies.clear()
        return {"Authorization": "Bearer " + r.json()["token"]}, r

    A, r = login("alexey")
    dump("auth_login", r)
    S, _ = login("staff")
    dump("config", c.get("/api/config"))
    comps = dump("companies_list", c.get("/api/companies", headers=A))["items"]
    ip, mayak, vector = (x["id"] for x in comps)
    dump("company_create_error", c.post("/api/companies", headers=A, json={"legal_form": "IP", "name": "", "registration_number": "12"}))
    dump("dashboard_ip", c.get(f"/api/companies/{ip}/dashboard", headers=A))
    dump("loans_ip", c.get(f"/api/companies/{ip}/loans", headers=A))
    dump("quote_new", c.post("/api/pricing/quote", headers=A, json={"company_id": ip, "borrowing_mode": "NEW_CREDIT", "amount": 1500000, "term_months": 24}))
    loan = c.get(f"/api/companies/{ip}/loans", headers=A).json()["items"][0]
    dump("quote_refinance", c.post("/api/pricing/quote", headers=A, json={"company_id": ip, "borrowing_mode": "REFINANCE", "existing_loan_id": loan["id"], "term_months": 18}))
    dump("refinance_no_loans_409", c.post(f"/api/companies/{mayak}/applications", headers=A, json={"borrowing_mode": "REFINANCE"}))
    d = dump("draft_created", c.post(f"/api/companies/{ip}/applications", headers=A, json={"borrowing_mode": "NEW_CREDIT"}))
    aid = d["id"]
    dump("draft_patch_error", c.patch(f"/api/applications/{aid}", headers=A, json={"amount": 5000000, "business_profile": {"monthly_revenue": -1}}))
    prof = {"industry": "Оптовая торговля", "months_operating": 36, "monthly_revenue": 1800000, "monthly_debt_payments": 120000, "purpose_details": "Закупка товаров к зимнему сезону"}
    dump("submit_incomplete_422", c.post(f"/api/applications/{aid}/submit", headers=A, json={"confirm_data": False}))
    dump("draft_filled", c.patch(f"/api/applications/{aid}", headers=A, json={"product_id": "WORKING_CAPITAL", "amount": 1500000, "term_months": 24, "business_profile": prof, "current_step": "review"}))
    dump("application_submitted", c.post(f"/api/applications/{aid}/submit", headers=A, json={"confirm_data": True}))
    dump("submit_again_409", c.post(f"/api/applications/{aid}/submit", headers=A, json={"confirm_data": True}))
    dump("staff_queue", c.get("/api/staff/applications", headers=S))
    dump("staff_card", c.get(f"/api/staff/applications/{aid}", headers=S))
    c.post(f"/api/staff/applications/{aid}/request-info", headers=S, json={"message": "Уточните, пожалуйста, среднемесячную выручку за последние полгода.", "requested_fields": ["monthly_revenue"]})
    dump("application_need_info", c.get(f"/api/applications/{aid}", headers=A))
    c.post(f"/api/applications/{aid}/info-response", headers=A, json={"answer_text": "Выручка выросла после открытия второго склада.", "fields": {"monthly_revenue": 2100000}})
    c.post(f"/api/staff/applications/{aid}/counter-offer", headers=S, json={"amount": 1200000, "term_months": 24, "rate": 19.5, "comment": "Снизили сумму с учётом долговой нагрузки."})
    dump("application_counter_offer", c.get(f"/api/applications/{aid}", headers=A))
    dump("application_completed", c.post(f"/api/applications/{aid}/accept", headers=A))
    dump("accept_again_409", c.post(f"/api/applications/{aid}/accept", headers=A))
    b = c.post(f"/api/companies/{vector}/applications", headers=A, json={"borrowing_mode": "REFINANCE"}).json()
    vloan = c.get(f"/api/companies/{vector}/loans", headers=A).json()["items"][0]
    dump("refinance_draft", c.patch(f"/api/applications/{b['id']}", headers=A, json={"existing_loan_id": vloan["id"], "term_months": 30, "business_profile": {**prof, "purpose_details": "Хочу снизить ежемесячный платёж"}}))
    c.post(f"/api/applications/{b['id']}/submit", headers=A, json={"confirm_data": True})
    dump("staff_reject_reasons", c.get("/api/staff/reject-reasons", headers=S))
    c.post(f"/api/staff/applications/{b['id']}/reject", headers=S, json={"reason_code": "LOW_RATING"})
    dump("application_rejected", c.get(f"/api/applications/{b['id']}", headers=A))
    dump("my_applications", c.get(f"/api/companies/{ip}/applications", headers=A))
    dump("news_list", c.get(f"/api/news?company_id={mayak}&product_id=EQUIPMENT", headers=A))
    dump("news_detail", c.get("/api/news/1", headers=A))
    dump("support", c.get("/api/support"))
    dump("unauthorized_401", c.get("/api/companies"))
print("ok", len(list(OUT.glob("*.json"))), "files")
