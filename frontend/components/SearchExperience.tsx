"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { search, suggest } from "@/lib/api";
import { clearGeo, loadGeo, requestBrowserGeo, saveGeo } from "@/lib/geolocation";
import type { ServiceComparison, SortOrder } from "@/lib/types";
import ServiceCard, { nearestKm } from "./ServiceCard";
import { CardGridSkeleton } from "./Skeletons";

interface Props {
  cities: string[];
  categories: string[];
  initialResults: ServiceComparison[];
}

export default function SearchExperience({
  cities,
  categories,
  initialResults,
}: Props) {
  const [query, setQuery] = useState("");
  const [city, setCity] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState<SortOrder>("price_asc");
  // «Чекпоинт» местоположения — общий для всех страниц с поиском (localStorage).
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [geoState, setGeoState] = useState<"idle" | "loading" | "denied">("idle");

  const [results, setResults] = useState<ServiceComparison[]>(initialResults);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isPopular, setIsPopular] = useState(true);

  const abortRef = useRef<AbortController | null>(null);
  const firstRun = useRef(true);

  // Подхватываем сохранённый «чекпоинт» при загрузке (после маунта — localStorage).
  useEffect(() => {
    const g = loadGeo();
    if (g) setCoords({ lat: g.lat, lng: g.lng });
  }, []);

  const enableGeo = useCallback(async () => {
    setGeoState("loading");
    try {
      const c = await requestBrowserGeo();
      setCoords(c);
      saveGeo(c);
      setGeoState("idle");
    } catch {
      setGeoState("denied");
    }
  }, []);

  const disableGeo = useCallback(() => {
    clearGeo();
    setCoords(null);
    setGeoState("idle");
    setSort((s) => (s === "distance" ? "price_asc" : s));
  }, []);

  // Выбор сортировки «ближе» без чекпоинта — сразу просим геолокацию.
  useEffect(() => {
    if (sort === "distance" && !coords && geoState === "idle") enableGeo();
  }, [sort, coords, geoState, enableGeo]);

  const runSearch = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    const hasFilters = Boolean(query.trim() || city || category);
    setIsPopular(!hasFilters);

    try {
      const data = await search(
        {
          q: query.trim() || undefined,
          city: city || undefined,
          category: category || undefined,
          sort,
          user_lat: coords?.lat,
          user_lng: coords?.lng,
          limit: hasFilters ? 30 : 12,
        },
        controller.signal,
      );
      setResults(data);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setError("Не удалось загрузить данные. Проверьте, что сервер доступен.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [query, city, category, sort, coords]);

  // Дебаунс по всем фильтрам, кроме самой первой отрисовки (SSR данные уже есть).
  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    const t = setTimeout(runSearch, 300);
    return () => clearTimeout(t);
  }, [runSearch]);

  // Сортировка «ближе»: список услуг по расстоянию до ближайшей клиники (клиентски,
  // т.к. бэкенд сортирует офферы внутри услуги, но не список услуг).
  const shown = useMemo(() => {
    if (sort !== "distance" || !coords) return results;
    return [...results].sort((a, b) => {
      const da = nearestKm(a, coords);
      const db = nearestKm(b, coords);
      return (da ?? Infinity) - (db ?? Infinity);
    });
  }, [results, sort, coords]);

  return (
    <div className="space-y-8">
      <FilterBar
        query={query}
        onQuery={setQuery}
        city={city}
        onCity={setCity}
        category={category}
        onCategory={setCategory}
        sort={sort}
        onSort={setSort}
        cities={cities}
        categories={categories}
        hasGeo={Boolean(coords)}
        geoState={geoState}
        onEnableGeo={enableGeo}
        onDisableGeo={disableGeo}
      />

      <section className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
        <div className="mb-5 flex items-baseline justify-between gap-4">
          <h2 className="text-lg font-semibold text-ink-900">
            {isPopular ? "Популярные услуги" : "Результаты поиска"}
          </h2>
          {!loading && !error && (
            <span className="text-sm text-ink-400">
              {results.length}{" "}
              {pluralServices(results.length)}
            </span>
          )}
        </div>

        {error ? (
          <ErrorState message={error} onRetry={runSearch} />
        ) : loading ? (
          <CardGridSkeleton count={isPopular ? 12 : 6} />
        ) : results.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {shown.map((s, i) => (
              <ServiceCard
                key={s.service_id}
                service={s}
                index={i}
                city={city}
                userCoords={coords}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

interface FilterProps {
  query: string;
  onQuery: (v: string) => void;
  city: string;
  onCity: (v: string) => void;
  category: string;
  onCategory: (v: string) => void;
  sort: SortOrder;
  onSort: (v: SortOrder) => void;
  cities: string[];
  categories: string[];
  hasGeo: boolean;
  geoState: "idle" | "loading" | "denied";
  onEnableGeo: () => void;
  onDisableGeo: () => void;
}

function FilterBar(p: FilterProps) {
  return (
    <div className="mx-auto -mt-8 max-w-4xl px-4 sm:px-6">
      <div className="card relative z-10 grid grid-cols-1 gap-3 p-3 sm:grid-cols-12 sm:items-center">
        <div className="sm:col-span-12">
          <SearchAutocomplete query={p.query} onQuery={p.onQuery} />
        </div>

        <div className="sm:col-span-4">
          <select
            value={p.city}
            onChange={(e) => p.onCity(e.target.value)}
            className="field appearance-none bg-[length:1.25rem] bg-[right_0.75rem_center] bg-no-repeat pr-10"
            style={{ backgroundImage: chevron }}
            aria-label="Город"
          >
            <option value="">Все города</option>
            {p.cities.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        <div className="sm:col-span-4">
          <select
            value={p.category}
            onChange={(e) => p.onCategory(e.target.value)}
            className="field appearance-none bg-[length:1.25rem] bg-[right_0.75rem_center] bg-no-repeat pr-10"
            style={{ backgroundImage: chevron }}
            aria-label="Категория"
          >
            <option value="">Все категории</option>
            {p.categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        <div className="sm:col-span-4">
          <SortToggle sort={p.sort} onSort={p.onSort} />
        </div>

        <div className="sm:col-span-12">
          <GeoControl
            hasGeo={p.hasGeo}
            geoState={p.geoState}
            onEnable={p.onEnableGeo}
            onDisable={p.onDisableGeo}
          />
        </div>
      </div>
    </div>
  );
}

function GeoControl({
  hasGeo,
  geoState,
  onEnable,
  onDisable,
}: {
  hasGeo: boolean;
  geoState: "idle" | "loading" | "denied";
  onEnable: () => void;
  onDisable: () => void;
}) {
  const pin = (
    <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4" aria-hidden>
      <path d="M10 18s6-5.3 6-10A6 6 0 0 0 4 8c0 4.7 6 10 6 10Z" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="10" cy="8" r="2" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
  if (hasGeo) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <span className="inline-flex items-center gap-1.5 rounded-lg bg-brand-50 px-3 py-2 font-medium text-brand-700 ring-1 ring-inset ring-brand-100">
          {pin} Местоположение учтено — показываем расстояние
        </span>
        <button
          type="button"
          onClick={onDisable}
          className="text-ink-400 underline-offset-2 hover:text-ink-700 hover:underline"
        >
          сбросить
        </button>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 text-sm">
      <button
        type="button"
        onClick={onEnable}
        disabled={geoState === "loading"}
        className="inline-flex items-center gap-1.5 rounded-lg border border-ink-200 px-3 py-2 font-medium text-ink-700 transition hover:border-brand-300 hover:text-brand-700 disabled:opacity-60"
      >
        {pin}
        {geoState === "loading" ? "Определяем…" : "Рядом со мной — учесть расстояние"}
      </button>
      {geoState === "denied" && (
        <span className="text-xs text-ink-400">
          Доступ к геолокации отклонён — разрешите его в браузере.
        </span>
      )}
    </div>
  );
}

function SearchAutocomplete({
  query,
  onQuery,
}: {
  query: string;
  onQuery: (v: string) => void;
}) {
  const [items, setItems] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  // Когда значение поставлено выбором из списка — не дёргаем подсказки заново.
  const skipNext = useRef(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (skipNext.current) {
      skipNext.current = false;
      return;
    }
    const q = query.trim();
    if (q.length < 2) {
      setItems([]);
      setOpen(false);
      return;
    }
    const t = setTimeout(async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const data = await suggest(q, 10, controller.signal);
        setItems(data);
        setOpen(data.length > 0);
        setActive(-1);
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setItems([]);
        setOpen(false);
      }
    }, 200);
    return () => clearTimeout(t);
  }, [query]);

  // Закрытие по клику вне.
  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const pick = (value: string) => {
    skipNext.current = true;
    onQuery(value);
    setOpen(false);
    setItems([]);
    setActive(-1);
  };

  return (
    <div ref={boxRef} className="relative">
      <svg
        viewBox="0 0 20 20"
        fill="none"
        className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-400"
        aria-hidden
      >
        <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="1.75" />
        <path d="m14 14 3 3" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
      </svg>
      <input
        type="text"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        onFocus={() => {
          if (items.length > 0) setOpen(true);
        }}
        onKeyDown={(e) => {
          if (!open || items.length === 0) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((i) => (i + 1) % items.length);
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((i) => (i - 1 + items.length) % items.length);
          } else if (e.key === "Enter" && active >= 0) {
            e.preventDefault();
            pick(items[active]);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
        placeholder="Например: МРТ головного мозга, УЗИ, приём кардиолога…"
        className="field pl-12 text-base"
        aria-label="Поиск медицинской услуги"
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        autoComplete="off"
      />
      {open && items.length > 0 && (
        <ul
          className="absolute left-0 right-0 top-full z-20 mt-2 max-h-72 overflow-auto rounded-xl border border-ink-200 bg-white py-1.5 shadow-lg"
          role="listbox"
        >
          {items.map((item, i) => (
            <li key={item} role="option" aria-selected={i === active}>
              <button
                type="button"
                onMouseEnter={() => setActive(i)}
                onClick={() => pick(item)}
                className={`flex w-full items-center gap-2.5 px-4 py-2 text-left text-sm transition ${
                  i === active ? "bg-brand-50 text-brand-800" : "text-ink-700 hover:bg-ink-50"
                }`}
              >
                <svg
                  viewBox="0 0 20 20"
                  fill="none"
                  className="h-4 w-4 shrink-0 text-ink-300"
                  aria-hidden
                >
                  <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="1.6" />
                  <path d="m14 14 3 3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
                <span className="truncate">{item}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SortToggle({
  sort,
  onSort,
}: {
  sort: SortOrder;
  onSort: (v: SortOrder) => void;
}) {
  const btn = (value: SortOrder, label: string) => (
    <button
      type="button"
      onClick={() => onSort(value)}
      className={`flex-1 whitespace-nowrap rounded-lg px-3 py-2 transition ${
        sort === value
          ? "bg-brand-600 text-white shadow-sm"
          : "text-ink-500 hover:text-ink-800"
      }`}
      aria-pressed={sort === value}
    >
      {label}
    </button>
  );
  return (
    <div className="flex rounded-xl border border-ink-200 bg-white p-1 text-sm font-medium">
      {btn("price_asc", "Дешевле")}
      {btn("price_desc", "Дороже")}
      {/* «Ближе» — учитывает расстояние; при выборе без чекпоинта спросит геолокацию */}
      {btn("distance", "Ближе")}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-16 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-500">
        <svg viewBox="0 0 24 24" fill="none" className="h-7 w-7" aria-hidden>
          <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8" />
          <path
            d="m16.5 16.5 4 4"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      </div>
      <h3 className="text-base font-semibold text-ink-900">Ничего не нашлось</h3>
      <p className="max-w-sm text-sm text-ink-500">
        Попробуйте изменить запрос, выбрать другой город или сбросить фильтр
        категории.
      </p>
    </div>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-16 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-red-50 text-red-500">
        <svg viewBox="0 0 24 24" fill="none" className="h-7 w-7" aria-hidden>
          <path
            d="M12 8v5m0 3h.01M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.7 3.86a2 2 0 0 0-3.42 0Z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
      <h3 className="text-base font-semibold text-ink-900">Что-то пошло не так</h3>
      <p className="max-w-sm text-sm text-ink-500">{message}</p>
      <button type="button" onClick={onRetry} className="btn-primary mt-2">
        Повторить
      </button>
    </div>
  );
}

const chevron =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='none'%3E%3Cpath d='M6 8l4 4 4-4' stroke='%2364748b' stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")";

function pluralServices(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "услуга";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return "услуги";
  return "услуг";
}
