"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { ApiError, compare, createLead, reportPrice, subscribePrice } from "@/lib/api";
import { formatDate, formatPrice } from "@/lib/format";
import type { PriceTrend, ServiceComparison, ServiceVariant, SortOrder } from "@/lib/types";
import CategoryBadge from "./CategoryBadge";
import SourceBadge from "./SourceBadge";
import ServiceComparePanel from "./ServiceComparePanel";
import { OfferRowSkeleton } from "./Skeletons";

// Карта только на клиенте — Яндекс.Карты обращаются к window.
const ClinicMap = dynamic(() => import("./ClinicMap"), {
  ssr: false,
  loading: () => (
    <div className="skeleton h-full min-h-[320px] w-full rounded-2xl" />
  ),
});

interface Props {
  serviceId: string; // uuid услуги (§2.2)
  initial: ServiceComparison;
  cities: string[];
  initialCity?: string;
  highlightClinicId?: string; // приход из чата (?clinic=) — подсветить оффер
}

export default function ComparisonView({ serviceId, initial, cities, initialCity = "", highlightClinicId }: Props) {
  const [data, setData] = useState<ServiceComparison>(initial);
  const [city, setCity] = useState(initialCity);
  const [sort, setSort] = useState<SortOrder>("price_asc");

  // Верхняя граница слайдера фиксируется по исходным данным.
  const priceCeiling = useMemo(
    () => Math.ceil((initial.max_price || 1) / 500) * 500 || 1000,
    [initial.max_price],
  );
  const [minPrice, setMinPrice] = useState(0);
  const [maxPrice, setMaxPrice] = useState(priceCeiling);
  const [minRating, setMinRating] = useState(0);
  const [onlineOnly, setOnlineOnly] = useState(false);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [geoState, setGeoState] = useState<"idle" | "loading" | "denied" | "ready">("idle");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Клиника, выбранная кликом по карточке (или метке) — для синхронизации с картой.
  // Стартовое значение — из чата (?clinic=): сразу подсветить и подскроллить оффер.
  const [activeClinicId, setActiveClinicId] = useState<string | undefined>(highlightClinicId);
  // Мультивыбор клиник для панели сравнения (макс. 4).
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length >= 4 ? prev : [...prev, id],
    );
  }, []);
  const abortRef = useRef<AbortController | null>(null);
  const firstRun = useRef(true);

  // Геолокация — нужна для сортировки «по расстоянию».
  const requestGeo = useCallback(() => {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      setGeoState("denied");
      return;
    }
    setGeoState("loading");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setGeoState("ready");
      },
      () => setGeoState("denied"),
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300_000 },
    );
  }, []);

  useEffect(() => {
    if (sort === "distance" && !coords && geoState === "idle") requestGeo();
  }, [sort, coords, geoState, requestGeo]);

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
          min_price: minPrice > 0 ? minPrice : undefined,
          max_price: maxPrice < priceCeiling ? maxPrice : undefined,
          min_rating: minRating > 0 ? minRating : undefined,
          online_booking: onlineOnly ? true : undefined,
          user_lat: sort === "distance" ? coords?.lat : undefined,
          user_lng: sort === "distance" ? coords?.lng : undefined,
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
  }, [serviceId, city, minPrice, maxPrice, minRating, onlineOnly, sort, coords, priceCeiling]);

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
        <div className="flex flex-wrap items-center gap-1.5">
          {data.ontology && (
            <>
              <span className="rounded-full bg-ink-100 px-2.5 py-0.5 text-xs font-medium text-ink-600">
                {data.ontology.group}
              </span>
              {data.ontology.osms ? (
                <span
                  className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700"
                  title="Услуга обычно покрывается ОСМС (справочно, по показаниям/направлению)"
                >
                  входит в ОСМС
                </span>
              ) : (
                <span
                  className="rounded-full bg-ink-50 px-2.5 py-0.5 text-xs font-medium text-ink-500"
                  title="Обычно не входит в базовый пакет ОСМС или по квоте/направлению"
                >
                  вне ОСМС
                </span>
              )}
            </>
          )}
          {data.attributes?.tags?.map((t) => (
            <span
              key={t}
              className="rounded-full bg-ink-100 px-2.5 py-0.5 text-xs font-medium text-ink-600"
            >
              {t}
            </span>
          ))}
        </div>
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

      <div className="flex flex-col gap-4 lg:flex-row lg:items-stretch lg:justify-between">
        <PriceTrendBlock trend={data.price_trend} />
        <SubscribePriceBlock
          serviceId={data.service_id}
          serviceName={data.canonical_name}
          city={city}
        />
      </div>
      <VariantsBar variants={data.variants} city={city} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Левая колонка: фильтры + список */}
        <div className="space-y-5 lg:col-span-7">
          <Filters
            cities={cities}
            city={city}
            onCity={setCity}
            sort={sort}
            onSort={setSort}
            minPrice={minPrice}
            onMinPrice={setMinPrice}
            maxPrice={maxPrice}
            onMaxPrice={setMaxPrice}
            priceCeiling={priceCeiling}
            minRating={minRating}
            onMinRating={setMinRating}
            onlineOnly={onlineOnly}
            onOnlineOnly={setOnlineOnly}
            geoState={geoState}
            onRetryGeo={requestGeo}
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
                  serviceName={data.canonical_name}
                  selected={selectedIds.includes(o.clinic_id)}
                  onToggleSelect={() => toggleSelect(o.clinic_id)}
                  selectionDisabled={selectedIds.length >= 4 && !selectedIds.includes(o.clinic_id)}
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

      <ServiceComparePanel
        offers={offers}
        selectedIds={selectedIds}
        coords={coords}
        serviceName={data.canonical_name}
        onRemove={toggleSelect}
        onClear={() => setSelectedIds([])}
        onRequestGeo={requestGeo}
      />
    </div>
  );
}

