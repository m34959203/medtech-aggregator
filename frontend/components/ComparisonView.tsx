"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { compare } from "@/lib/api";
import { formatDate, formatPrice } from "@/lib/format";
import type { ServiceComparison, SortOrder } from "@/lib/types";
import CategoryBadge from "./CategoryBadge";
import SourceBadge from "./SourceBadge";
import { OfferRowSkeleton } from "./Skeletons";

// Карта только на клиенте — Яндекс.Карты обращаются к window.
const ClinicMap = dynamic(() => import("./ClinicMap"), {
  ssr: false,
  loading: () => (
    <div className="skeleton h-full min-h-[320px] w-full rounded-2xl" />
  ),
});

interface Props {
  serviceId: number;
  initial: ServiceComparison;
  cities: string[];
  initialCity?: string;
}

export default function ComparisonView({ serviceId, initial, cities, initialCity = "" }: Props) {
  const [data, setData] = useState<ServiceComparison>(initial);
  const [city, setCity] = useState(initialCity);
  const [sort, setSort] = useState<SortOrder>("price_asc");

  // Верхняя граница слайдера фиксируется по исходным данным.
  const priceCeiling = useMemo(
    () => Math.ceil((initial.max_price || 1) / 500) * 500 || 1000,
    [initial.max_price],
  );
  const [maxPrice, setMaxPrice] = useState(priceCeiling);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Клиника, выбранная кликом по карточке (или метке) — для синхронизации с картой.
  const [activeClinicId, setActiveClinicId] = useState<number | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);
  const firstRun = useRef(true);

  const refetch = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const next = await compare(
        serviceId,
        {
          city: city || undefined,
          max_price: maxPrice < priceCeiling ? maxPrice : undefined,
          sort,
        },
        controller.signal,
      );
      setData(next);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setError("Не удалось обновить данные.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [serviceId, city, maxPrice, sort, priceCeiling]);

  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    const t = setTimeout(refetch, 280);
    return () => clearTimeout(t);
  }, [refetch]);

  const offers = data.offers;
  const cheapest = useMemo(
    () =>
      offers.length
        ? offers.reduce((min, o) => (o.price < min.price ? o : min), offers[0])
        : undefined,
    [offers],
  );

  return (
    <div className="space-y-8">
      {/* Заголовок услуги */}
      <header className="space-y-3">
        <CategoryBadge category={data.category} />
        <h1 className="text-2xl font-bold tracking-tight text-ink-900 sm:text-3xl">
          {data.canonical_name}
        </h1>
        <p className="text-sm text-ink-500">
          {data.offers_count > 0 ? (
            <>
              {data.offers_count} предложений · цены от{" "}
              <span className="font-semibold text-brand-700">
                {formatPrice(data.min_price)}
              </span>{" "}
              до {formatPrice(data.max_price)}
            </>
          ) : (
            "Нет предложений по выбранным фильтрам"
          )}
        </p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Левая колонка: фильтры + список */}
        <div className="space-y-5 lg:col-span-7">
          <Filters
            cities={cities}
            city={city}
            onCity={setCity}
            sort={sort}
            onSort={setSort}
            maxPrice={maxPrice}
            onMaxPrice={setMaxPrice}
            priceCeiling={priceCeiling}
          />

          {error ? (
            <div className="card p-6 text-center text-sm text-red-600">
              {error}{" "}
              <button onClick={refetch} className="font-semibold underline">
                Повторить
              </button>
            </div>
          ) : loading ? (
            <div className="space-y-3">
              <OfferRowSkeleton />
              <OfferRowSkeleton />
              <OfferRowSkeleton />
            </div>
          ) : offers.length === 0 ? (
            <div className="card p-10 text-center text-sm text-ink-500">
              По выбранным фильтрам ничего не найдено. Попробуйте увеличить
              лимит цены или выбрать другой город.
            </div>
          ) : (
            <ul className="space-y-3">
              {offers.map((o, i) => (
                <OfferRow
                  key={`${o.clinic_id}-${i}`}
                  offer={o}
                  isCheapest={cheapest?.clinic_id === o.clinic_id && i === 0}
                  isActive={activeClinicId === o.clinic_id}
                  onSelect={() => setActiveClinicId(o.clinic_id)}
                />
              ))}
            </ul>
          )}

          <p className="rounded-xl bg-amber-50/70 px-4 py-3 text-xs leading-relaxed text-amber-800 ring-1 ring-inset ring-amber-100">
            Данные с сайтов клиник носят справочный характер. Перед визитом
            уточняйте актуальную стоимость напрямую в клинике.
          </p>
        </div>

        {/* Правая колонка: карта */}
        <div className="lg:col-span-5">
          <div className="card sticky top-20 overflow-hidden p-1.5">
            <div className="h-[420px] w-full overflow-hidden rounded-xl">
              <ClinicMap
                offers={offers}
                cheapestClinicId={cheapest?.clinic_id}
                activeClinicId={activeClinicId}
                onSelectClinic={setActiveClinicId}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface FiltersProps {
  cities: string[];
  city: string;
  onCity: (v: string) => void;
  sort: SortOrder;
  onSort: (v: SortOrder) => void;
  maxPrice: number;
  onMaxPrice: (v: number) => void;
  priceCeiling: number;
}

