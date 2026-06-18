// Типы, отражающие контракт FastAPI-бэкенда (см. app/schemas.py).

export type SourceType = "upload" | "web_scrape" | "api";
export type SortOrder = "price_asc" | "price_desc";

export interface PriceOffer {
  clinic_id: number;
  clinic_name: string;
  city: string;
  district: string;
  address: string;
  lat: number | null;
  lng: number | null;
  phone: string;
  price: number;
  currency: string;
  raw_name: string;
  source_type: SourceType;
  match_confidence: number; // 0..1
  valid_from: string; // ISO date
}

export interface ServiceVariant {
  service_id: number;
  canonical_name: string;
  label: string;
  offers_count: number;
  min_price: number;
}

export interface ServiceAttributes {
  base_key?: string;
  visit?: "primary" | "repeat" | "online" | "pediatric" | null;
  biomaterial?: "blood" | "urine" | null;
  variant?: string | null;
  tags?: string[];
}

export interface ServiceComparison {
  service_id: number;
  canonical_name: string;
  category: string;
  offers_count: number;
  min_price: number;
  max_price: number;
  offers: PriceOffer[];
  attributes?: ServiceAttributes;
  variants?: ServiceVariant[];
}

export interface ClinicOut {
  id: number;
  name: string;
  city: string;
  district: string;
  address: string;
  lat: number | null;
  lng: number | null;
  phone: string;
}

// --- Live-демо нормализатора ---
export type NormMethod = "fuzzy" | "fuzzy-weak" | "llm" | "new";

export interface NormalizationPreview {
  raw: string;
  canonical: string;
  category: string;
  confidence: number;
  method: NormMethod;
  is_new: boolean;
  candidates: string[];
}

// --- Кейс 1: админ-приём (дашборд, журнал, пакетная загрузка) ---
export interface IngestionRun {
  id: number;
  source_id: number | null;
  channel: string;
  format: string;
  status: string;
  items_found: number;
  message: string;
  created_at: string;
}

export interface IngestionStats {
  clinics: number;
  cities: number;
  services: number;
  prices: number;
  runs: number;
  needs_review: number;
  empty_runs: number;
  failed_runs: number;
  reports_new: number;
  by_source: Record<string, number>;
}

export interface BatchFileResult {
  file: string;
  status: "ok" | "empty" | "error";
  clinic_id?: number;
  format?: string;
  items?: number;
  matched?: number;
  needs_review?: number;
  run_id?: number;
  error?: string;
}

export interface BatchResult {
  files: BatchFileResult[];
  totals: { files: number; ok: number; items: number; matched: number; needs_review: number };
}

// --- Спринт-2: ревью (human-in-the-loop) ---
export interface ReviewItem {
  price_id: number;
  clinic_id: number;
  clinic_name: string;
  city: string;
  service_id: number;
  canonical_name: string;
  raw_name: string;
  price: number;
  currency: string;
  match_confidence: number;
}

export interface ReviewReport {
  id: number;
  clinic_name: string;
  service: string;
  price: number | null;
  note: string;
  created_at: string;
}

export interface ReviewQueue {
  threshold: number;
  low_confidence: ReviewItem[];
  reports: ReviewReport[];
}

// --- Чат-помощник ---
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatOffer {
  service: string;
  clinic_name: string;
  city: string;
  district: string;
  address: string;
  phone: string;
  price: number;
  currency: string;
  is_cheapest: boolean;
}

export interface ChatResponse {
  reply: string;
  offers: ChatOffer[];
  grounded: boolean;
  llm: boolean;
}

export interface SearchParams {
  q?: string;
  city?: string;
  category?: string;
  max_price?: number;
  sort?: SortOrder;
  limit?: number;
}
