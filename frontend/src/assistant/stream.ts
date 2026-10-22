import { ApiError } from "../api";
import type { Intent, StreamEvent } from "./types";

/** POST + cookie authentication, UTF-8/CRLF-safe SSE, including fragmented frames. */
export async function streamMessage(
  id: string,
  body: { request_id: string; content: string; intent: Intent },
  signal: AbortSignal,
  onEvent: (event: StreamEvent) => void,
) {
  let response: Response;
  try {
    response = await fetch(
      `/api/assistant/conversations/${encodeURIComponent(id)}/messages/stream`,
      {
        method: "POST",
        credentials: "same-origin",
        signal,
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify(body),
      },
    );
  } catch (e) {
    if (signal.aborted) throw e;
    throw new ApiError(
      0,
      "Соединение прервалось. Ваш вопрос сохранён в поле ввода.",
    );
  }
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event("delo:session-expired"));
    const data = await response.json().catch(() => null);
    throw new ApiError(
      response.status,
      data?.error?.message || "Не удалось получить ответ помощника.",
      data?.error?.fields || {},
      data?.error?.code || "",
    );
  }
  if (
    !response.body ||
    !response.headers.get("content-type")?.includes("text/event-stream")
  )
    throw new ApiError(502, "Сервер вернул некорректный поток ответа.");
  const reader = response.body.getReader(),
    decoder = new TextDecoder();
  let buffer = "",
    done = false;
  function frame(value: string) {
    const raw = value
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n");
    if (!raw) return;
    let event: StreamEvent;
    try {
      event = JSON.parse(raw);
    } catch {
      throw new ApiError(502, "Не удалось прочитать ответ помощника.");
    }
    if (event.type === "error")
      throw new ApiError(event.status, event.message, {}, event.code);
    if (event.type === "done") done = true;
    onEvent(event);
  }
  try {
    while (!done) {
      const chunk = await reader.read();
      buffer += decoder.decode(chunk.value, { stream: !chunk.done });
      if (buffer.length > 1_000_000)
        throw new ApiError(502, "Ответ превысил допустимый размер.");
      let match: RegExpExecArray | null;
      while ((match = /\r?\n\r?\n/.exec(buffer))) {
        const current = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        frame(current);
      }
      if (chunk.done) {
        if (buffer.trim()) frame(buffer);
        break;
      }
    }
    if (!done)
      throw new ApiError(
        502,
        "Ответ не завершён. Проверьте историю перед повторной отправкой.",
        {},
        "ASSISTANT_STREAM_INTERRUPTED",
      );
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
