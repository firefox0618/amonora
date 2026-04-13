import { ApiEnvelope } from "@/lib/types";

export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || "";
const API_PREFIX = `${BASE_PATH}/api/proxy/dashboard/api/v2`;

function buildHeaders(init?: RequestInit, hasFormData = false) {
  const headers = new Headers(init?.headers || {});
  if (!hasFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return headers;
}

function redirectToLoginOnUnauthorized() {
  if (typeof window === "undefined") {
    return;
  }
  const loginPath = `${BASE_PATH}/login?notice=${encodeURIComponent("Сессия истекла. Войди заново.")}`;
  const authPaths = new Set([`${BASE_PATH}/login`, `${BASE_PATH}/verify`]);
  if (!authPaths.has(window.location.pathname)) {
    window.location.assign(loginPath);
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const hasFormData = typeof FormData !== "undefined" && init?.body instanceof FormData;
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    credentials: "include",
    headers: buildHeaders(init, hasFormData),
    cache: "no-store",
  });

  let payload: ApiEnvelope<T>;
  const rawText = await response.text();
  try {
    payload = JSON.parse(rawText) as ApiEnvelope<T>;
  } catch {
    const snippet = rawText.trim().slice(0, 180);
    if (response.status === 401) {
      redirectToLoginOnUnauthorized();
    }
    throw new Error(snippet ? `Не удалось обработать ответ сервера: ${snippet}` : "Не удалось обработать ответ сервера");
  }

  if (response.status === 401) {
    redirectToLoginOnUnauthorized();
  }
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || "Запрос завершился с ошибкой");
  }

  return payload.data;
}

export function apiGet<T>(path: string) {
  return apiFetch<T>(path);
}

export function apiPost<T>(path: string, body?: unknown, init?: RequestInit) {
  return apiFetch<T>(path, {
    ...init,
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
}

export function apiUpload<T>(path: string, formData: FormData, init?: RequestInit) {
  return apiFetch<T>(path, {
    ...init,
    method: "POST",
    body: formData,
  });
}