function Filters(p: FiltersProps) {
  return (
    <div className="card space-y-4 p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-xs font-medium text-ink-500">
            Город
          </span>
          <select
            value={p.city}
            onChange={(e) => p.onCity(e.target.value)}
            className="field py-2.5 text-sm"
          >
            <option value="">Все города</option>
            {p.cities.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>

        <div>
          <span className="mb-1.5 block text-xs font-medium text-ink-500">
            Сортировка
          </span>
          <div className="flex rounded-xl border border-ink-200 bg-white p-1 text-sm font-medium">
            <button
              type="button"
              onClick={() => p.onSort("price_asc")}
              className={`flex-1 rounded-lg px-2 py-1.5 transition ${
                p.sort === "price_asc"
                  ? "bg-brand-600 text-white"
                  : "text-ink-500 hover:text-ink-800"
              }`}
            >
              Дешевле
            </button>
            <button
              type="button"
              onClick={() => p.onSort("price_desc")}
              className={`flex-1 rounded-lg px-2 py-1.5 transition ${
                p.sort === "price_desc"
                  ? "bg-brand-600 text-white"
                  : "text-ink-500 hover:text-ink-800"
              }`}
            >
              Дороже
            </button>
          </div>
        </div>
      </div>

      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-xs font-medium text-ink-500">Цена до</span>
          <span className="text-sm font-semibold text-brand-700">
            {formatPrice(p.maxPrice)}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={p.priceCeiling}
          step={Math.max(100, Math.round(p.priceCeiling / 100))}
          value={p.maxPrice}
          onChange={(e) => p.onMaxPrice(Number(e.target.value))}
          className="h-2 w-full cursor-pointer appearance-none rounded-full bg-ink-100 accent-brand-600"
          aria-label="Максимальная цена"
        />
      </div>
    </div>
  );
}

function OfferRow({
  offer,
  isCheapest,
  isActive,
  onSelect,
}: {
  offer: import("@/lib/types").PriceOffer;
  isCheapest: boolean;
  isActive: boolean;
  onSelect: () => void;
}) {
  const confidence = Math.round(offer.match_confidence * 100);
  const liRef = useRef<HTMLLIElement>(null);
  const hasGeo = offer.lat != null && offer.lng != null;

  // Когда клиника выбрана на карте — подтягиваем её карточку в зону видимости.
  useEffect(() => {
    if (isActive && liRef.current) {
      liRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [isActive]);

  return (
    <li
      ref={liRef}
      onClick={hasGeo ? onSelect : undefined}
      role={hasGeo ? "button" : undefined}
      tabIndex={hasGeo ? 0 : undefined}
      onKeyDown={
        hasGeo
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect();
              }
            }
          : undefined
      }
      title={hasGeo ? "Показать на карте" : undefined}
      className={`card p-4 transition sm:p-5 ${
        hasGeo ? "cursor-pointer hover:border-brand-300" : ""
      } ${
        isActive
          ? "ring-2 ring-brand-500"
          : isCheapest
            ? "ring-2 ring-brand-300"
            : ""
      }`}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-ink-900">
              {offer.clinic_name}
            </h3>
            {isCheapest && (
              <span className="badge bg-brand-600 text-white">
                🏆 Лучшая цена
              </span>
            )}
          </div>
          <p className="text-sm text-ink-500">
            {[offer.district, offer.address].filter(Boolean).join(" · ") ||
              "Адрес уточняйте в клинике"}
          </p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <SourceBadge source={offer.source_type} />
            <span className="text-xs text-ink-400">
              точность сопоставления {confidence}%
            </span>
          </div>
          <p className="text-xs text-ink-400">
            Актуально с {formatDate(offer.valid_from)}
            {offer.raw_name && offer.raw_name !== offer.clinic_name ? (
              <span className="text-ink-300"> · «{offer.raw_name}»</span>
            ) : null}
          </p>
        </div>

        <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
          <p
            className={`text-2xl font-bold tracking-tight ${
              isCheapest ? "text-brand-700" : "text-ink-900"
            }`}
          >
            {formatPrice(offer.price, offer.currency)}
          </p>
          {offer.phone && (
            <a
              href={`tel:${offer.phone.replace(/[^\d+]/g, "")}`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-ink-200 px-3 py-1.5 text-sm font-medium text-ink-700 transition hover:border-brand-300 hover:text-brand-700"
            >
              <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4" aria-hidden>
                <path
                  d="M5 3h2l1.5 4-2 1.5a9 9 0 0 0 4 4l1.5-2 4 1.5v2c0 .5-.4 1-1 1A13 13 0 0 1 4 4c0-.6.4-1 1-1Z"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  strokeLinejoin="round"
                />
              </svg>
              {offer.phone}
            </a>
          )}
        </div>
      </div>
    </li>
  );
}
