export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fields: Record<string, string> = {},
    public code = "",
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers:
        body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (e instanceof Error && e.name === "AbortError") throw e;
    throw new ApiError(
      0,
      "Не удалось связаться с сервером. Проверьте подключение и повторите действие.",
    );
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    if (r.status === 401 && !path.startsWith("/auth/"))
      window.dispatchEvent(new Event("delo:session-expired"));
    throw new ApiError(
      r.status,
      data?.error?.message ||
        "Не удалось выполнить действие. Повторите попытку.",
      data?.error?.fields || {},
      data?.error?.code || "",
    );
  }
  return data as T;
}
export const money = (v: number | null | undefined) =>
  v == null ? "—" : `${new Intl.NumberFormat("ru-RU").format(v)} ₽`;
export const number = (v: number | null | undefined) =>
  v == null ? "—" : new Intl.NumberFormat("ru-RU").format(v);
export const percent = (v: number | null | undefined) =>
  v == null
    ? "—"
    : `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(v)} %`;
export function date(v: string | null | undefined, time = false) {
  if (!v) return "—";
  const utc = /T/.test(v) && !/(Z|[+-]\d\d:\d\d)$/.test(v) ? v + "Z" : v;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    ...(time ? { hour: "2-digit", minute: "2-digit" } : { year: "numeric" }),
  }).format(new Date(utc));
}
