"use client";

import { useEffect, useMemo, useState } from "react";
import type { PriceOffer } from "@/lib/types";
import { formatPrice, formatDate } from "@/lib/format";
import { haversineKm, formatDistance } from "@/lib/distance";

interface ServiceComparePanelProps {
  offers: PriceOffer[]; // все текущие офферы (для поиска выбранных по clinic_id)
  selectedIds: string[]; // выбранные clinic_id (0..4)
  coords: { lat: number; lng: number } | null; // геопозиция пользователя
  serviceName: string;
  onRemove: (clinicId: string) => void; // убрать клинику из выбора
  onClear: () => void; // очистить выбор
  onRequestGeo?: () => void; // запросить геолокацию (если coords == null)
}

const MIN_SELECT = 2;
const MAX_SELECT = 4;

/** Кол-во дней с даты обновления цены до сегодня. */
function daysSince(iso: string): number | null {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const ms = Date.now() - d.getTime();
  return Math.max(0, Math.floor(ms / 86_400_000));
}

function freshnessLabel(days: number | null): string {
  if (days === null) return "—";
  if (days === 0) return "сегодня";
  return `${days} дн назад`;
}

/** Сравнивает значения метрики и возвращает множество индексов-лидеров. */
function leaders(
  values: (number | null)[],
  mode: "min" | "max",
): Set<number> {
  const present = values
    .map((v, i) => ({ v, i }))
    .filter((x): x is { v: number; i: number } => x.v !== null);
  if (present.length < 2) return new Set(); // нечего сравнивать
  const best =
    mode === "min"
      ? Math.min(...present.map((x) => x.v))
      : Math.max(...present.map((x) => x.v));
  return new Set(present.filter((x) => x.v === best).map((x) => x.i));
}

