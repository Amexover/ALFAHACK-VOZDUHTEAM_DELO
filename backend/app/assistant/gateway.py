"""Small, bounded client for Qwen's OpenAI-compatible inference protocol."""
import json
import logging

import httpx

from app.assistant.config import settings
from app.core.errors import ApiError

logger = logging.getLogger(__name__)


def require_enabled():
    if not settings.enabled:
        raise ApiError(503, "ASSISTANT_DISABLED", "ИИ-помощник ещё не подключён")


class VisibleText:
    """Defence against a misconfigured reasoning parser, including split tags."""
    def __init__(self):
        self.buffer = ""
        self.thinking = False

    def feed(self, text: str, final: bool = False) -> str:
        self.buffer += text
        result = ""
        while self.buffer:
            marker = "</think>" if self.thinking else "<think>"
            pos = self.buffer.find(marker)
            if pos >= 0:
                if not self.thinking:
                    result += self.buffer[:pos]
                self.buffer = self.buffer[pos + len(marker):]
                self.thinking = not self.thinking
                continue
            keep = 0
            if not final:
                for size in range(1, len(marker)):
                    if self.buffer.endswith(marker[:size]):
                        keep = size
            safe = self.buffer[:-keep] if keep else self.buffer
            if not self.thinking:
                result += safe
            self.buffer = self.buffer[-keep:] if keep else ""
            break
        return result


class QwenGateway:
    def client(self) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
        return httpx.AsyncClient(base_url=str(settings.base_url).rstrip("/") + "/", headers=headers,
                                 timeout=httpx.Timeout(settings.timeout_seconds, connect=5),
                                 follow_redirects=False, trust_env=False)

    async def health(self) -> dict:
        require_enabled()
        try:
            async with self.client() as client:
                response = await client.get("models", timeout=5)
                if response.status_code != 200 or len(response.content) > 100000:
                    raise ValueError("Invalid models response")
                models = [item["id"] for item in response.json()["data"]]
                if settings.model not in models:
                    raise ApiError(503, "ASSISTANT_MODEL_MISSING", "Выбранная модель не загружена на сервере инференса")
        except ApiError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            raise ApiError(503, "ASSISTANT_UNAVAILABLE", "Сервер модели недоступен") from None
        return {"status": "ready", "model": settings.model}

    async def stream(self, messages: list[dict], tools: list[dict], allow_tools: bool = True):
        require_enabled()
        payload = {"model": settings.model, "messages": messages, "stream": True,
                   "stream_options": {"include_usage": True}, "max_tokens": settings.max_output_tokens,
                   "temperature": 0.7, "top_p": 0.8, "presence_penalty": 1.5,
                   "chat_template_kwargs": {"enable_thinking": False, "preserve_thinking": False},
                   "tools": tools, "tool_choice": "auto" if allow_tools else "none"}
        filter_ = VisibleText()
        calls, received, finished, usage = {}, 0, None, {}
        try:
            async with self.client() as client:
                async with client.stream("POST", "chat/completions", json=payload) as response:
                    if response.status_code != 200:
                        logger.warning("Qwen inference returned HTTP %s", response.status_code)
                        if response.status_code == 429:
                            raise ApiError(503, "ASSISTANT_OVERLOADED", "Модель занята, повторите запрос позже")
                        raise ApiError(502, "ASSISTANT_UPSTREAM_ERROR", "Сервер модели не смог обработать запрос")
                    async for line in response.aiter_lines():
                        received += len(line)
                        if received > 2_000_000:
                            raise ValueError("Upstream response limit")
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        chunk = json.loads(data)
                        if "error" in chunk:
                            raise ValueError("Upstream stream error")
                        if chunk.get("usage"):
                            usage = {key: value for key, value in chunk["usage"].items()
                                     if key in ("prompt_tokens", "completion_tokens", "total_tokens")
                                     and type(value) is int and value >= 0}
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        choice = choices[0]
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            text = filter_.feed(delta["content"])
                            if text:
                                yield {"type": "delta", "text": text}
                        for part in delta.get("tool_calls") or []:
                            index = part["index"]
                            if type(index) is not int or not 0 <= index < 6:
                                raise ValueError("Tool call limit")
                            call = calls.setdefault(index, {"id": "", "type": "function",
                                                          "function": {"name": "", "arguments": ""}})
                            if part.get("id"):
                                call["id"] += part["id"]
                            for field in ("name", "arguments"):
                                call["function"][field] += (part.get("function") or {}).get(field, "")
                            if len(call["function"]["arguments"]) > 4000 or len(call["id"]) > 200 or len(call["function"]["name"]) > 80:
                                raise ValueError("Tool argument limit")
                        if choice.get("finish_reason"):
                            finished = choice["finish_reason"]
            tail = filter_.feed("", final=True)
            if tail:
                yield {"type": "delta", "text": tail}
            if finished not in ("stop", "tool_calls"):
                code = "ASSISTANT_OUTPUT_LIMIT" if finished == "length" else "ASSISTANT_INVALID_RESPONSE"
                raise ApiError(502, code, "Модель не завершила ответ; повторите запрос короче")
            if calls and (not allow_tools or any(not c["id"] or not c["function"]["name"] for c in calls.values())):
                raise ValueError("Invalid tool response")
            yield {"type": "result", "tool_calls": [calls[k] for k in sorted(calls)], "usage": usage}
        except ApiError:
            raise
        except httpx.TimeoutException:
            raise ApiError(504, "ASSISTANT_TIMEOUT", "Модель не ответила вовремя") from None
        except httpx.HTTPError:
            raise ApiError(503, "ASSISTANT_UNAVAILABLE", "Соединение с моделью недоступно") from None
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ApiError(502, "ASSISTANT_INVALID_RESPONSE", "Некорректный ответ сервера модели") from None
