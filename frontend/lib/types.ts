// Типы, отражающие контракт FastAPI-бэкенда (см. app/schemas.py).

export type SourceType = "upload" | "web_scrape" | "api";
export type SortOrder = "price_asc" | "price_desc" | "updated" | "distance";

export interface PriceOffer {
  clinic_id: string; // uuid клиники (§2.2)
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
  // --- §3.3: расширенный контракт оффера ---
  working_hours?: string | null;
  website?: string | null;
  source_url?: string | null;
  rating?: number | null;
  online_booking?: boolean | null;
  duration_days?: number | null;
  is_active?: boolean | null;
  parsed_at?: string | null;
  price_original?: number | null;
  currency_original?: string | null;
}

export interface ServiceVariant {
  service_id: string; // uuid услуги (§2.2)
  canonical_name: string;
  label: string;
  offers_count: number;
  min_price: number;
}

// --- §3.4: сравнительная таблица клиник по выбранным услугам ---
export interface CompareCell {
  service_id: string;
  found: boolean;
  price: number | null;
  is_best: boolean; // лучшая цена по услуге среди клиник → 🏆
  source_url?: string;
  source_type?: string;
  parsed_at?: string | null;
  freshness_days?: number | null;
}

export interface CompareColumn {
  clinic_id: string;
  clinic_name: string;
  city: string;
  address: string;
  phone: string;
  lat: number | null;
  lng: number | null;
  rating: number | null;
  online_booking: boolean | null;
  working_hours: string;
  website: string;
  distance_km: number | null;
  cells: CompareCell[]; // по одной на каждую услугу из services (в порядке)
  total: number;
  found_count: number;
  covers_all: boolean;
  savings_vs_max: number;
}

export interface ServiceMini {
  service_id: string;
  canonical_name: string;
}

export interface CompareRecommendation {
  clinic_id: string;
  clinic_name: string;
  label: string;
}

export interface ClinicComparison {
  services: ServiceMini[];
  clinics: CompareColumn[];
  max_total: number;
  recommendations: {
    cheapest?: CompareRecommendation;
    nearest?: CompareRecommendation;
    best_balance?: CompareRecommendation;
  };
}

export interface ClinicCompareRequest {
  service_ids: string[];
  clinic_ids?: string[] | null;
  city?: string | null;
  user_lat?: number | null;
  user_lng?: number | null;
  require_all?: boolean;
}

export interface ServiceAttributes {
  base_key?: string;
  visit?: "primary" | "repeat" | "online" | "pediatric" | null;
  biomaterial?: "blood" | "urine" | null;
  variant?: string | null;
  tags?: string[];
}

export interface PriceTrend {
  points: { date: string; median: number }[];
  change_pct: number;
  direction: "up" | "down" | "flat";
}

export interface ServiceOntology {
  code: string;
  group: string;
  osms: boolean;
}

export type CategoryEnum = "лаборатория" | "приём врача" | "диагностика" | "процедура";

export interface ServiceComparison {
  service_id: string; // uuid услуги (§2.2)
  canonical_name: string;
  category: string;
  category_enum?: CategoryEnum | string | null;
  offers_count: number;
  min_price: number;
  max_price: number;
  offers: PriceOffer[];
  attributes?: ServiceAttributes;
  variants?: ServiceVariant[];
  price_trend?: PriceTrend | null;
  ontology?: ServiceOntology | null;
}

export interface ClinicOut {
  id: string; // uuid клиники (§2.2)
  name: string;
  city: string;
  district: string;
  address: string;
  lat: number | null;
  lng: number | null;
  phone: string;
}

// --- Live-демо нормализатора (новый контракт POST /api/ingest/preview) ---
// "panel" — исходная строка-панель разбита движком на несколько услуг.
export type NormMethod = "fuzzy" | "fuzzy-weak" | "semantic" | "llm" | "panel" | "new";

// Один распознанный элемент внутри строки направления.
export interface NormItem {
  canonical: string;
  category: string;
  confidence: number; // 0..1
  method: NormMethod;
  status: "matched" | "unmatched";
}

// Одна строка исходного направления после разбора.
// kind="noise" — служебная строка (дата/инструкция/заголовок), отфильтрована; items пуст.
// kind="service" — содержит 1..N распознанных услуг (несколько = панель).
export interface NormalizationLine {
  raw: string;
  kind: "service" | "noise";
  reason?: string;
  items: NormItem[];
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
  clinic_id?: string; // uuid клиники (§2.2)
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
  clinic_id: string; // uuid клиники (§2.2)
  clinic_name: string;
  city: string;
  service_id: string; // uuid услуги (§2.2)
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

// --- Спринт-3: портал клиники (self-service) ---
export interface PortalPrice {
  price_id: number;
  service: string;
  category: string;
  raw_name: string;
  price: number;
  currency: string;
  source_type: SourceType;
  confirmed: boolean;
  valid_from: string;
}

export interface PortalView {
  clinic: { id: string; name: string; city: string; district: string; address: string; phone: string };
  prices: PortalPrice[];
  confirmed_count: number;
}

// --- Спринт-3: корзина-рецепт ---
export interface BasketCheapest {
  clinic_id: string; // uuid клиники (§2.2)
  clinic_name: string;
  city: string;
  address: string;
  phone: string;
  price: number;
}

export interface BasketItem {
  input: string;
  service_id: string; // uuid услуги (§2.2)
  canonical: string;
  confidence: number;
  offers_count: number;
  cheapest: BasketCheapest | null;
}

export interface BasketSingleClinic {
  clinic_id: string; // uuid клиники (§2.2)
  clinic_name: string;
  city: string;
  phone: string;
  address: string;
  covered: number;
  total: number;
  missing: string[];
}

export interface BasketResult {
  recognized: BasketItem[];
  unrecognized: string[];
  services_found: number;
  total_cheapest_mixed: number;
  best_single_clinic: BasketSingleClinic | null;
  city: string | null;
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
  min_price?: number;
  max_price?: number;
  min_rating?: number;
  online_booking?: boolean;
  user_lat?: number;
  user_lng?: number;
  sort?: SortOrder;
  limit?: number;
}

// --- §3.3: профиль клиники (все услуги) ---
export interface ClinicProfileService {
  name: string;
  price: number;
  currency: string;
  duration_days: number | null;
  source_type: SourceType;
  valid_from: string;
  is_active: boolean;
}

export interface ClinicProfile {
  id: string; // uuid клиники (§2.2)
  name: string;
  city: string;
  address: string;
  phone: string;
  working_hours: string | null;
  website: string | null;
  rating: number | null;
  online_booking: boolean;
  lat: number | null;
  lng: number | null;
  services_count: number;
  services: ClinicProfileService[];
}
