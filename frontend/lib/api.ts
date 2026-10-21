export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = "ApiError"; }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...options, headers, credentials: "same-origin", cache: "no-store" });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Не удалось связаться с PAXVEIL. Проверьте подключение и повторите.", 0);
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    let message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((x: { msg: string }) => x.msg).join("; ") : typeof detail?.message === "string" ? detail.message : response.status >= 500 ? "Сервис временно недоступен. Попробуйте позже." : `Не удалось выполнить действие (${response.status}). Попробуйте ещё раз.`;
    const retryAfter = Number(response.headers.get("Retry-After"));
    if (response.status === 429 && Number.isFinite(retryAfter) && retryAfter > 0) {
      message += ` Повторите ${new Intl.RelativeTimeFormat("ru-RU", { numeric: "always" }).format(Math.max(1, Math.ceil(retryAfter / 60)), "minute")}.`;
    }
    throw new ApiError(message, response.status);
  }
  return data as T;
}
export const json = (value: unknown) => JSON.stringify(value);
export const formatDate = (value?: string | null) => value ? new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "нет данных";
export function safeUrl(value: string) { try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) ? url.href : null; } catch { return null; } }
