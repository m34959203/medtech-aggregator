import Link from "next/link";
import CategoryBadge from "./CategoryBadge";
import { formatPrice } from "@/lib/format";
import type { ServiceComparison } from "@/lib/types";

export default function ServiceCard({
  service,
  index = 0,
  city = "",
}: {
  service: ServiceComparison;
  index?: number;
  city?: string;
}) {
  const spread =
    service.max_price > service.min_price
      ? Math.round(((service.max_price - service.min_price) / service.max_price) * 100)
      : 0;

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
        <span className="rounded-full bg-ink-50 px-2.5 py-1 text-xs font-medium text-ink-500 ring-1 ring-inset ring-ink-100">
          {service.offers_count}{" "}
          {pluralOffers(service.offers_count)}
        </span>
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
          <p className="text-xl font-bold tracking-tight text-ink-900">
            {formatPrice(service.min_price)}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          {spread > 0 && (
            <span className="text-xs font-medium text-brand-600">
              экономия до {spread}%
            </span>
          )}
          <span className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 transition group-hover:gap-2">
            Сравнить
            <svg
              viewBox="0 0 20 20"
              fill="none"
              className="h-4 w-4"
              aria-hidden
            >
              <path
                d="M4 10h12m0 0-4-4m4 4-4 4"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
        </div>
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
