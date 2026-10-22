"""E2E-only API: isolated synthetic SQLite database and deterministic inference.

Never imported by production. No model weights, external APIs or existing databases.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

frontend = Path(__file__).resolve().parents[1]
runtime = frontend / "test-results"
runtime.mkdir(exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + (runtime / f"assistant-{uuid4().hex}.db").as_posix()
os.environ["ASSISTANT_ENABLED"] = "true"
os.environ["BUREAU_AVAILABLE"] = "true"
os.environ["COOKIE_SECURE"] = "false"
sys.path.insert(0, str(frontend.parent / "backend"))

from app.assistant.gateway import QwenGateway  # noqa: E402
from app.core.errors import ApiError  # noqa: E402
from app.main import app  # noqa: E402


async def stream(self, messages, tools, allow_tools=True):
    question = next(m["content"] for m in reversed(messages) if m["role"] == "user")
    if "сбой" in question.lower():
        raise ApiError(504, "ASSISTANT_TIMEOUT", "Тестовый таймаут: повторите вопрос")
    if "долго" in question.lower():
        await asyncio.sleep(30)
    if messages[-1]["role"] == "user" and allow_tools:
        yield {"type": "result", "tool_calls": [{"id": "e2e-search", "type": "function", "function": {
            "name": "search_knowledge", "arguments": json.dumps({"query": "Кредитный рейтинг"})}}], "usage": {}}
        return
    answer = "**Тестовый ответ.** Рейтинг компании — показатель бюро, а решение по заявке принимает банк.\n\nПроверьте сведения и своевременность платежей. [rating]"
    for index in range(0, len(answer), 9):
        await asyncio.sleep(0.035)
        yield {"type": "delta", "text": answer[index:index + 9]}
    yield {"type": "result", "tool_calls": [], "usage": {"prompt_tokens": 20, "completion_tokens": 30}}


async def health(self):
    return {"status": "ready", "model": "Qwen/Qwen3.8-27B", "test_fixture": True}


QwenGateway.stream = stream
QwenGateway.health = health

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8017, log_level="warning")
