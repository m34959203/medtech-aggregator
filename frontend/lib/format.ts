import type { SourceType } from "./types";

const tengeFmt = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 0,
});

/** Форматирует цену в тенге: 12500 → «12 500 ₸». */
export function formatPrice(value: number, currency = "KZT"): string {
  const symbol = currency === "KZT" ? "₸" : currency;
  return `${tengeFmt.format(Math.round(value))} ${symbol}`;
}

const dateFmt = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

/** «2026-01-15» → «15 января 2026 г.» */
export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return dateFmt.format(d);
}

export interface SourceMeta {
  label: string;
  /** Классы Tailwind для бейджа. */
  className: string;
  dot: string;
}

export function sourceMeta(source: SourceType): SourceMeta {
  switch (source) {
    case "upload":
      return {
        label: "Официально от клиники",
        className: "bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-200",
        dot: "bg-brand-500",
      };
    case "web_scrape":
      return {
        label: "С сайта клиники",
        className: "bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200",
        dot: "bg-amber-500",
      };
    case "api":
      return {
        label: "API",
        className: "bg-sky-50 text-sky-700 ring-1 ring-inset ring-sky-200",
        dot: "bg-sky-500",
      };
    default:
      return {
        label: source,
        className: "bg-ink-100 text-ink-600 ring-1 ring-inset ring-ink-200",
        dot: "bg-ink-400",
      };
  }
}