function LeadButton({
  serviceName,
  offer,
}: {
  serviceName: string;
  offer: import("@/lib/types").PriceOffer;
}) {
  const [open, setOpen] = useState(false);
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");

  if (state === "done") {
    return <p className="text-xs text-emerald-600">Заявка принята — клиника свяжется с вами.</p>;
  }
  if (!open) {
    return (
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
        className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-brand-700"
      >
        Записаться
      </button>
    );
  }
  return (
    <form
      onClick={(e) => e.stopPropagation()}
      onSubmit={async (e) => {
        e.preventDefault();
        if (state === "sending") return;
        setState("sending");
        try {
          await createLead({
            clinic_id: offer.clinic_id,
            clinic_name: offer.clinic_name,
            service: serviceName,
            price: offer.price,
            name,
            phone,
          });
          setState("done");
        } catch {
          setState("error");
        }
      }}
      className="flex w-full flex-col gap-1.5 sm:w-56"
    >
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Имя"
        className="field py-1.5 text-sm"
      />
      <input
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
        placeholder="Телефон*"
        inputMode="tel"
        required
        className="field py-1.5 text-sm"
      />
      <button
        type="submit"
        disabled={state === "sending"}
        className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
      >
        {state === "sending" ? "Отправляю…" : "Оставить заявку"}
      </button>
      {state === "error" && <p className="text-xs text-red-600">Проверьте телефон.</p>}
    </form>
  );
}

function ReportPriceButton({
  serviceName,
  offer,
}: {
  serviceName: string;
  offer: import("@/lib/types").PriceOffer;
}) {
  const [state, setState] = useState<"idle" | "sending" | "done">("idle");
  if (state === "done") {
    return <p className="text-xs text-emerald-600">Спасибо! Передали на проверку.</p>;
  }
  return (
    <button
      type="button"
      onClick={async (e) => {
        e.stopPropagation(); // не триггерить выбор клиники на карте
        if (state === "sending") return;
        setState("sending");
        try {
          await reportPrice({
            clinic_id: offer.clinic_id,
            clinic_name: offer.clinic_name,
            service: serviceName,
            price: offer.price,
          });
          setState("done");
        } catch {
          setState("idle");
        }
      }}
      className="text-xs text-ink-400 underline-offset-2 transition hover:text-amber-600 hover:underline"
    >
      {state === "sending" ? "Отправляю…" : "⚠ Цена неверная?"}
    </button>
  );
}

