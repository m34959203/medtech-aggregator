"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  getCities,
  recommendBasket,
  recommendBasketFile,
} from "@/lib/api";
import { formatPrice } from "@/lib/format";
import type { BasketItem, BasketResult } from "@/lib/types";

const SAMPLE = "Направление на анализы:\n1. Общий анализ крови\n2. Глюкоза\n3. ТТГ\n4. Витамин D";

export default function RecipePage() {
  const [text, setText] = useState(SAMPLE);
  const [city, setCity] = useState("");
  const [cities, setCities] = useState<string[]>([]);
  const [result, setResult] = useState<BasketResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getCities().then(setCities).catch(() => {});
  }, []);

  async function run(promise: Promise<BasketResult>) {
    setLoading(true);
    setError(null);
    try {
      setResult(await promise);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Не удалось обработать направление.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6">
      <header className="mb-8 max-w-2xl">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-200">
          Направление врача → выгодный маршрут
        </span>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-ink-900">
          Куда сдать анализы по направлению
        </h1>
        <p className="mt-3 text-ink-600">
          Сфотографируйте направление или вставьте список анализов — система
          распознает услуги и подскажет, где это дешевле и можно ли сдать всё
          в одной клинике.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-3 lg:col-span-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={8}
            className="w-full resize-y rounded-2xl border border-ink-200 bg-white p-4 text-sm text-ink-800 outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          />
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
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => run(recommendBasket({ text, city: city || undefined }))}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-glow transition hover:bg-brand-700 disabled:opacity-50"
            >
              {loading ? "Считаю…" : "Найти выгодно"}
            </button>
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={loading}
              className="rounded-full border border-ink-200 px-5 py-2.5 text-sm font-medium text-ink-700 transition hover:border-brand-300 hover:text-brand-700 disabled:opacity-50"
            >
              Загрузить фото/скан
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".png,.jpg,.jpeg,.tiff,.webp,.pdf,.txt"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) run(recommendBasketFile(f, city || undefined));
                if (fileRef.current) fileRef.current.value = "";
              }}
            />
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        <div className="lg:col-span-3">
          {!result && !loading && (
            <div className="flex h-full min-h-[280px] items-center justify-center rounded-2xl border border-dashed border-ink-200 bg-ink-50 px-6 text-center text-sm text-ink-400">
              Результат появится здесь
            </div>
          )}
          {result && <BasketResultView result={result} city={city} />}
        </div>
      </div>
    </div>
  );
}

function BasketResultView({ result, city }: { result: BasketResult; city: string }) {
  const single = result.best_single_clinic;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="card p-4">
          <p className="text-xs font-medium text-ink-500">Минимум (по разным клиникам)</p>
          <p className="mt-1 text-2xl font-bold tracking-tight text-brand-700">
            {formatPrice(result.total_cheapest_mixed)}
          </p>
          <p className="text-xs text-ink-400">распознано услуг: {result.services_found}</p>
        </div>
        {single && (
          <div className="card p-4 ring-2 ring-brand-200">
            <p className="text-xs font-medium text-ink-500">В одной клинике</p>
            <p className="mt-1 text-base font-semibold text-ink-900">{single.clinic_name}</p>
            <p className="text-sm text-ink-600">
              {formatPrice(single.total)} · покрывает {single.covered} из {result.services_found}
            </p>
            {single.missing.length > 0 && (
              <p className="mt-1 text-xs text-amber-600">нет: {single.missing.join(", ")}</p>
            )}
            {single.phone && (
              <a
                href={`tel:${single.phone.replace(/[^\d+]/g, "")}`}
                className="mt-2 inline-block text-sm font-medium text-brand-700 hover:underline"
              >
                {single.phone}
              </a>
            )}
          </div>
        )}
      </div>

      <ul className="space-y-2">
        {result.recognized.map((it) => (
          <ItemRow key={it.service_id} item={it} city={city} />
        ))}
      </ul>

      {result.unrecognized.length > 0 && (
        <p className="rounded-xl bg-ink-50 px-4 py-3 text-xs text-ink-500">
          Не распознано как услуга: {result.unrecognized.join(" · ")}
        </p>
      )}
    </div>
  );
}

function ItemRow({ item, city }: { item: BasketItem; city: string }) {
  const href = city
    ? `/service/${item.service_id}?city=${encodeURIComponent(city)}`
    : `/service/${item.service_id}`;
  return (
    <li className="card flex items-center justify-between gap-3 p-3.5">
      <div className="min-w-0">
        <Link href={href} className="text-sm font-medium text-ink-900 hover:text-brand-700">
          {item.canonical}
        </Link>
        <p className="truncate text-xs text-ink-400">
          из направления: «{item.input}»
        </p>
      </div>
      <div className="shrink-0 text-right">
        {item.cheapest ? (
          <>
            <p className="text-sm font-bold text-brand-700">
              {formatPrice(item.cheapest.price)}
            </p>
            <Link
              href={`/clinics/${item.cheapest.clinic_id}`}
              className="text-xs font-medium text-ink-600 underline-offset-2 hover:text-brand-700 hover:underline"
              title="Страница лаборатории — все услуги, адрес, контакты"
            >
              {item.cheapest.clinic_name}
            </Link>
            <div className="mt-0.5 flex items-center justify-end gap-x-3">
              <Link
                href={`/clinics/${item.cheapest.clinic_id}`}
                className="text-[11px] font-medium text-brand-700 underline-offset-2 hover:underline"
              >
                Лаборатория →
              </Link>
              {item.cheapest.lat != null && item.cheapest.lng != null && (
                <a
                  href={`https://yandex.ru/maps/?rtext=~${item.cheapest.lat},${item.cheapest.lng}&rtt=auto`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-[11px] font-medium text-brand-700 underline-offset-2 hover:underline"
                  title="Маршрут до лаборатории (Яндекс.Карты)"
                >
                  <svg viewBox="0 0 20 20" fill="none" className="h-3 w-3" aria-hidden>
                    <path d="M10 18s6-5.3 6-10A6 6 0 1 0 4 8c0 4.7 6 10 6 10Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                    <circle cx="10" cy="8" r="2" stroke="currentColor" strokeWidth="1.5" />
                  </svg>
                  Карта
                </a>
              )}
            </div>
          </>
        ) : (
          <p className="text-xs text-ink-400">нет предложений</p>
        )}
      </div>
    </li>
  );
}
