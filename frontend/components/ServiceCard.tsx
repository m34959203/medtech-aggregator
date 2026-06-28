import Link from "next/link";
import CategoryBadge from "./CategoryBadge";
import { formatPrice } from "@/lib/format";
import { haversineKm, formatDistance } from "@/lib/distance";
import type { ServiceComparison } from "@/lib/types";

/** Расстояние до ближайшей клиники с этой услугой (по офферам), или null. */
export function nearestKm(
  service: ServiceComparison,
  coords: { lat: number; lng: number } | null | undefined,
): number | null {
  if (!coords) return null;
  let best: number | null = null;
  for (const o of service.offers || []) {
    if (o.lat == null || o.lng == null) continue;
    const d = haversineKm(coords.lat, coords.lng, o.lat, o.lng);
    if (best == null || d < best) best = d;
  }
  return best;
}

export default function ServiceCard({
  service,
  index = 0,
  city = "",
  userCoords = null,
}: {
  service: ServiceComparison;
  index?: number;
  city?: string;
  userCoords?: { lat: number; lng: number } | null;
}) {
  const spread =
    service.max_price > service.min_price
      ? Math.round(((service.max_price - service.min_price) / service.max_price) * 100)
      : 0;
  const distKm = nearestKm(service, userCoords);

  // Переносим выбранный город на страницу услуги, чтобы фильтр не слетал.
  const href = city
    ? `/service/${service.service_id}?city=${encodeURIComponent(city)}`
    : `/service/${service.service_id}`;

  return (
    <Link
      href={href}
      className="card-interactive group flex animate-fade-up flex-col gap-4 p-5"
      style={{ animationDelay: `${Math.min(index, 12) * 40}ms` }}
    >
      <div className="flex items-start justify-between gap-3">
        <CategoryBadge category={service.category} />
        <div className="flex shrink-0 items-center gap-1.5">
          {distKm != null && (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-100"
              title="До ближайшей клиники с этой услугой"
            >
              <svg viewBox="0 0 20 20" fill="none" className="h-3 w-3" aria-hidden>
                <path d="M10 18s6-5.3 6-10A6 6 0 0 0 4 8c0 4.7 6 10 6 10Z" stroke="currentColor" strokeWidth="1.6" />
                <circle cx="10" cy="8" r="2" stroke="currentColor" strokeWidth="1.6" />
              </svg>
              {formatDistance(distKm)}
            </span>
          )}
          <span className="rounded-full bg-ink-50 px-2.5 py-1 text-xs font-medium text-ink-500 ring-1 ring-inset ring-ink-100">
            {service.offers_count}{" "}
            {pluralOffers(service.offers_count)}
          </span>
        </div>
      </div>

      <div>
        <h3 className="text-base font-semibold leading-snug text-ink-900 transition group-hover:text-brand-700">
          {service.canonical_name}
        </h3>
        {service.description && (
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-ink-500">
            {service.description}
          </p>
        )}
      </div>

      <div className="mt-auto flex items-end justify-between gap-3 border-t border-ink-100 pt-4">
        <div>
          <p className="text-xs text-ink-400">от</p>
          <p className="text-[22px] font-extrabold tracking-tight text-ink-900">
            {formatPrice(service.min_price)}
          </p>
        </div>
        {spread >= 5 && (
          <span className="rounded-lg bg-brand-50 px-2.5 py-1.5 text-xs font-bold text-brand-700">
            −{spread}%
          </span>
        )}
      </div>
    </Link>
  );
}

function pluralOffers(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "клиника";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return "клиники";
  return "клиник";
}
