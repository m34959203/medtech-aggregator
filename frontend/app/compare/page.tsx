"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  compareClinics,
  getCities,
  getClinics,
  getServices,
} from "@/lib/api";
import { formatPrice } from "@/lib/format";
import type {
  ClinicComparison,
  ClinicOut,
  CompareCell,
  CompareColumn,
  CompareRecommendation,
} from "@/lib/types";

type ServiceLite = { id: string; canonical_name: string; category: string };

const MIN_SERVICES = 2;
const MAX_SERVICES = 8;
const MAX_CLINICS = 4;

export default function ComparePage() {
  // --- Справочники ---
  const [catalog, setCatalog] = useState<ServiceLite[]>([]);
  const [cities, setCities] = useState<string[]>([]);
  const [clinics, setClinics] = useState<ClinicOut[]>([]);

  // --- Выбор пользователя ---
  const [serviceIds, setServiceIds] = useState<string[]>([]);
  const [city, setCity] = useState("");
  const [clinicIds, setClinicIds] = useState<string[]>([]);
  const [requireAll, setRequireAll] = useState(false);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [geoState, setGeoState] = useState<"idle" | "loading" | "error">("idle");

  // --- Результат ---
  const [result, setResult] = useState<ClinicComparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getServices().then(setCatalog).catch(() => {});
    getCities().then(setCities).catch(() => {});
    getClinics().then(setClinics).catch(() => {});
  }, []);

  // Имя услуги по id (для чипов выбранных услуг).
  const nameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const s of catalog) m.set(s.id, s.canonical_name);
    return m;
  }, [catalog]);

  // Клиники, доступные к выбору (по городу, исключая уже выбранные).
  const clinicOptions = useMemo(() => {
    return clinics.filter(
      (c) => (!city || c.city === city) && !clinicIds.includes(c.id),
    );
  }, [clinics, city, clinicIds]);

  const clinicById = useMemo(() => {
    const m = new Map<string, ClinicOut>();
    for (const c of clinics) m.set(c.id, c);
    return m;
  }, [clinics]);

  // Если сменили город — сбрасываем выбранные клиники из других городов.
  useEffect(() => {
    if (!city) return;
    setClinicIds((ids) =>
      ids.filter((id) => clinicById.get(id)?.city === city),
    );
  }, [city, clinicById]);

  function addService(id: string) {
    setServiceIds((s) =>
      s.includes(id) || s.length >= MAX_SERVICES ? s : [...s, id],
    );
  }
  function removeService(id: string) {
    setServiceIds((s) => s.filter((x) => x !== id));
  }
  function addClinic(id: string) {
    setClinicIds((s) =>
      s.includes(id) || s.length >= MAX_CLINICS ? s : [...s, id],
    );
  }
  function removeClinic(id: string) {
    setClinicIds((s) => s.filter((x) => x !== id));
  }

  function requestGeo() {
    if (coords) {
      setCoords(null);
      setGeoState("idle");
      return;
    }
    if (!("geolocation" in navigator)) {
      setGeoState("error");
      return;
    }
    setGeoState("loading");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setGeoState("idle");
      },
      () => setGeoState("error"),
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 600000 },
    );
  }

  async function run() {
    if (serviceIds.length < MIN_SERVICES) {
      setError(`Выберите минимум ${MIN_SERVICES} услуги для сравнения.`);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await compareClinics({
        service_ids: serviceIds,
        clinic_ids: clinicIds.length ? clinicIds : null,
        city: city || null,
        user_lat: coords?.lat ?? null,
        user_lng: coords?.lng ?? null,
        require_all: requireAll,
      });
      setResult(data);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Не удалось построить сравнение.",
      );
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  const canRun = serviceIds.length >= MIN_SERVICES && !loading;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <header className="mb-8 max-w-2xl">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-200">
          Услуги × клиники → одна таблица
        </span>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-ink-900">
          Сравнение клиник
        </h1>
        <p className="mt-3 text-ink-600">
          Выберите несколько услуг и клиники — система соберёт цены в одну
          таблицу, отметит лучшую цену по каждой услуге и подскажет выгодный
          вариант. Оставьте список клиник пустым — подберём четыре лучших
          автоматически.
        </p>
      </header>

      {/* --- Зона выбора --- */}
      <div className="card mb-8 space-y-5 p-5 sm:p-6">
        <ServicePicker
          catalog={catalog}
          selected={serviceIds}
          nameById={nameById}
          onAdd={addService}
          onRemove={removeService}
        />

        <div className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-ink-700">Город</label>
            <select
              value={city}
              onChange={(e) => setCity(e.target.value)}
              className="field py-2.5 text-sm"
            >
              <option value="">Все города</option>
              {cities.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>

          <ClinicPicker
            options={clinicOptions}
            selected={clinicIds}
            clinicById={clinicById}
            onAdd={addClinic}
            onRemove={removeClinic}
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={requestGeo}
            className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium ring-1 ring-inset transition ${
              coords
                ? "bg-brand-50 text-brand-700 ring-brand-300"
                : "bg-white text-ink-600 ring-ink-200 hover:border-brand-300 hover:text-brand-700"
            }`}
          >
            <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" aria-hidden>
              <path
                d="M10 18s6-5.2 6-9.5A6 6 0 0 0 4 8.5C4 12.8 10 18 10 18Z"
                stroke="currentColor"
                strokeWidth="1.6"
              />
              <circle cx="10" cy="8.5" r="2" stroke="currentColor" strokeWidth="1.6" />
            </svg>
            {coords
              ? "Расстояние учитывается"
              : geoState === "loading"
                ? "Определяю…"
                : "Учитывать расстояние"}
          </button>

          <label className="inline-flex cursor-pointer select-none items-center gap-2 text-sm text-ink-700">
            <input
              type="checkbox"
              checked={requireAll}
              onChange={(e) => setRequireAll(e.target.checked)}
              className="h-4 w-4 rounded border-ink-300 text-brand-600 focus:ring-brand-200"
            />
            Только клиники со всеми услугами
          </label>

          {geoState === "error" && (
            <span className="text-xs text-amber-600">
              Геолокация недоступна — расстояние не будет учтено.
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-ink-100 pt-4">
          <button
            type="button"
            onClick={run}
            disabled={!canRun}
            className="inline-flex items-center gap-2 rounded-full bg-brand-600 px-6 py-2.5 text-sm font-semibold text-white shadow-glow transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Сравниваю…" : "Сравнить клиники"}
          </button>
          <span className="text-xs text-ink-400">
            Услуг выбрано: {serviceIds.length} / {MAX_SERVICES}
            {clinicIds.length === 0
              ? " · клиники подберём автоматически"
              : ` · клиник: ${clinicIds.length} / ${MAX_CLINICS}`}
          </span>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>

      {/* --- Результат --- */}
      {loading && <TableSkeleton />}

      {!loading && !result && (
        <div className="flex min-h-[240px] items-center justify-center rounded-2xl border border-dashed border-ink-200 bg-ink-50 px-6 text-center text-sm text-ink-400">
          Выберите услуги и клиники для сравнения
        </div>
      )}

      {!loading && result && result.clinics.length === 0 && (
        <div className="flex min-h-[200px] items-center justify-center rounded-2xl border border-dashed border-ink-200 bg-ink-50 px-6 text-center text-sm text-ink-500">
          Не нашлось клиник под заданные условия. Снимите фильтр «только со всеми
          услугами» или расширьте город.
        </div>
      )}

      {!loading && result && result.clinics.length > 0 && (
        <ResultView result={result} coords={coords} />
      )}
    </div>
  );
}

/* ============================ Выбор услуг ============================ */

function ServicePicker({
  catalog,
  selected,
  nameById,
  onAdd,
  onRemove,
}: {
  catalog: ServiceLite[];
  selected: string[];
  nameById: Map<string, string>;
  onAdd: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 1) return [];
    return catalog
      .filter(
        (s) =>
          !selected.includes(s.id) &&
          s.canonical_name.toLowerCase().includes(q),
      )
      .slice(0, 8);
  }, [query, catalog, selected]);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node))
        setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const full = selected.length >= MAX_SERVICES;

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-ink-700">
        Услуги для сравнения{" "}
        <span className="font-normal text-ink-400">
          (от {MIN_SERVICES} до {MAX_SERVICES})
        </span>
      </label>

      {selected.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selected.map((id) => (
            <span
              key={id}
              className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 py-1 pl-3 pr-1.5 text-sm text-brand-800 ring-1 ring-inset ring-brand-200"
            >
              {nameById.get(id) ?? "услуга"}
              <button
                type="button"
                onClick={() => onRemove(id)}
                aria-label="Убрать услугу"
                className="grid h-5 w-5 place-items-center rounded-full text-brand-500 transition hover:bg-brand-100 hover:text-brand-800"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <div ref={boxRef} className="relative">
        <input
          type="text"
          value={query}
          disabled={full}
          placeholder={
            full
              ? "Достигнут максимум услуг"
              : "Начните вводить название анализа или услуги…"
          }
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocusCapture={() => setOpen(true)}
          className="field py-2.5 text-sm disabled:cursor-not-allowed disabled:bg-ink-50"
        />
        {open && matches.length > 0 && (
          <ul className="absolute z-20 mt-1.5 max-h-72 w-full overflow-auto rounded-xl border border-ink-100 bg-white p-1 shadow-card-hover">
            {matches.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => {
                    onAdd(s.id);
                    setQuery("");
                    setOpen(false);
                  }}
                  className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm text-ink-800 transition hover:bg-brand-50"
                >
                  <span>{s.canonical_name}</span>
                  <span className="shrink-0 text-xs text-ink-400">
                    {s.category}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/* ============================ Выбор клиник ============================ */

function ClinicPicker({
  options,
  selected,
  clinicById,
  onAdd,
  onRemove,
}: {
  options: ClinicOut[];
  selected: string[];
  clinicById: Map<string, ClinicOut>;
  onAdd: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    const base = q
      ? options.filter((c) => c.name.toLowerCase().includes(q))
      : options;
    return base.slice(0, 8);
  }, [query, options]);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node))
        setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const full = selected.length >= MAX_CLINICS;

  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium text-ink-700">
        Клиники{" "}
        <span className="font-normal text-ink-400">
          (до {MAX_CLINICS}; пусто = авто)
        </span>
      </label>

      {selected.length > 0 && (
        <div className="mb-1 flex flex-wrap gap-2">
          {selected.map((id) => (
            <span
              key={id}
              className="inline-flex items-center gap-1.5 rounded-full bg-ink-100 py-1 pl-3 pr-1.5 text-sm text-ink-700 ring-1 ring-inset ring-ink-200"
            >
              {clinicById.get(id)?.name ?? "клиника"}
              <button
                type="button"
                onClick={() => onRemove(id)}
                aria-label="Убрать клинику"
                className="grid h-5 w-5 place-items-center rounded-full text-ink-400 transition hover:bg-ink-200 hover:text-ink-700"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <div ref={boxRef} className="relative">
        <input
          type="text"
          value={query}
          disabled={full}
          placeholder={full ? "Максимум клиник выбран" : "+ Добавить клинику"}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocusCapture={() => setOpen(true)}
          className="field py-2.5 text-sm disabled:cursor-not-allowed disabled:bg-ink-50"
        />
        {open && !full && matches.length > 0 && (
          <ul className="absolute z-20 mt-1.5 max-h-72 w-full overflow-auto rounded-xl border border-ink-100 bg-white p-1 shadow-card-hover">
            {matches.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => {
                    onAdd(c.id);
                    setQuery("");
                    setOpen(false);
                  }}
                  className="flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm text-ink-800 transition hover:bg-brand-50"
                >
                  <span className="truncate">{c.name}</span>
                  <span className="shrink-0 text-xs text-ink-400">{c.city}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/* ============================ Результат ============================ */

function ResultView({
  result,
  coords,
}: {
  result: ClinicComparison;
  coords: { lat: number; lng: number } | null;
}) {
  const { clinics, services } = result;
  // Минимальный итог — для отметки 🏆 в строке «Итого».
  const minTotal = Math.min(...clinics.map((c) => c.total));

  return (
    <div className="space-y-6">
      <Recommendations recs={result.recommendations} />

      {/* Десктоп / планшет — широкая таблица */}
      <div className="hidden sm:block">
        <div className="card overflow-hidden p-0">
          <div className="max-h-[72vh] overflow-auto">
            <table className="w-full border-separate border-spacing-0 text-sm">
              <thead>
                <tr>
                  <th className="sticky left-0 top-0 z-30 min-w-[180px] border-b border-ink-100 bg-ink-50 px-4 py-3 text-left font-semibold text-ink-500">
                    Параметр
                  </th>
                  {clinics.map((c) => (
                    <th
                      key={c.clinic_id}
                      className="sticky top-0 z-20 min-w-[200px] border-b border-l border-ink-100 bg-white px-4 py-3 text-left align-top"
                    >
                      <div className="font-bold text-ink-900">{c.clinic_name}</div>
                      <div className="mt-0.5 text-xs font-normal text-ink-400">
                        {[c.city, c.address].filter(Boolean).join(" · ")}
                      </div>
                      {c.covers_all && (
                        <span className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-medium text-brand-700 ring-1 ring-inset ring-brand-200">
                          все услуги
                        </span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {/* Строки услуг */}
                {services.map((svc, rowIdx) => (
                  <tr key={svc.service_id} className="group">
                    <ThRow>{svc.canonical_name}</ThRow>
                    {clinics.map((c) => (
                      <td
                        key={c.clinic_id}
                        className="border-b border-l border-ink-100 px-4 py-3 group-hover:bg-ink-50/60"
                      >
                        <PriceCell cell={c.cells[rowIdx]} />
                      </td>
                    ))}
                  </tr>
                ))}

                {/* Итого */}
                <SummaryRow label={`Итого за ${services.length} ${pluralServices(services.length)}`} accent>
                  {clinics.map((c) => (
                    <SummaryCell key={c.clinic_id} accent>
                      <span className="text-base font-bold text-ink-900">
                        {formatPrice(c.total)}
                      </span>
                      {c.total === minTotal && <Trophy />}
                    </SummaryCell>
                  ))}
                </SummaryRow>

                {/* Экономия */}
                <SummaryRow label="Экономия от самого дорогого">
                  {clinics.map((c) => (
                    <SummaryCell key={c.clinic_id}>
                      {c.savings_vs_max > 0 ? (
                        <span className="font-semibold text-brand-700">
                          −{formatPrice(c.savings_vs_max)}
                        </span>
                      ) : (
                        <Dash />
                      )}
                    </SummaryCell>
                  ))}
                </SummaryRow>

                {/* Расстояние */}
                <SummaryRow label="Расстояние">
                  {clinics.map((c) => (
                    <SummaryCell key={c.clinic_id}>
                      {c.distance_km != null ? (
                        <span className="text-ink-700">
                          {c.distance_km.toFixed(1)} км
                        </span>
                      ) : (
                        <Dash />
                      )}
                    </SummaryCell>
                  ))}
                </SummaryRow>

                {/* Рейтинг */}
                <SummaryRow label="Рейтинг">
                  {clinics.map((c) => (
                    <SummaryCell key={c.clinic_id}>
                      {c.rating != null ? (
                        <span className="text-ink-700">{c.rating} ★</span>
                      ) : (
                        <Dash />
                      )}
                    </SummaryCell>
                  ))}
                </SummaryRow>

                {/* Онлайн-запись */}
                <SummaryRow label="Онлайн-запись">
                  {clinics.map((c) => (
                    <SummaryCell key={c.clinic_id}>
                      {c.online_booking ? (
                        <span className="font-medium text-brand-700">Есть</span>
                      ) : (
                        <span className="text-ink-400">Нет</span>
                      )}
                    </SummaryCell>
                  ))}
                </SummaryRow>

                {/* Режим работы */}
                <SummaryRow label="Режим работы">
                  {clinics.map((c) => (
                    <SummaryCell key={c.clinic_id}>
                      {c.working_hours ? (
                        <span className="text-ink-700">{c.working_hours}</span>
                      ) : (
                        <Dash />
                      )}
                    </SummaryCell>
                  ))}
                </SummaryRow>

                {/* Обновление цены */}
                <SummaryRow label="Обновление цены">
                  {clinics.map((c) => (
                    <SummaryCell key={c.clinic_id}>
                      <span className="text-ink-600">{freshnessLabel(c.cells)}</span>
                    </SummaryCell>
                  ))}
                </SummaryRow>

                {/* Источник */}
                <SummaryRow label="Источник">
                  {clinics.map((c) => (
                    <SummaryCell key={c.clinic_id}>
                      <span className="text-ink-600">{sourceLabel(c.cells)}</span>
                    </SummaryCell>
                  ))}
                </SummaryRow>

                {/* Действия */}
                <SummaryRow label="Действия">
                  {clinics.map((c) => (
                    <SummaryCell key={c.clinic_id}>
                      <ClinicActions col={c} coords={coords} />
                    </SummaryCell>
                  ))}
                </SummaryRow>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Мобильные — карточки клиник */}
      <div className="space-y-4 sm:hidden">
        {clinics.map((c) => (
          <ClinicCard
            key={c.clinic_id}
            col={c}
            services={services}
            isCheapest={c.total === minTotal}
            coords={coords}
          />
        ))}
      </div>
    </div>
  );
}

function Recommendations({
  recs,
}: {
  recs: ClinicComparison["recommendations"];
}) {
  const items: { rec: CompareRecommendation; tone: string; icon: string }[] = [];
  if (recs.cheapest)
    items.push({ rec: recs.cheapest, tone: "brand", icon: "💰" });
  if (recs.nearest) items.push({ rec: recs.nearest, tone: "sky", icon: "📍" });
  if (recs.best_balance)
    items.push({ rec: recs.best_balance, tone: "amber", icon: "⚖️" });
  if (items.length === 0) return null;

  const tones: Record<string, string> = {
    brand: "bg-brand-50 ring-brand-200",
    sky: "bg-sky-50 ring-sky-200",
    amber: "bg-amber-50 ring-amber-200",
  };

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {items.map(({ rec, tone, icon }) => (
        <div
          key={rec.label}
          className={`rounded-2xl p-4 ring-1 ring-inset ${tones[tone]}`}
        >
          <p className="flex items-center gap-1.5 text-xs font-medium text-ink-500">
            <span aria-hidden>{icon}</span>
            {rec.label}
          </p>
          <p className="mt-1 text-base font-bold text-ink-900">
            {rec.clinic_name}
          </p>
        </div>
      ))}
    </div>
  );
}

/* ----- Ячейки и строки таблицы ----- */

function ThRow({ children }: { children: React.ReactNode }) {
  return (
    <th className="sticky left-0 z-10 min-w-[180px] border-b border-ink-100 bg-white px-4 py-3 text-left font-medium text-ink-600 group-hover:bg-ink-50">
      {children}
    </th>
  );
}

function SummaryRow({
  label,
  children,
  accent,
}: {
  label: string;
  children: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <tr className="group">
      <th
        className={`sticky left-0 z-10 border-b border-ink-100 px-4 py-3 text-left font-semibold ${
          accent ? "bg-brand-50/60 text-ink-800" : "bg-ink-50 text-ink-600"
        }`}
      >
        {label}
      </th>
      {children}
    </tr>
  );
}

function SummaryCell({
  children,
  accent,
}: {
  children: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <td
      className={`border-b border-l border-ink-100 px-4 py-3 ${
        accent ? "bg-brand-50/40" : ""
      }`}
    >
      <span className="inline-flex items-center gap-1.5">{children}</span>
    </td>
  );
}

function PriceCell({ cell }: { cell: CompareCell | undefined }) {
  if (!cell || !cell.found || cell.price == null) {
    return <span className="text-ink-300">Не найдено</span>;
  }
  if (cell.is_best) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-lg bg-brand-50 px-2 py-1 font-bold text-brand-700 ring-1 ring-inset ring-brand-200">
        <span aria-hidden>🏆</span>
        {formatPrice(cell.price)}
      </span>
    );
  }
  return <span className="font-medium text-ink-800">{formatPrice(cell.price)}</span>;
}

function ClinicActions({
  col,
  coords,
}: {
  col: CompareColumn;
  coords: { lat: number; lng: number } | null;
}) {
  const tel = col.phone ? col.phone.replace(/[^\d+]/g, "") : "";
  return (
    <span className="flex flex-col items-start gap-1.5">
      {col.online_booking && col.website ? (
        <a
          href={col.website}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-full bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-brand-700"
        >
          Записаться
        </a>
      ) : tel ? (
        <a
          href={`tel:${tel}`}
          className="inline-flex items-center gap-1 rounded-full border border-ink-200 px-3 py-1.5 text-xs font-medium text-ink-700 transition hover:border-brand-300 hover:text-brand-700"
        >
          Позвонить
        </a>
      ) : null}
      <a
        href={mapsHref(col, coords)}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs font-medium text-brand-700 hover:underline"
      >
        Маршрут →
      </a>
    </span>
  );
}

/* ----- Мобильная карточка клиники ----- */

function ClinicCard({
  col,
  services,
  isCheapest,
  coords,
}: {
  col: CompareColumn;
  services: ClinicComparison["services"];
  isCheapest: boolean;
  coords: { lat: number; lng: number } | null;
}) {
  return (
    <div
      className={`card p-4 ${isCheapest ? "ring-2 ring-brand-300" : ""}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-bold text-ink-900">{col.clinic_name}</h3>
          <p className="mt-0.5 truncate text-xs text-ink-400">
            {[col.city, col.address].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <div className="flex items-center gap-1 text-lg font-bold text-brand-700">
            {isCheapest && <span aria-hidden>🏆</span>}
            {formatPrice(col.total)}
          </div>
          {col.savings_vs_max > 0 && (
            <p className="text-xs text-brand-600">
              экономия {formatPrice(col.savings_vs_max)}
            </p>
          )}
        </div>
      </div>

      <ul className="mt-3 divide-y divide-ink-100 border-y border-ink-100">
        {services.map((svc, i) => {
          const cell = col.cells[i];
          return (
            <li
              key={svc.service_id}
              className="flex items-center justify-between gap-3 py-2 text-sm"
            >
              <span className="min-w-0 truncate text-ink-600">
                {svc.canonical_name}
              </span>
              <span className="shrink-0">
                {!cell || !cell.found || cell.price == null ? (
                  <span className="text-ink-300">Не найдено</span>
                ) : cell.is_best ? (
                  <span className="inline-flex items-center gap-1 font-bold text-brand-700">
                    <span aria-hidden>🏆</span>
                    {formatPrice(cell.price)}
                  </span>
                ) : (
                  <span className="font-medium text-ink-800">
                    {formatPrice(cell.price)}
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ul>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
        <Meta term="Расстояние">
          {col.distance_km != null ? `${col.distance_km.toFixed(1)} км` : "—"}
        </Meta>
        <Meta term="Рейтинг">{col.rating != null ? `${col.rating} ★` : "—"}</Meta>
        <Meta term="Онлайн-запись">{col.online_booking ? "Есть" : "Нет"}</Meta>
        <Meta term="Обновлено">{freshnessLabel(col.cells)}</Meta>
        <Meta term="Режим">{col.working_hours || "—"}</Meta>
        <Meta term="Источник">{sourceLabel(col.cells)}</Meta>
      </dl>

      <div className="mt-3 flex items-center gap-2">
        <ClinicActions col={col} coords={coords} />
      </div>
    </div>
  );
}

function Meta({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-ink-400">{term}</dt>
      <dd className="text-right font-medium text-ink-700">{children}</dd>
    </div>
  );
}

/* ----- Мелочи ----- */

function Trophy() {
  return (
    <span aria-label="лучшая цена" className="text-base">
      🏆
    </span>
  );
}

function Dash() {
  return <span className="text-ink-300">—</span>;
}

function TableSkeleton() {
  return (
    <div className="card space-y-3 p-6">
      <div className="skeleton h-10 w-full rounded-lg" />
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="skeleton h-8 w-full rounded-lg" />
      ))}
    </div>
  );
}

/* ----- Хелперы форматирования ----- */

function pluralServices(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "услугу";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return "услуги";
  return "услуг";
}

// Берём «представительную» ячейку (первую найденную) для метаданных строки.
function firstFound(cells: CompareCell[]): CompareCell | undefined {
  return cells.find((c) => c.found) ?? cells[0];
}

function freshnessLabel(cells: CompareCell[]): string {
  const cell = firstFound(cells);
  const days = cell?.freshness_days;
  if (days == null) return "—";
  if (days <= 0) return "Сегодня";
  return `${days} ${pluralDays(days)} назад`;
}

function pluralDays(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "день";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return "дня";
  return "дней";
}

function sourceLabel(cells: CompareCell[]): string {
  const src = firstFound(cells)?.source_type;
  switch (src) {
    case "api":
      return "103.kz";
    case "web_scrape":
      return "Сайт клиники";
    case "upload":
      return "Загрузка";
    default:
      return "—";
  }
}

function mapsHref(
  col: CompareColumn,
  coords: { lat: number; lng: number } | null,
): string {
  const from = coords ? `${coords.lat},${coords.lng}~` : "";
  const to =
    col.lat != null && col.lng != null
      ? `${col.lat},${col.lng}`
      : encodeURIComponent([col.city, col.address].filter(Boolean).join(", "));
  return `https://yandex.ru/maps/?rtext=${from}${to}&rtt=auto`;
}
