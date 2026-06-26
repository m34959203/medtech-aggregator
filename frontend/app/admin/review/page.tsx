"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  aiResolveQueue,
  getReviewQueue,
  getServices,
  reviewPrice,
  reviewReport,
} from "@/lib/api";
import { formatPrice } from "@/lib/format";
import type { ReviewItem, ReviewQueue, ReviewReport } from "@/lib/types";

export default function ReviewPage() {
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [services, setServices] = useState<{ id: number; canonical_name: string }[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [q, s] = await Promise.all([getReviewQueue(), getServices()]);
      setQueue(q);
      setServices(s);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? `Ошибка: ${e.message}` : "Бэкенд недоступен.");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <header className="mb-6">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-200">
          Спринт-2 · human-in-the-loop
        </span>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-ink-900">
          Очередь на проверку
        </h1>
        <p className="mt-2 text-ink-600">
          Спорные сопоставления (уверенность ниже{" "}
          {queue ? Math.round(queue.threshold * 100) : "—"}%) и жалобы «цена неверная».
          Оператор подтверждает, переназначает или удаляет.
        </p>
      </header>

      {error && (
        <div className="mb-6 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-inset ring-red-100">
          {error}
        </div>
      )}

      {queue && queue.low_confidence.length > 0 && (
        <AiResolvePanel total={queue.low_confidence.length} onDone={refresh} />
      )}

      <section className="mb-8">
        <h2 className="mb-3 text-base font-semibold text-ink-900">
          Спорные сопоставления{" "}
          <span className="text-ink-400">({queue?.low_confidence.length ?? 0})</span>
        </h2>
        {queue && queue.low_confidence.length === 0 ? (
          <div className="card p-6 text-center text-sm text-ink-500">
            Очередь пуста — все сопоставления уверенные.
          </div>
        ) : (
          <ul className="space-y-2.5">
            {queue?.low_confidence.map((it) => (
              <ReviewRow key={it.price_id} item={it} services={services} onDone={refresh} />
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-base font-semibold text-ink-900">
          Жалобы «цена неверная»{" "}
          <span className="text-ink-400">({queue?.reports.length ?? 0})</span>
        </h2>
        {queue && queue.reports.length === 0 ? (
          <div className="card p-6 text-center text-sm text-ink-500">Жалоб нет.</div>
        ) : (
          <ul className="space-y-2.5">
            {queue?.reports.map((r) => (
              <ReportRow key={r.id} report={r} onDone={refresh} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function AiResolvePanel({ total, onDone }: { total: number; onDone: () => void }) {
  const [running, setRunning] = useState(false);
  const [applied, setApplied] = useState(0);
  const [done, setDone] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);

  async function run() {
    if (running) return;
    setRunning(true);
    setApplied(0);
    setDone(0);
    setMsg(null);
    let totalApplied = 0;
    let processedTotal = 0;
    let prevRemaining = Infinity;
    try {
      // цикл по батчам, пока очередь убывает (защита от зацикливания при недоступном ИИ)
      for (let i = 0; i < 60; i++) {
        const r = await aiResolveQueue({ limit: 25, apply: true, min_confidence: 0.8 });
        totalApplied += r.applied;
        processedTotal += r.processed;
        setApplied(totalApplied);
        setDone(processedTotal);
        if (r.processed === 0) break;
        // нет прогресса (ИИ ничего не применил и очередь не уменьшилась) → стоп
        if (r.applied === 0 && r.remaining >= prevRemaining) {
          setMsg(
            "ИИ не смог уверенно разобрать оставшиеся позиции (или туннель LLM недоступен). " +
              "Разберите их вручную ниже.",
          );
          break;
        }
        prevRemaining = r.remaining;
        if (r.remaining === 0) break;
      }
      onDone();
    } catch (e) {
      setMsg(e instanceof ApiError ? `Ошибка: ${e.message}` : "Бэкенд недоступен.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="card mb-6 flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div className="flex items-center gap-2 font-medium text-ink-900">
          <span>🤖 ИИ-разбор очереди</span>
        </div>
        <p className="mt-0.5 text-sm text-ink-500">
          ИИ подберёт услугу из официального справочника, подтвердит верные и пометит
          мусор. Применяются только уверенные решения (≥80%); спорные останутся вам.
        </p>
        {(running || done > 0) && (
          <p className="mt-1 text-sm text-brand-700">
            Обработано {done} из ~{total} · применено {applied}
            {running ? " · идёт…" : ""}
          </p>
        )}
        {msg && <p className="mt-1 text-sm text-amber-700">{msg}</p>}
      </div>
      <button onClick={run} disabled={running} className="btn-primary shrink-0 text-sm">
        {running ? "Разбираю…" : "Запустить ИИ-разбор"}
      </button>
    </div>
  );
}

function ReviewRow({
  item,
  services,
  onDone,
}: {
  item: ReviewItem;
  services: { id: number; canonical_name: string }[];
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState<number>(item.service_id);

  async function act(action: "confirm" | "reassign" | "reject") {
    if (busy) return;
    setBusy(true);
    try {
      await reviewPrice(item.price_id, action, action === "reassign" ? target : undefined);
      onDone();
    } catch {
      setBusy(false);
    }
  }

  return (
    <li className="card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink-900">
            {item.clinic_name} <span className="text-ink-400">· {item.city}</span>
          </p>
          <p className="mt-0.5 text-xs text-ink-500">
            в прайсе: «{item.raw_name}» → <b>{item.canonical_name}</b>
          </p>
          <p className="mt-1 text-xs">
            <span className="rounded bg-amber-50 px-1.5 py-0.5 font-medium text-amber-700">
              уверенность {Math.round(item.match_confidence * 100)}%
            </span>{" "}
            <span className="text-ink-500">{formatPrice(item.price, item.currency)}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => act("confirm")}
            disabled={busy}
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
          >
            Подтвердить
          </button>
          <select
            value={target}
            onChange={(e) => setTarget(Number(e.target.value))}
            className="field max-w-[12rem] py-1.5 text-xs"
            aria-label="Переназначить на услугу"
          >
            {services.map((s) => (
              <option key={s.id} value={s.id}>
                {s.canonical_name}
              </option>
            ))}
          </select>
          <button
            onClick={() => act("reassign")}
            disabled={busy || target === item.service_id}
            className="rounded-lg border border-ink-200 px-3 py-1.5 text-xs font-medium text-ink-700 transition hover:border-brand-300 disabled:opacity-40"
          >
            Переназначить
          </button>
          <button
            onClick={() => act("reject")}
            disabled={busy}
            className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 transition hover:bg-red-50 disabled:opacity-50"
          >
            Удалить
          </button>
        </div>
      </div>
    </li>
  );
}

function ReportRow({ report, onDone }: { report: ReviewReport; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <li className="card flex flex-wrap items-center justify-between gap-3 p-4">
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink-900">
          {report.clinic_name || "—"} · {report.service || "—"}
        </p>
        <p className="text-xs text-ink-500">
          {report.price != null ? formatPrice(report.price) : "цена не указана"}
          {report.note ? ` · «${report.note}»` : ""}
        </p>
      </div>
      <button
        onClick={async () => {
          if (busy) return;
          setBusy(true);
          try {
            await reviewReport(report.id, "fixed");
            onDone();
          } catch {
            setBusy(false);
          }
        }}
        disabled={busy}
        className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
      >
        Обработано
      </button>
    </li>
  );
}