// «2026-01-15» → «15.01» (день.месяц)
function formatDayMonth(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}.${mm}`;
}

function PriceTrendBlock({ trend }: { trend?: PriceTrend | null }) {
  // Уникальный id градиента — на случай нескольких графиков на странице.
  const gradId = useId();
  if (!trend || trend.points.length < 2) return null;

  const vals = trend.points.map((p) => p.median);
  const min = Math.min(...vals);
  const max = Math.max(...vals);

  // viewBox в «логических» единицах, реальный размер тянется CSS-ом.
  const w = 480;
  const h = 96;
  const padX = 8;
  const padTop = 10;
  const padBottom = 10;
  const span = max - min || 1;
  const n = trend.points.length;

  const xy = trend.points.map((p, i) => {
    const x = padX + (i * (w - 2 * padX)) / (n - 1);
    const y = padTop + (1 - (p.median - min) / span) * (h - padTop - padBottom);
    return { x, y, ...p };
  });

  const line = xy.map((q) => `${q.x.toFixed(1)},${q.y.toFixed(1)}`).join(" ");
  // Замкнутая область под линией для заливки.
  const area =
    `${padX},${h - padBottom} ` +
    line +
    ` ${(w - padX).toFixed(1)},${h - padBottom}`;

  const flat = trend.direction === "flat";
  const up = trend.direction === "up";
  const color = flat ? "#64748b" : up ? "#dc2626" : "#059669";
  const label = flat
    ? "цена стабильна"
    : `цена ${up ? "выросла" : "снизилась"} на ${Math.abs(trend.change_pct)}%`;

  // Промежуточные подписи дат для длинного ряда (берём 1-2 точки в середине).
  const tickIdx = new Set<number>([0, n - 1]);
  if (n >= 5) tickIdx.add(Math.floor((n - 1) / 2));
  if (n >= 8) {
    tickIdx.add(Math.floor((n - 1) / 3));
    tickIdx.add(Math.floor((2 * (n - 1)) / 3));
  }

  return (
    <div className="card w-full p-4 lg:max-w-[520px]">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="text-sm font-semibold text-ink-900">Динамика цены</h2>
        <span className="text-xs font-medium" style={{ color }}>
          {label} <span className="text-ink-400">за период</span>
        </span>
      </div>

      <div className="relative">
        <svg
          viewBox={`0 0 ${w} ${h}`}
          className="h-[88px] w-full"
          preserveAspectRatio="none"
          role="img"
          aria-label={`График динамики цены: ${label}`}
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity="0.18" />
              <stop offset="100%" stopColor={color} stopOpacity="0" />
            </linearGradient>
          </defs>
          <polygon points={area} fill={`url(#${gradId})`} stroke="none" />
          <polyline
            points={line}
            fill="none"
            stroke={color}
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
          {xy.map((q, i) => (
            <circle
              key={i}
              cx={q.x}
              cy={q.y}
              r="2.6"
              fill="#fff"
              stroke={color}
              strokeWidth="1.6"
              vectorEffect="non-scaling-stroke"
            >
              <title>{`${formatDayMonth(q.date)}: ${formatPrice(q.median)}`}</title>
            </circle>
          ))}
        </svg>
      </div>

      {/* Ось X: даты под крайними (и при длинном ряде — промежуточными) точками */}
      <div className="mt-1.5 flex justify-between text-[11px] text-ink-400">
        {xy.map((q, i) =>
          tickIdx.has(i) ? (
            <span key={i}>{formatDayMonth(q.date)}</span>
          ) : null,
        )}
      </div>

      {/* Ось Y: подсказка по диапазону медианной цены */}
      <p className="mt-2 border-t border-ink-100 pt-2 text-[11px] text-ink-500">
        min <span className="font-semibold text-ink-700">{formatPrice(min)}</span>
        <span className="px-1 text-ink-300">·</span>
        max <span className="font-semibold text-ink-700">{formatPrice(max)}</span>
      </p>
    </div>
  );
}