export default function ServiceComparePanel({
  offers,
  selectedIds,
  coords,
  serviceName,
  onRemove,
  onClear,
  onRequestGeo,
}: ServiceComparePanelProps) {
  const [open, setOpen] = useState(false);

  // Выбранные офферы в порядке selectedIds (первый оффер по clinic_id).
  const selected = useMemo(
    () =>
      selectedIds
        .map((id) => offers.find((o) => o.clinic_id === id))
        .filter((o): o is PriceOffer => Boolean(o)),
    [offers, selectedIds],
  );

  const count = selected.length;
  const canCompare = count >= MIN_SELECT && count <= MAX_SELECT;

  // Esc закрывает модалку.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Блокируем фоновый скролл при открытой модалке.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // Если выбор опустел при открытой модалке — закрываем.
  useEffect(() => {
    if (count === 0 && open) setOpen(false);
  }, [count, open]);

  if (selectedIds.length === 0) return null;

  // --- Предрасчёт метрик и лидеров для модалки ---
  const prices = selected.map((o) => o.price);
  const ratings = selected.map((o) => (o.rating != null ? o.rating : null));
  const distances = selected.map((o) =>
    coords && o.lat != null && o.lng != null
      ? haversineKm(coords.lat, coords.lng, o.lat, o.lng)
      : null,
  );
  const ages = selected.map((o) => daysSince(o.valid_from));

  const priceLeaders = leaders(prices, "min");
  const ratingLeaders = leaders(ratings, "max");
  const distanceLeaders = leaders(distances, "min");
  const freshLeaders = leaders(ages, "min");

  const cellBase = "px-4 py-3 align-top text-sm border-t border-ink-100";
  const winCell = "bg-brand-50";

  return (
    <>
      {/* ── Закреплённая панель снизу ── */}
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex justify-center px-3 pb-3 sm:pb-5">
        <div className="card pointer-events-auto w-full max-w-3xl !rounded-2xl px-3 py-3 shadow-lg sm:px-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-ink-900">
                  Сравнение: {count}
                </span>
                <button
                  type="button"
                  onClick={onClear}
                  className="text-xs font-medium text-ink-500 underline-offset-2 hover:text-ink-700 hover:underline"
                >
                  Очистить
                </button>
              </div>

              {/* Чипы выбранных клиник */}
              <div className="mt-2 flex flex-wrap gap-1.5">
                {selected.map((o) => (
                  <span
                    key={o.clinic_id}
                    className="badge inline-flex items-center gap-1 bg-ink-50 text-ink-700 ring-1 ring-inset ring-ink-200"
                  >
                    <span className="max-w-[10rem] truncate">
                      {o.clinic_name}
                    </span>
                    <button
                      type="button"
                      aria-label={`Убрать ${o.clinic_name} из сравнения`}
                      onClick={() => onRemove(o.clinic_id)}
                      className="-mr-0.5 flex h-4 w-4 items-center justify-center rounded-full text-ink-400 hover:bg-ink-200 hover:text-ink-700"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>

            <div className="flex shrink-0 flex-col items-stretch gap-1 sm:items-end">
              <button
                type="button"
                disabled={!canCompare}
                onClick={() => setOpen(true)}
                aria-label={`Сравнить ${count} клиник`}
                className="rounded-xl bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 focus:outline-none focus:ring-2 focus:ring-brand-300 disabled:cursor-not-allowed disabled:bg-ink-200 disabled:text-ink-400 disabled:shadow-none"
              >
                Сравнить ({count})
              </button>
              {count < MIN_SELECT && (
                <span className="text-xs text-ink-400">
                  Выберите ещё минимум одну клинику
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Модалка сравнения ── */}
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-ink-900/50 p-0 backdrop-blur-sm sm:items-center sm:p-4"
          onClick={() => setOpen(false)}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label={`Сравнение клиник: ${serviceName}`}
            onClick={(e) => e.stopPropagation()}
            className="card flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden !rounded-t-2xl !rounded-b-none p-0 sm:!rounded-2xl"
          >
            {/* Шапка */}
            <div className="flex items-start justify-between gap-4 border-b border-ink-100 px-5 py-4">
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-wide text-ink-400">
                  Сравнение услуги
                </p>
                <h2 className="truncate text-base font-semibold text-ink-900">
                  {serviceName}
                </h2>
              </div>
              <button
                type="button"
                aria-label="Закрыть сравнение"
                onClick={() => setOpen(false)}
                className="-mr-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-ink-400 hover:bg-ink-100 hover:text-ink-700"
              >
                ×
              </button>
            </div>

            {/* Таблица */}
            <div className="overflow-x-auto overflow-y-auto">
              <table className="w-full min-w-[640px] border-collapse">
                <thead>
                  <tr>
                    <th className="sticky left-0 z-10 bg-white px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-ink-400">
                      Параметр
                    </th>
                    {selected.map((o) => (
                      <th
                        key={o.clinic_id}
                        className="px-4 py-3 text-left align-bottom"
                      >
                        <div className="text-sm font-semibold text-ink-900">
                          {o.clinic_name}
                        </div>
                        <div className="text-xs font-normal text-ink-500">
                          {o.city}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {/* Цена */}
                  <tr>
                    <th className="sticky left-0 z-10 bg-white px-4 py-3 text-left text-sm font-medium text-ink-500 border-t border-ink-100">
                      Цена
                    </th>
                    {selected.map((o, i) => {
                      const win = priceLeaders.has(i);
                      return (
                        <td
                          key={o.clinic_id}
                          className={`${cellBase} ${win ? winCell : ""}`}
                        >
                          <span
                            className={
                              win
                                ? "font-bold text-brand-700"
                                : "font-semibold text-ink-900"
                            }
                          >
                            {win && <span aria-hidden>🏆 </span>}
                            {formatPrice(o.price, o.currency)}
                          </span>
                        </td>
                      );
                    })}
                  </tr>

                  {/* Рейтинг */}
                  <tr>
                    <th className="sticky left-0 z-10 bg-white px-4 py-3 text-left text-sm font-medium text-ink-500 border-t border-ink-100">
                      Рейтинг
                    </th>
                    {selected.map((o, i) => {
                      const win = ratingLeaders.has(i);
                      return (
                        <td
                          key={o.clinic_id}
                          className={`${cellBase} ${win ? winCell : ""}`}
                        >
                          {o.rating != null ? (
                            <span
                              className={
                                win
                                  ? "font-bold text-brand-700"
                                  : "text-ink-700"
                              }
                            >
                              {o.rating.toFixed(1)} ★
                            </span>
                          ) : (
                            <span className="text-ink-400">—</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>

                  {/* Расстояние */}
                  <tr>
                    <th className="sticky left-0 z-10 bg-white px-4 py-3 text-left text-sm font-medium text-ink-500 border-t border-ink-100">
                      Расстояние
                    </th>
                    {selected.map((o, i) => {
                      const km = distances[i];
                      const win = distanceLeaders.has(i);
                      return (
                        <td
                          key={o.clinic_id}
                          className={`${cellBase} ${win ? winCell : ""}`}
                        >
                          {km != null ? (
                            <span
                              className={
                                win
                                  ? "font-bold text-brand-700"
                                  : "text-ink-700"
                              }
                            >
                              {formatDistance(km)}
                            </span>
                          ) : coords == null && onRequestGeo ? (
                            <button
                              type="button"
                              onClick={onRequestGeo}
                              className="text-xs font-medium text-brand-700 underline-offset-2 hover:underline"
                            >
                              Показать расстояние
                            </button>
                          ) : (
                            <span className="text-ink-400">—</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>

                  {/* Онлайн-запись */}
                  <tr>
                    <th className="sticky left-0 z-10 bg-white px-4 py-3 text-left text-sm font-medium text-ink-500 border-t border-ink-100">
                      Онлайн-запись
                    </th>
                    {selected.map((o) => (
                      <td key={o.clinic_id} className={cellBase}>
                        {o.online_booking ? (
                          <span className="badge bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200">
                            да
                          </span>
                        ) : (
                          <span className="badge bg-ink-100 text-ink-500 ring-1 ring-inset ring-ink-200">
                            нет
                          </span>
                        )}
                      </td>
                    ))}
                  </tr>

                  {/* Адрес */}
                  <tr>
                    <th className="sticky left-0 z-10 bg-white px-4 py-3 text-left text-sm font-medium text-ink-500 border-t border-ink-100">
                      Адрес
                    </th>
                    {selected.map((o) => {
                      const addr =
                        [o.district, o.address].filter(Boolean).join(", ") ||
                        "—";
                      return (
                        <td
                          key={o.clinic_id}
                          className={`${cellBase} text-ink-700`}
                        >
                          {addr}
                        </td>
                      );
                    })}
                  </tr>

                  {/* Режим работы */}
                  <tr>
                    <th className="sticky left-0 z-10 bg-white px-4 py-3 text-left text-sm font-medium text-ink-500 border-t border-ink-100">
                      Режим работы
                    </th>
                    {selected.map((o) => (
                      <td
                        key={o.clinic_id}
                        className={`${cellBase} text-ink-700`}
                      >
                        {o.working_hours || "—"}
                      </td>
                    ))}
                  </tr>

                  {/* Обновлено */}
                  <tr>
                    <th className="sticky left-0 z-10 bg-white px-4 py-3 text-left text-sm font-medium text-ink-500 border-t border-ink-100">
                      Обновлено
                    </th>
                    {selected.map((o, i) => {
                      const days = ages[i];
                      const win = freshLeaders.has(i);
                      return (
                        <td
                          key={o.clinic_id}
                          className={`${cellBase} ${win ? winCell : ""}`}
                        >
                          <span
                            className={
                              win
                                ? "font-bold text-brand-700"
                                : "text-ink-700"
                            }
                          >
                            {freshnessLabel(days)}
                          </span>
                          <span className="mt-0.5 block text-xs text-ink-400">
                            {formatDate(o.valid_from)}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                </tbody>
              </table>
            </div>

            {/* Подвал */}
            <div className="flex items-center justify-between gap-3 border-t border-ink-100 px-5 py-3">
              <span className="text-xs text-ink-400">
                🏆 — лучшее предложение по параметру
              </span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-1.5 text-sm font-medium text-ink-600 hover:bg-ink-100"
              >
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
