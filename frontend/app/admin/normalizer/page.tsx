"use client";

import { useMemo, useState } from "react";
import { previewNormalization, ApiError } from "@/lib/api";
import type { NormalizationLine, NormItem, NormMethod } from "@/lib/types";

// Реальное направление: смесь шума (дата/ФИО/заголовок) и панелей (липидограмма,
// коагулограмма), которые движок должен разобрать на отдельные услуги.
const SAMPLE = [
  "НАПРАВЛЕНИЕ НА ЛАБОРАТОРНЫЕ ИССЛЕДОВАНИЯ",
  "Пациент: Тестовый пациент",
  "Дата: 27.06.2026",
  "ОАК развернутый + лейкоцитарная формула + СОЭ",
  "Glucose fasting — глюкоза крови натощак",
  "Липидограмма: общий холестерин, ЛПНП, ЛПВП, триглицериды",
  "Коагулограмма: ПТИ, МНО (INR), АЧТВ, фибриноген",
  "Ферритин (феретин)",
  "HbA1c (гликированный гемоглобин)",
].join("\n");

const METHOD_META: Record<NormMethod, { label: string; cls: string }> = {
  fuzzy: { label: "Нечёткое сопоставление", cls: "bg-brand-50 text-brand-700 ring-brand-200" },
  "fuzzy-weak": { label: "Нечёткое (слабое)", cls: "bg-amber-50 text-amber-700 ring-amber-200" },
  semantic: { label: "Семантика (смысл)", cls: "bg-teal-50 text-teal-700 ring-teal-200" },
  llm: { label: "LLM-разрешение", cls: "bg-violet-50 text-violet-700 ring-violet-200" },
  panel: { label: "Панель (разбита)", cls: "bg-indigo-50 text-indigo-700 ring-indigo-200" },
  new: { label: "Новая услуга", cls: "bg-sky-50 text-sky-700 ring-sky-200" },
};

// Причины фильтрации шума (бэкенд присылает короткий ключ).
const REASON_LABEL: Record<string, string> = {
  дата: "дата",
  инструкция: "инструкция",
  заголовок: "заголовок",
  "метаданные бланка": "метаданные бланка",
};

function confColor(c: number): string {
  if (c >= 0.85) return "bg-brand-500";
  if (c >= 0.7) return "bg-amber-500";
  return "bg-ink-300";
}