function SubscribePriceBlock({
  serviceId,
  serviceName,
  city,
}: {
  serviceId: string;
  serviceName: string;
  city: string;
}) {
  const [open, setOpen] = useState(false);
  const [phone, setPhone] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done">("idle");
  const [result, setResult] = useState<{ already?: boolean; tracking_price?: number | null } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const digits = phone.replace(/\D/g, "").length;
  const canSubmit = digits >= 10 && state !== "sending";

  if (state === "done") {
    const trackingPrice = result?.tracking_price ?? null;
    return (
      <div className="flex items-center rounded-xl border border-emerald-200 bg-emerald-50/70 px-4 py-3 lg:max-w-xs">
        <p className="text-sm font-medium text-emerald-700">
          {result?.already
            ? "✓ Вы уже подписаны."
            : `✓ Подписка оформлена. Отслеживаем минимум${trackingPrice ? ` ${formatPrice(trackingPrice)}` : ""}.`}
        </p>
      </div>
    );
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex h-fit items-center justify-center gap-1.5 self-start rounded-full border border-brand-200 bg-brand-50 px-4 py-2 text-sm font-semibold text-brand-700 transition hover:border-brand-300 hover:bg-brand-100"
      >
        🔔 Подписаться на снижение цены
      </button>
    );
  }

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        if (!canSubmit) return;
        setState("sending");
        setError(null);
        try {
          const res = await subscribePrice({
            service_id: serviceId,
            city: city || null,
            phone,
          });
          setResult({ already: res.already, tracking_price: res.tracking_price });
          setState("done");
        } catch (err) {
          setState("idle");
          setError(
            err instanceof ApiError ? err.message : "Не удалось оформить подписку. Попробуйте позже.",
          );
        }
      }}
      className="flex w-full flex-col gap-2 rounded-xl border border-ink-100 bg-white p-4 lg:max-w-xs"
    >
      <p className="text-sm font-semibold text-ink-900">🔔 Снижение цены</p>
      <p className="text-xs leading-relaxed text-ink-500">
        Сообщим в WhatsApp, когда цена на «{serviceName}» снизится.
      </p>
      <input
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
        placeholder="+7 707 123 45 67"
        inputMode="tel"
        autoFocus
        className="field py-2 text-sm"
        aria-label="Номер телефона для уведомления"
      />
      <button
        type="submit"
        disabled={!canSubmit}
        className="rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
      >
        {state === "sending" ? "Оформляю…" : "Подписаться"}
      </button>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </form>
  );
}

