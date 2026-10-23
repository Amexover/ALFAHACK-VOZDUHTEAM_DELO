"""Live acceptance through the API. Uses an existing company and deletes its own chat.

Set DELO_URL, DELO_LOGIN, DELO_PASSWORD. Run only against synthetic/demo data.
This script calls the real model, checks JSON and SSE, then cleans up its own conversations.
"""
import json
import os
import sys
from uuid import uuid4

import httpx


def main():
    base = os.environ.get("DELO_URL", "http://localhost:8000").rstrip("/")
    login = os.environ.get("DELO_LOGIN", "alexey")
    password = os.environ.get("DELO_PASSWORD")
    if not password:
        raise SystemExit("Set DELO_PASSWORD for your demo account")
    chats = []
    with httpx.Client(base_url=base, timeout=240, trust_env=False) as client:
        auth = client.post("/api/auth/login", json={"login": login, "password": password})
        auth.raise_for_status()
        client.headers["Authorization"] = "Bearer " + auth.json()["token"]
        health = client.get("/api/assistant/health")
        health.raise_for_status()
        expected_model = os.environ.get("DELO_EXPECTED_MODEL", "Qwen/Qwen3.8-27B")
        assert health.json()["model"] == expected_model
        companies = client.get("/api/companies")
        companies.raise_for_status()
        company = companies.json()["items"][0]
        try:
            for streaming in (False, True):
                create = client.post("/api/assistant/conversations", json={
                    "company_id": company["id"], "title": "Assistant live smoke"})
                create.raise_for_status()
                cid = create.json()["id"]
                chats.append(cid)
                endpoint = f"/api/assistant/conversations/{cid}/messages" + ("/stream" if streaming else "")
                body = {"request_id": str(uuid4()), "content": "Какой у выбранной компании рейтинг? Не выдумывай причины изменения.",
                        "intent": "rating"}
                if streaming:
                    done = None
                    with client.stream("POST", endpoint, json=body) as response:
                        response.raise_for_status()
                        for line in response.iter_lines():
                            if not line.startswith("data: "):
                                continue
                            event = json.loads(line[6:])
                            assert event["type"] != "error", event.get("code")
                            if event["type"] == "done":
                                done = event["turn"]
                    assert done and done["status"] == "completed"
                else:
                    answer = client.post(endpoint, json=body)
                    answer.raise_for_status()
                    done = answer.json()
                    replay = client.post(endpoint, json=body)
                    replay.raise_for_status()
                    assert replay.json() == done
                assert done["assistant_content"] and any(s["id"] == "rating" for s in done["sources"])
                assert "<think>" not in done["assistant_content"]
                print(f"{'SSE' if streaming else 'JSON'}: completed, model={done['model']}, latency_ms={done['latency_ms']}")
        finally:
            for cid in chats:
                response = client.delete(f"/api/assistant/conversations/{cid}")
                if response.status_code != 204:
                    print(f"Cleanup pending for conversation {cid}", file=sys.stderr)
    print("Live Qwen protocol smoke passed. Response quality still requires domain evaluation.")


if __name__ == "__main__":
    main()