// Один распознанный элемент: эталон, категория, метод, уверенность, статус.
function ItemRow({ item, nested }: { item: NormItem; nested?: boolean }) {
  const m = METHOD_META[item.method] ?? METHOD_META.fuzzy;
  const unmatched = item.status === "unmatched";
  const pct = Math.round(item.confidence * 100);
  return (
    <div className={nested ? "rounded-xl border border-ink-100 bg-ink-50/60 p-3" : ""}>
      <div className="flex flex-wrap items-center gap-2 text-ink-400">
        <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" aria-hidden>
          <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className={`font-semibold ${unmatched ? "text-ink-400" : "text-ink-900"}`}>
          {item.canonical?.trim() || "—"}
        </span>
        {unmatched ? (
          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 ring-1 ring-inset ring-amber-200">
            не распознано
          </span>
        ) : (
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset ${m.cls}`}>
            {m.label}
          </span>
        )}
        {item.category && <span className="ml-auto text-xs text-ink-400">{item.category}</span>}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-100">
          <div
            className={`h-full rounded-full ${unmatched ? "bg-ink-300" : confColor(item.confidence)}`}
            style={{ width: `${Math.max(pct, 4)}%` }}
          />
        </div>
        <span className="w-10 text-right text-xs font-medium text-ink-500">{pct}%</span>
      </div>
    </div>
  );
}

export default function NormalizerPage() {
  const [text, setText] = useState(SAMPLE);
  const [rows, setRows] = useState<NormalizationLine[] | null>(null);
  const [strict, setStrict] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    const names = text.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 30);
    if (names.length === 0 || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await previewNormalization(names);
      setRows(res.results);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? `Ошибка сервера: ${err.message}`
          : "Не удалось связаться с движком нормализации.",
      );
    } finally {
      setLoading(false);
    }
  }

  // Строгий режим: прячем шум и оставляем только уверенно сопоставленные услуги.
  const view = useMemo(() => {
    if (!rows) return null;
    return rows
      .map((line) => {
        if (line.kind === "noise") return strict ? null : line;
        const items = strict ? line.items.filter((i) => i.status === "matched") : line.items;
        if (strict && items.length === 0) return null; // нечего показывать — скрываем строку
        return { ...line, items };
      })
      .filter((l): l is NormalizationLine => l !== null);
  }, [rows, strict]);

  // Сводка по исходному (нефильтрованному) результату.
  const stats = useMemo(() => {
    if (!rows) return null;
    let noise = 0, services = 0, matched = 0, unmatched = 0;
    for (const l of rows) {
      if (l.kind === "noise") { noise++; continue; }
      services++;
      for (const it of l.items) it.status === "matched" ? matched++ : unmatched++;
    }
    return { noise, services, matched, unmatched };
  }, [rows]);

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <div className="mb-8 max-w-2xl">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-200">
          ★ Ядро платформы
        </span>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-ink-900">
          Умная нормализация направлений
        </h1>
        <p className="mt-3 text-ink-600">
          Вставьте сырое направление целиком — со штампами, датами и панелями.
          Движок отфильтрует служебные строки, разобьёт панели (например,
          «Липидограмму») на отдельные услуги и сведёт каждую к справочнику с
          указанием метода и уверенности. Ничего не записывается в базу.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <label className="mb-2 block text-sm font-medium text-ink-700">
            Текст направления — по строке на услугу
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={12}
            spellCheck={false}
            className="w-full resize-y rounded-2xl border border-ink-200 bg-white p-4 font-mono text-sm text-ink-800 outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button type="button" onClick={run} disabled={loading} className="btn-primary">
              {loading ? "Нормализую…" : "Нормализовать"}
            </button>
            <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-ink-200 bg-white px-3 py-2.5">
              <input
                type="checkbox"
                checked={strict}
                onChange={(e) => setStrict(e.target.checked)}
                className="h-4 w-4 rounded accent-brand-600"
              />
              <span className="text-sm font-medium text-ink-700">Строгий режим</span>
            </label>
          </div>
          <p className="mt-2 text-xs text-ink-400">
            Строгий режим скрывает шум и нераспознанное — остаются только уверенные совпадения.
          </p>
          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        </div>

        <div className="lg:col-span-3">
          {!rows && !loading && (
            <div className="flex h-full min-h-[280px] items-center justify-center rounded-2xl border border-dashed border-ink-200 bg-ink-50 px-6 text-center text-sm text-ink-400">
              Результаты появятся здесь
            </div>
          )}

          {stats && (
            <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-500">
              <span><b className="text-ink-800">{stats.services}</b> услуг(и)</span>
              <span><b className="text-amber-600">{stats.unmatched}</b> не распознано</span>
              <span><b className="text-ink-400">{stats.noise}</b> строк отфильтровано</span>
              {strict && <span className="font-medium text-brand-700">строгий режим включён</span>}
            </div>
          )}

          {view && (
            <div className="space-y-2.5">
              {view.length === 0 && (
                <div className="rounded-2xl border border-dashed border-ink-200 bg-ink-50 px-6 py-8 text-center text-sm text-ink-400">
                  В строгом режиме уверенных совпадений не найдено.
                </div>
              )}

              {view.map((line, i) => {
                // Шум — приглушённая строка с причиной фильтрации.
                if (line.kind === "noise") {
                  return (
                    <div
                      key={i}
                      className="flex flex-wrap items-center gap-2 rounded-2xl border border-ink-100 bg-ink-50/70 px-4 py-3 animate-fade-up"
                      style={{ animationDelay: `${i * 40}ms` }}
                    >
                      <span className="font-mono text-sm text-ink-400 line-through decoration-ink-300">
                        {line.raw}
                      </span>
                      <span className="ml-auto rounded-full bg-ink-100 px-2 py-0.5 text-[10px] font-semibold text-ink-500">
                        пропущено
                      </span>
                      {line.reason && (
                        <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-medium text-ink-500 ring-1 ring-inset ring-ink-200">
                          {REASON_LABEL[line.reason] ?? line.reason}
                        </span>
                      )}
                    </div>
                  );
                }

                // Панель: исходная строка разбита на несколько услуг.
                if (line.items.length > 1) {
                  return (
                    <div
                      key={i}
                      className="rounded-2xl border border-ink-100 bg-white p-4 shadow-card animate-fade-up"
                      style={{ animationDelay: `${i * 40}ms` }}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono text-sm text-ink-500">{line.raw}</span>
                        <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-[11px] font-medium text-indigo-700 ring-1 ring-inset ring-indigo-200">
                          разбита на {line.items.length}
                        </span>
                      </div>
                      <div className="mt-3 space-y-2">
                        {line.items.map((it, j) => (
                          <ItemRow key={j} item={it} nested />
                        ))}
                      </div>
                    </div>
                  );
                }

                // Обычная строка: одно сопоставление (или одно нераспознанное).
                const it = line.items[0];
                return (
                  <div
                    key={i}
                    className="rounded-2xl border border-ink-100 bg-white p-4 shadow-card animate-fade-up"
                    style={{ animationDelay: `${i * 40}ms` }}
                  >
                    <div className="mb-2 font-mono text-sm text-ink-500">{line.raw}</div>
                    {it ? (
                      <ItemRow item={it} />
                    ) : (
                      <span className="text-xs text-ink-400">нет элементов</span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