function VariantsBar({ variants, city }: { variants?: ServiceVariant[]; city: string }) {
  if (!variants || variants.length === 0) return null;
  const href = (id: string) =>
    city ? `/service/${id}?city=${encodeURIComponent(city)}` : `/service/${id}`;
  return (
    <div className="rounded-xl border border-ink-100 bg-ink-50/60 px-4 py-3">
      <p className="mb-2 text-xs font-medium text-ink-500">
        Другие варианты этой услуги — это разные продукты, сравниваются отдельно:
      </p>
      <div className="flex flex-wrap gap-2">
        {variants.map((v) => (
          <Link
            key={v.service_id}
            href={href(v.service_id)}
            className="inline-flex items-center gap-1.5 rounded-full border border-ink-200 bg-white px-3 py-1.5 text-xs font-medium text-ink-700 transition hover:border-brand-300 hover:text-brand-700"
          >
            {v.canonical_name}
            <span className="text-ink-400">от {formatPrice(v.min_price)}</span>
          </Link>
        ))}
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
  minPrice: number;
  onMinPrice: (v: number) => void;
  maxPrice: number;
  onMaxPrice: (v: number) => void;
  priceCeiling: number;
  minRating: number;
  onMinRating: (v: number) => void;
  onlineOnly: boolean;
  onOnlineOnly: (v: boolean) => void;
  geoState: "idle" | "loading" | "denied" | "ready";
  onRetryGeo: () => void;
}

const SORT_OPTIONS: { value: SortOrder; label: string }[] = [
  { value: "price_asc", label: "Сначала дешевле" },
  { value: "price_desc", label: "Сначала дороже" },
  { value: "updated", label: "По дате обновления" },
  { value: "distance", label: "По расстоянию" },
];

function Filters(p: FiltersProps) {
  const priceStep = Math.max(100, Math.round(p.priceCeiling / 100));
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

        <label className="block">
          <span className="mb-1.5 block text-xs font-medium text-ink-500">
            Сортировка
          </span>
          <select
            value={p.sort}
            onChange={(e) => p.onSort(e.target.value as SortOrder)}
            className="field py-2.5 text-sm"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {p.sort === "distance" && p.geoState !== "ready" && (
        <p className="rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-500">
          {p.geoState === "loading"
            ? "Определяем ваше местоположение…"
            : p.geoState === "denied"
              ? (
                <>
                  Не удалось получить геолокацию.{" "}
                  <button
                    type="button"
                    onClick={p.onRetryGeo}
                    className="font-semibold text-brand-700 underline"
                  >
                    Разрешить доступ
                  </button>
                </>
              )
              : "Для сортировки по расстоянию нужен доступ к геолокации."}
        </p>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-xs font-medium text-ink-500">
            Рейтинг клиники
          </span>
          <select
            value={p.minRating}
            onChange={(e) => p.onMinRating(Number(e.target.value))}
            className="field py-2.5 text-sm"
          >
            <option value={0}>Любой</option>
            <option value={3}>от 3,0 ★</option>
            <option value={3.5}>от 3,5 ★</option>
            <option value={4}>от 4,0 ★</option>
            <option value={4.5}>от 4,5 ★</option>
          </select>
        </label>

        <label className="flex cursor-pointer items-center gap-2.5 self-end rounded-xl border border-ink-200 bg-white px-3 py-2.5">
          <input
            type="checkbox"
            checked={p.onlineOnly}
            onChange={(e) => p.onOnlineOnly(e.target.checked)}
            className="h-4 w-4 rounded accent-brand-600"
          />
          <span className="text-sm font-medium text-ink-700">
            Только с онлайн-записью
          </span>
        </label>
      </div>

      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-xs font-medium text-ink-500">Цена</span>
          <span className="text-sm font-semibold text-brand-700">
            {formatPrice(p.minPrice)} – {formatPrice(p.maxPrice)}
          </span>
        </div>
        <div className="space-y-2">
          <label className="flex items-center gap-2">
            <span className="w-8 shrink-0 text-xs text-ink-400">от</span>
            <input
              type="range"
              min={0}
              max={p.priceCeiling}
              step={priceStep}
              value={p.minPrice}
              onChange={(e) => {
                const v = Math.min(Number(e.target.value), p.maxPrice);
                p.onMinPrice(v);
              }}
              className="h-2 w-full cursor-pointer appearance-none rounded-full bg-ink-100 accent-brand-600"
              aria-label="Минимальная цена"
            />
          </label>
          <label className="flex items-center gap-2">
            <span className="w-8 shrink-0 text-xs text-ink-400">до</span>
            <input
              type="range"
              min={0}
              max={p.priceCeiling}
              step={priceStep}
              value={p.maxPrice}
              onChange={(e) => {
                const v = Math.max(Number(e.target.value), p.minPrice);
                p.onMaxPrice(v);
              }}
              className="h-2 w-full cursor-pointer appearance-none rounded-full bg-ink-100 accent-brand-600"
              aria-label="Максимальная цена"
            />
          </label>
        </div>
      </div>
    </div>
  );
}

function daysSince(iso: string): number | null {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 86_400_000);
}

function freshnessLabel(days: number | null): string {
  if (days == null) return "";
  if (days <= 0) return "обновлено сегодня";
  if (days === 1) return "обновлено вчера";
  if (days < 30) return `обновлено ${days} дн. назад`;
  return `данные старше 30 дней`;
}

function OfferRow({
  offer,
  isCheapest,
  isActive,
  onSelect,
  serviceName,
  selected,
  onToggleSelect,
  selectionDisabled,
}: {
  offer: import("@/lib/types").PriceOffer;
  isCheapest: boolean;
  isActive: boolean;
  onSelect: () => void;
  serviceName: string;
  selected: boolean;
  onToggleSelect: () => void;
  selectionDisabled: boolean;
}) {
  const confidence = Math.round(offer.match_confidence * 100);
  const liRef = useRef<HTMLLIElement>(null);
  const hasGeo = offer.lat != null && offer.lng != null;
  const days = daysSince(offer.valid_from);
  const stale = days != null && days > 30;

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
      } ${stale ? "opacity-60" : ""} ${
        isActive
          ? "ring-2 ring-brand-500"
          : selected
            ? "ring-2 ring-brand-400"
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
            <label
              className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 text-xs font-medium text-ink-600"
              onClick={(e) => e.stopPropagation()}
            >
              <input
                type="checkbox"
                checked={selected}
                disabled={selectionDisabled}
                onChange={onToggleSelect}
                className="h-4 w-4 rounded border-ink-300 text-brand-600 focus:ring-brand-500 disabled:opacity-40"
              />
              Сравнить
            </label>
          </div>
          <p className="text-sm text-ink-500">
            {[offer.district, offer.address].filter(Boolean).join(" · ") ||
              "Адрес уточняйте в клинике"}
          </p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <SourceBadge source={offer.source_type} />
            {offer.rating != null && (
              <span
                className="inline-flex items-center gap-1 text-xs font-medium text-amber-600"
                title="Рейтинг клиники"
              >
                <span aria-hidden>★</span>
                {offer.rating.toFixed(1)}
              </span>
            )}
            {offer.online_booking && (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                онлайн-запись
              </span>
            )}
            <span
              className={`inline-flex items-center gap-1 text-xs ${
                stale ? "font-medium text-amber-600" : "text-ink-400"
              }`}
              title={`Актуально с ${formatDate(offer.valid_from)}`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${stale ? "bg-amber-500" : "bg-emerald-500"}`} />
              {freshnessLabel(days)}
            </span>
            <span className="text-xs text-ink-400">точность {confidence}%</span>
          </div>
          {offer.working_hours && (
            <p className="inline-flex items-center gap-1.5 text-xs text-ink-500">
              <svg viewBox="0 0 20 20" fill="none" className="h-3.5 w-3.5 text-ink-400" aria-hidden>
                <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.5" />
                <path d="M10 6v4l2.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {offer.working_hours}
            </p>
          )}
          {offer.raw_name && offer.raw_name !== offer.clinic_name && (
            <p className="text-xs text-ink-300">в прайсе: «{offer.raw_name}»</p>
          )}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
            <Link
              href={`/clinics/${offer.clinic_id}`}
              onClick={(e) => e.stopPropagation()}
              className="text-xs font-medium text-brand-700 underline-offset-2 transition hover:underline"
            >
              Все услуги клиники →
            </Link>
            {(offer.source_url || offer.website) && (
              <a
                href={(offer.source_url || offer.website) as string}
                target="_blank"
                rel="noopener noreferrer nofollow"
                onClick={(e) => e.stopPropagation()}
                className="inline-flex items-center gap-1 text-xs text-ink-400 underline-offset-2 transition hover:text-brand-700 hover:underline"
              >
                <svg viewBox="0 0 20 20" fill="none" className="h-3.5 w-3.5" aria-hidden>
                  <path d="M11 4h5v5M16 4l-7 7M9 5H5a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Источник
              </a>
            )}
            {hasGeo && (
              <a
                href={`https://yandex.ru/maps/?rtext=~${offer.lat},${offer.lng}&rtt=auto`}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="inline-flex items-center gap-1 text-xs font-medium text-brand-700 underline-offset-2 transition hover:underline"
                title="Маршрут до клиники (Яндекс.Карты)"
              >
                <svg viewBox="0 0 20 20" fill="none" className="h-3.5 w-3.5" aria-hidden>
                  <path d="M10 18s6-5.3 6-10A6 6 0 1 0 4 8c0 4.7 6 10 6 10Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                  <circle cx="10" cy="8" r="2" stroke="currentColor" strokeWidth="1.5" />
                </svg>
                Маршрут
              </a>
            )}
            <ReportPriceButton
              serviceName={serviceName}
              offer={offer}
            />
          </div>
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
          <LeadButton serviceName={serviceName} offer={offer} />
        </div>
      </div>
    </li>
  );
}
