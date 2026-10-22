"""Полная последовательная Postman-приёмка. Запускать на отдельном тестовом стенде."""
import json
from pathlib import Path

items = []


def request(name, method, path, body=None, actor=None, status=200, checks=()):
    headers = [{"key": "Content-Type", "value": "application/json"}]
    if actor:
        headers.append({"key": "Authorization", "value": "Bearer {{" + actor + "Token}}"})
    req = {"method": method, "header": headers, "url": "{{baseUrl}}/api" + path}
    if body is not None:
        req["body"] = {"mode": "raw", "raw": json.dumps(body, ensure_ascii=False),
                       "options": {"raw": {"language": "json"}}}
    code = ["(() => {", f"pm.test('HTTP {status}', () => pm.response.to.have.status({status}));",
            "const data = pm.response.json();", *checks, "})();"]
    items.append({"name": name, "request": req,
                  "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": code}}]})


def login(actor, username):
    request("Login " + username, "POST", "/auth/login", {"login": username, "password": "demo"},
            checks=[f"pm.collectionVariables.set('{actor}Token', data.token);"])


def draft(name):
    request(name, "POST", "/companies/{{companyId}}/applications", {"borrowing_mode": "NEW_CREDIT"}, "client", 201,
            ["pm.collectionVariables.set('applicationId', data.id);"])
    request("Save draft", "PATCH", "/applications/{{applicationId}}", {
        "product_id": "WORKING_CAPITAL", "amount": 900000, "term_months": 18,
        "business_profile": {"industry": "Торговля", "months_operating": 36,
                             "monthly_revenue": 1800000, "monthly_debt_payments": 120000,
                             "purpose_details": "Изолированная приёмка отдела"}}, "client")
    request("Submit", "POST", "/applications/{{applicationId}}/submit", {"confirm_data": True}, "client")


request("Health", "GET", "/health")
request("Config", "GET", "/config")
for actor, user in [("client", "alexey"), ("staff", "staff"), ("verifier", "verifier"), ("underwriter", "underwriter")]:
    login(actor, user)
request("Companies", "GET", "/companies", actor="client", checks=[
    "pm.collectionVariables.set('companyId', data.items.find(c => c.legal_form === 'IP').id);"])
request("Dashboard", "GET", "/companies/{{companyId}}/dashboard", actor="client")
request("Quote", "POST", "/pricing/quote", {"company_id": "{{companyId}}", "borrowing_mode": "NEW_CREDIT",
                                               "amount": 900000, "term_months": 18}, "client")
draft("Create draft for department")
request("Application", "GET", "/applications/{{applicationId}}", actor="client")
request("Legacy queue", "GET", "/staff/applications", actor="staff")
request("Staff card", "GET", "/staff/applications/{{applicationId}}", actor="underwriter")
for actor in ("verifier", "underwriter"):
    request("Department identity " + actor, "GET", "/staff/me", actor=actor)
request("Department queue", "GET", "/staff/queue?scope=all", actor="verifier", checks=[
    "const auto = data.items.find(a => a.number === 'AUTO-T4-FIXTURE');",
    "pm.test('isolated auto fixture exists', () => pm.expect(auto).to.be.an('object'));",
    "if (auto) pm.collectionVariables.set('autoApplicationId', auto.id);"])
p = "/staff/applications/{{applicationId}}"
request("Pipeline card", "GET", p + "/pipeline", actor="verifier")
request("Claim by verifier", "POST", p + "/claim", actor="verifier")
request("My queue", "GET", "/staff/queue?scope=mine", actor="verifier")
request("Request information", "POST", p + "/request-info",
        {"message": "Подтвердите выручку", "requested_fields": ["monthly_revenue"]}, "verifier")
request("Answer information request", "POST", "/applications/{{applicationId}}/info-response",
        {"answer_text": "Подтверждаем", "fields": {"monthly_revenue": 2100000}}, "client")
request("Pass to underwriting", "POST", p + "/pass-to-underwriting", {"comment": "Сведения проверены"}, "verifier")
request("Claim by underwriter", "POST", p + "/claim", actor="underwriter")
request("Scoring", "GET", p + "/scoring", actor="underwriter")
request("Preview", "POST", p + "/scoring/preview", {"amount": 800000, "term_months": 24}, "underwriter")
request("Release", "POST", p + "/release", {"comment": "Передача смене"}, "underwriter")
request("Claim again", "POST", p + "/claim", actor="underwriter")
request("Approve", "POST", p + "/approve", {"comment": "Проверено"}, "underwriter")
request("Accept", "POST", "/applications/{{applicationId}}/accept", actor="client")
draft("Create draft for legacy decisions")
request("Counter offer", "POST", p + "/counter-offer", {"amount": 800000, "term_months": 24,
        "rate": 19.5, "comment": "Снижена сумма"}, "staff")
request("Supplement", "POST", "/applications/{{applicationId}}/supplement",
        {"answer_text": "Дополняем сведения", "fields": {"monthly_revenue": 2200000}}, "client")
request("Reject reasons", "GET", "/staff/reject-reasons", actor="staff")
request("Reject", "POST", p + "/reject", {"reason_code": "HIGH_DEBT_LOAD", "comment": "Проверено"}, "staff")
auto = "/staff/applications/{{autoApplicationId}}"
request("Automatic rejection", "GET", auto + "/pipeline", actor="underwriter", checks=[
    "pm.test('auto rejected', () => pm.expect(data.auto_rejected).to.equal(true));"])
request("Verifier cannot cancel", "POST", auto + "/cancel-auto-reject", {"reason": "Пересмотр"}, "verifier", 403)
request("Cancellation needs reason", "POST", auto + "/cancel-auto-reject", {"reason": "   "}, "underwriter", 422)
request("Cancel automatic rejection", "POST", auto + "/cancel-auto-reject",
        {"reason": "Подтверждение выручки проверено сотрудником"}, "underwriter", checks=[
            "pm.test('underwriting', () => pm.expect(data.pipeline.stage).to.equal('UNDERWRITING'));"])
request("Client sees review", "GET", "/applications/{{autoApplicationId}}", actor="client", checks=[
    "pm.test('review without decision', () => { pm.expect(data.status).to.equal('IN_REVIEW'); pm.expect(data.decision).to.equal(null); });"])
request("Manual decision after cancellation", "POST", auto + "/reject", {"reason_code": "HIGH_DEBT_LOAD"}, "underwriter")
request("News", "GET", "/news?company_id={{companyId}}", actor="client")
request("Support", "GET", "/support", actor="client")
collection = {"info": {"name": "Дело — полная приёмка Т1–Т4 (изолированный стенд)",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    "description": "Запускать на пустой отдельной базе после python -m scripts.prepare_staff_fixture --isolated. Создаёт синтетические заявки; рабочая база не подходит. Все токены получаются при запуске."},
    "variable": [{"key": "baseUrl", "value": "http://127.0.0.1:8081"}], "item": items}
out = Path(__file__).resolve().parents[2] / "docs" / "Delo.postman_collection.json"
out.write_text(json.dumps(collection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"{len(items)} запросов: {out}")
