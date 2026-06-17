// Типизированные хелперы для обращения к FastAPI-бэкенду агрегатора.

import type {
  ChatMessage,
  ChatResponse,
  ClinicOut,
  NormalizationPreview,
  SearchParams,
  ServiceComparison,
  SortOrder,
} from "./types";

const stripSlash = (u?: string) => u?.replace(/\/$/, "");

// На клиенте — публичный origin (same-origin: /api проксируется Next-ом на бэкенд).
// На сервере (SSR) — прямой адрес бэкенда в docker-сети, без round-trip через CF.
const PUBLIC = stripSlash(process.env.NEXT_PUBLIC_API_URL);
const INTERNAL = stripSlash(process.env.INTERNAL_API_URL);

export const API_URL =
  (typeof window === "undefined" ? INTERNAL || PUBLIC : PUBLIC) ||
  "http://localhost:8000";

function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    // Витрина — всегда свежие цены, без кэша.
    cache: "no-store",
    headers: { Accept: "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function search(params: SearchParams = {}, signal?: AbortSignal): Promise<ServiceComparison[]> {
  const query = buildQuery({
    q: params.q,
    city: params.city,
    category: params.category,
    max_price: params.max_price,
    sort: params.sort,
    limit: params.limit ?? 20,
  });
  return apiFetch<ServiceComparison[]>(`/api/search${query}`, { signal });
}

export function compare(
  serviceId: number,
  opts: { city?: string; max_price?: number; sort?: SortOrder } = {},
  signal?: AbortSignal,
): Promise<ServiceComparison> {
  const query = buildQuery({
    city: opts.city,
    max_price: opts.max_price,
    sort: opts.sort,
  });
  return apiFetch<ServiceComparison>(`/api/compare/${serviceId}${query}`, { signal });
}

export function getCategories(signal?: AbortSignal): Promise<string[]> {
  return apiFetch<string[]>("/api/categories", { signal });
}

export function getCities(signal?: AbortSignal): Promise<string[]> {
  return apiFetch<string[]>("/api/cities", { signal });
}

export function getClinics(signal?: AbortSignal): Promise<ClinicOut[]> {
  return apiFetch<ClinicOut[]>("/api/clinics", { signal });
}

export function previewNormalization(
  names: string[],
  signal?: AbortSignal,
): Promise<{ results: NormalizationPreview[] }> {
  return apiFetch<{ results: NormalizationPreview[] }>("/api/ingest/preview", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ names }),
    signal,
  });
}

export function chat(messages: ChatMessage[], signal?: AbortSignal): Promise<ChatResponse> {
  return apiFetch<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
    signal,
  });
}
