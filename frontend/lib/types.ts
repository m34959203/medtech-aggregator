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

export interface ServiceComparison {
  service_id: number;
  canonical_name: string;
  category: string;
  offers_count: number;
  min_price: number;
  max_price: number;
  offers: PriceOffer[];
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
