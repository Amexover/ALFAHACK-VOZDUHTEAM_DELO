"""Сквозная HTTP-приёмка отдела: отдельная новая синтетическая компания, без reset.

После перезапуска API: тот же --state и --verify (только чтение).
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://frontend")
    parser.add_argument("--state", type=Path, default=Path("/tmp/staff-live-t4.json"))
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    checks = 0

    def call(method, path, actor=None, body=None, expected=200):
        nonlocal checks
        headers = {"Authorization": "Bearer " + actor} if actor else {}
        r = httpx.request(method, args.base.rstrip("/") + "/api" + path,
                          headers=headers, json=body, timeout=30)
        assert r.status_code == expected, (method, path, r.status_code, r.text)
        checks += 1
        return r.json()

    def login(name):
        return call("POST", "/auth/login", body={"login": name, "password": "demo"})["token"]

    client, verifier, underwriter = (login(name) for name in ("pavel", "verifier", "underwriter"))
    assert call("GET", "/staff/me", verifier)["department"]["staff_role"] == "VERIFIER"
    assert call("GET", "/staff/me", underwriter)["department"]["staff_role"] == "UNDERWRITER"
    if args.verify:
        state = json.loads(args.state.read_text())
        aid = state["application_id"]
        assert call("GET", f"/applications/{aid}", client)["status"] == "COMPLETED"
        score = call("GET", f"/staff/applications/{aid}/scoring", underwriter)
        assert score["is_snapshot"] and score["snapshots"] == state["snapshots"]
        assert call("GET", f"/staff/applications/{aid}/pipeline", underwriter)["stage"] == "DONE"
        phase = "after-api-restart"
    else:
        stamp = datetime.now(timezone.utc).strftime("%m%d%H%M%S")
        company = call("POST", "/companies", client,
                       {"legal_form": "OOO", "name": "ООО «Приёмка Т4 " + stamp + "»",
                        "registration_number": "377" + stamp}, 201)
        cid = company["id"]
        draft = call("POST", f"/companies/{cid}/applications", client, {"borrowing_mode": "NEW_CREDIT"}, 201)
        aid = draft["id"]
        call("PATCH", f"/applications/{aid}", client, {
            "product_id": "WORKING_CAPITAL", "amount": 900000, "term_months": 18,
            "business_profile": {"industry": "Торговля", "months_operating": 36,
                                 "monthly_revenue": 3000000, "monthly_debt_payments": 100000,
                                 "purpose_details": "Синтетическая приёмка отдела Т4"}})
        call("POST", f"/applications/{aid}/submit", client, {"confirm_data": True})
        path = f"/staff/applications/{aid}"
        call("GET", "/staff/queue", verifier)
        call("POST", path + "/claim", verifier)
        call("POST", path + "/approve", verifier, {}, 403)
        call("POST", path + "/pass-to-underwriting", verifier, {"comment": "Сведения проверены"})
        call("POST", path + "/claim", underwriter)
        assert not call("GET", path + "/scoring", underwriter)["is_snapshot"]
        call("POST", path + "/scoring/preview", underwriter, {"amount": 800000, "term_months": 24})
        call("POST", path + "/approve", underwriter, {"comment": "Сквозная приёмка Т4"})
        call("POST", f"/applications/{aid}/accept", client)
        view = call("GET", f"/applications/{aid}", client)
        assert view["status"] == "COMPLETED" and "scoring" not in view
        score = call("GET", path + "/scoring", underwriter)
        assert score["is_snapshot"] and len(score["snapshots"]) == 2
        call("POST", path + "/cancel-auto-reject", verifier, {"reason": "Проверка прав"}, 403)
        call("POST", path + "/cancel-auto-reject", underwriter, {"reason": "Ручное решение"}, 409)
        args.state.write_text(json.dumps({"application_id": aid, "company_id": cid,
                                          "snapshots": score["snapshots"]}, default=str), encoding="utf-8")
        phase = "verification-underwriting-decision-acceptance"
    print(json.dumps({"result": "PASS", "phase": phase, "checks": checks,
                      "application_id": aid, "status": "COMPLETED"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
