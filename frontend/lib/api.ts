// Типизированные хелперы для обращения к FastAPI-бэкенду агрегатора.

import type {
  BatchResult,
  ChatMessage,
  ChatResponse,
  ClinicOut,
  ClinicProfile,
  IngestionRun,
  IngestionStats,
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
    min_price: params.min_price,
    max_price: params.max_price,
    min_rating: params.min_rating,
    online_booking: params.online_booking === undefined ? undefined : String(params.online_booking),
    user_lat: params.user_lat,
    user_lng: params.user_lng,
    sort: params.sort,
    limit: params.limit ?? 20,
  });
  return apiFetch<ServiceComparison[]>(`/api/search${query}`, { signal });
}

// Автодополнение строки поиска по официальному справочнику.
export function suggest(q: string, limit = 10, signal?: AbortSignal): Promise<string[]> {
  const query = buildQuery({ q, limit });
  return apiFetch<string[]>(`/api/suggest${query}`, { signal });
}

export interface CompareOpts {
  city?: string;
  min_price?: number;
  max_price?: number;
  min_rating?: number;
  online_booking?: boolean;
  user_lat?: number;
  user_lng?: number;
  sort?: SortOrder;
}

export function compare(
  serviceId: number,
  opts: CompareOpts = {},
  signal?: AbortSignal,
): Promise<ServiceComparison> {
  const query = buildQuery({
    city: opts.city,
    min_price: opts.min_price,
    max_price: opts.max_price,
    min_rating: opts.min_rating,
    online_booking: opts.online_booking === undefined ? undefined : String(opts.online_booking),
    user_lat: opts.user_lat,
    user_lng: opts.user_lng,
    sort: opts.sort,
  });
  return apiFetch<ServiceComparison>(`/api/compare/${serviceId}${query}`, { signal });
}

// Профиль клиники со всеми услугами.
export function getClinicProfile(id: number, signal?: AbortSignal): Promise<ClinicProfile> {
  return apiFetch<ClinicProfile>(`/api/clinics/${id}/profile`, { signal });
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

export function getServices(
  signal?: AbortSignal,
): Promise<{ id: number; canonical_name: string; category: string }[]> {
  return apiFetch("/api/services?limit=200", { signal });
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

// --- Кейс 1: админ-приём ---
export function getIngestionStats(signal?: AbortSignal): Promise<IngestionStats> {
  return apiFetch<IngestionStats>("/api/ingest/stats", { signal });
}

export function getIngestionRuns(limit = 50, signal?: AbortSignal): Promise<IngestionRun[]> {
  return apiFetch<IngestionRun[]>(`/api/ingest/runs?limit=${limit}`, { signal });
}

export function uploadBatch(files: File[], clinicId?: number): Promise<BatchResult> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  if (clinicId != null) form.append("clinic_id", String(clinicId));
  return apiFetch<BatchResult>("/api/ingest/upload-batch", { method: "POST", body: form });
}

// Прямая ссылка на скачивание (same-origin: /api проксируется Next-ом на бэкенд).
export function catalogExportUrl(format: "xlsx" | "csv"): string {
  return `/api/export/catalog?format=${format}`;
}

// --- Спринт-2: ревью и лиды ---
import type { ReviewQueue } from "./types";

export function getReviewQueue(signal?: AbortSignal): Promise<ReviewQueue> {
  return apiFetch<ReviewQueue>("/api/review/queue", { signal });
}

export function reviewPrice(
  priceId: number,
  action: "confirm" | "reassign" | "reject",
  targetServiceId?: number,
): Promise<unknown> {
  return apiFetch(`/api/review/price/${priceId}`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ action, target_service_id: targetServiceId }),
  });
}

export function reviewReport(reportId: number, status: "reviewed" | "fixed"): Promise<unknown> {
  return apiFetch(`/api/review/report/${reportId}`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

export function createLead(lead: {
  clinic_id?: number;
  clinic_name?: string;
  service?: string;
  price?: number;
  name?: string;
  phone?: string;
}): Promise<unknown> {
  return apiFetch("/api/leads", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(lead),
  });
}

// --- Безопасность: админ-авторизация (passwordless токен → httpOnly cookie) ---
export function authMe(signal?: AbortSignal): Promise<{ authenticated: boolean; configured: boolean }> {
  return apiFetch("/api/auth/me", { signal });
}

export function authLogin(token: string): Promise<{ ok: boolean }> {
  return apiFetch("/api/auth/login", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
}

export function authLogout(): Promise<unknown> {
  return apiFetch("/api/auth/logout", { method: "POST" });
}

// --- Спринт-3: корзина-рецепт ---
import type { BasketResult, PortalView } from "./types";

export function recommendBasket(input: {
  text?: string;
  names?: string[];
  city?: string;
}): Promise<BasketResult> {
  return apiFetch<BasketResult>("/api/basket/recommend", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function recommendBasketFile(file: File, city?: string): Promise<BasketResult> {
  const form = new FormData();
  form.append("file", file);
  if (city) form.append("city", city);
  return apiFetch<BasketResult>("/api/basket/recommend-file", { method: "POST", body: form });
}

// --- Спринт-3: портал клиники ---

export function issuePortalAccess(
  clinicId: number,
): Promise<{ clinic_id: number; clinic_name: string; token: string; portal_path: string }> {
  return apiFetch(`/api/portal/issue/${clinicId}`, { method: "POST" });
}

export function getPortal(token: string, signal?: AbortSignal): Promise<PortalView> {
  return apiFetch<PortalView>(`/api/portal/${token}`, { signal });
}

export function editPortalPrice(token: string, priceId: number, price: number): Promise<unknown> {
  return apiFetch(`/api/portal/${token}/price/${priceId}`, {
    method: "PATCH",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ price }),
  });
}

export function confirmAllPortal(token: string): Promise<{ confirmed: number }> {
  return apiFetch(`/api/portal/${token}/confirm-all`, { method: "POST" });
}

export function uploadPortalPricelist(token: string, file: File): Promise<unknown> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch(`/api/portal/${token}/upload`, { method: "POST", body: form });
}

// --- Петля обратной связи «цена неверная» ---
export function reportPrice(report: {
  clinic_id?: number;
  clinic_name?: string;
  service?: string;
  price?: number;
  note?: string;
}): Promise<unknown> {
  return apiFetch("/api/feedback/price-report", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(report),
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

// --- WhatsApp-туннель (admin) ---
export interface WaStatus {
  status: "disconnected" | "connecting" | "qr_ready" | "connected";
  phoneNumber: string | null;
  qrCode: string | null; // data-URL QR для привязки телефона
}
export interface WaLimits {
  dailyLimit: number;
  sentLast24h: number;
  remaining: number;
  humanize: boolean;
  requireClientInitiated: boolean;
  queueDepth: number;
}

export function waStatus(signal?: AbortSignal): Promise<WaStatus> {
  return apiFetch<WaStatus>("/api/wa/status", { signal });
}
export function waConnect(): Promise<{ status: string; qrCode?: string | null }> {
  return apiFetch("/api/wa/connect", { method: "POST" });
}
export function waDisconnect(): Promise<unknown> {
  return apiFetch("/api/wa/disconnect", { method: "POST" });
}
export function waLogout(): Promise<unknown> {
  return apiFetch("/api/wa/logout", { method: "POST" });
}
export function waLimits(signal?: AbortSignal): Promise<WaLimits> {
  return apiFetch<WaLimits>("/api/wa/limits", { signal });
}
