"use client";

import { useState } from "react";
import { previewNormalization, ApiError } from "@/lib/api";
import type { NormalizationPreview, NormMethod } from "@/lib/types";

const SAMPLE = [
  "ОАК (5 параметров) с лейкоформулой",
  "Кл. ан. крови развёрнутый",
  "Сахар крови натощак",
  "УЗ-исследование почек",
  "Консультация кардиолога, первичная",
  "ЭХОКГ сердца",
].join("\n");

const METHOD_META: Record<NormMethod, { label: string; cls: string }> = {
  fuzzy: { label: "Нечёткое сопоставление", cls: "bg-brand-50 text-brand-700 ring-brand-200" },
  "fuzzy-weak": { label: "Нечёткое (слабое)", cls: "bg-amber-50 text-amber-700 ring-amber-200" },
  llm: { label: "LLM-разрешение", cls: "bg-violet-50 text-violet-700 ring-violet-200" },
  new: { label: "Новая услуга", cls: "bg-sky-50 text-sky-700 ring-sky-200" },
};

function confColor(c: number): string {
  if (c >= 0.85) return "bg-brand-500";
  if (c >= 0.7) return "bg-amber-500";
  return "bg-ink-300";
}

export default function NormalizerPage() {
  const [text, setText] = useState(SAMPLE);
  const [rows, setRows] = useState<NormalizationPreview[] | null>(null);
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

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <div className="mb-8 max-w-2xl">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-200">
          ★ Ядро платформы
        </span>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-ink-900">
          Умная нормализация — вживую
        </h1>
        <p className="mt-3 text-ink-600">
          Клиники называют одну и ту же услугу по-разному. Движок сводит любой разнобой к единому
          справочнику: сначала нечёткое сопоставление (rapidfuzz), а в спорных случаях —
          LLM. Введите <b>любые</b> названия — увидите, как и с какой уверенностью движок их разнесёт.
          Ничего не записывается в базу.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <label className="mb-2 block text-sm font-medium text-ink-700">
            Названия услуг — по одному в строке
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={10}
            spellCheck={false}
            className="w-full resize-y rounded-2xl border border-ink-200 bg-white p-4 font-mono text-sm text-ink-800 outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          />
          <button
            type="button"
            onClick={run}
            disabled={loading}
            className="mt-3 inline-flex items-center gap-2 rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-glow transition hover:bg-brand-700 disabled:opacity-50"
          >
            {loading ? "Нормализую…" : "Нормализовать"}
          </button>
          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        </div>

        <div className="lg:col-span-3">
          {!rows && !loading && (
            <div className="flex h-full min-h-[280px] items-center justify-center rounded-2xl border border-dashed border-ink-200 bg-ink-50 px-6 text-center text-sm text-ink-400">
              Результаты появятся здесь
            </div>
          )}
          {rows && (
            <div className="space-y-2.5">
              {rows.map((r, i) => {
                const m = METHOD_META[r.method];
                return (
                  <div
                    key={i}
                    className="rounded-2xl border border-ink-100 bg-white p-4 shadow-card animate-fade-up"
                    style={{ animationDelay: `${i * 40}ms` }}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-sm text-ink-500">{r.raw}</span>
                      <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ring-1 ring-inset ${m.cls}`}>
                        {m.label}
                      </span>
                    </div>
                    <div className="mt-2 flex items-center gap-2 text-ink-400">
                      <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" aria-hidden>
                        <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                      <span className="font-semibold text-ink-900">{r.canonical}</span>
                      {r.is_new && (
                        <span className="rounded bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-700">
                          новая в справочнике
                        </span>
                      )}
                      <span className="ml-auto text-xs text-ink-400">{r.category}</span>
                    </div>
                    <div className="mt-2.5 flex items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-ink-100">
                        <div
                          className={`h-full rounded-full ${confColor(r.confidence)}`}
                          style={{ width: `${Math.round(r.confidence * 100)}%` }}
                        />
                      </div>
                      <span className="w-10 text-right text-xs font-medium text-ink-500">
                        {Math.round(r.confidence * 100)}%
                      </span>
                    </div>
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
