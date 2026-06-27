"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { ApiError, getRunDetail, reprocessRun, rollbackRun } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import type { RunDetail } from "@/lib/types";

export default function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const runId = Number(id);
  const [data, setData] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reprocessing, setReprocessing] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const router = useRouter();

  async function load() {
    setLoading(true);
    try {
      setData(await getRunDetail(runId));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? `Ошибка: ${e.message}` : "Прогон не найден.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!Number.isNaN(runId)) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  async function doReprocess() {
    if (reprocessing) return;
    setReprocessing(true);
    setMsg(null);
    try {
      await reprocessRun(runId);
      setMsg("Переобработка запущена — обновляю данные…");
      await load();
    } catch (e) {
      setMsg(e instanceof ApiError ? `Ошибка: ${e.message}` : "Не удалось переобработать.");
    } finally {
      setReprocessing(false);
    }
  }

  async function doRollback() {
    if (rollingBack) return;
    const n = data?.counts.positions ?? 0;
    if (!window.confirm(`Откатить прогон #${runId}? Будут удалены ${n} цен этого прогона. Действие необратимо.`)) {
      return;
    }
    setRollingBack(true);
    setMsg(null);
    try {
      const r = await rollbackRun(runId);
      setMsg(`Откат выполнен: удалено ${r.deleted_prices} цен. Возврат на дашборд…`);
      setTimeout(() => router.push("/admin"), 1400);
    } catch (e) {
      setMsg(e instanceof ApiError ? `Ошибка: ${e.message}` : "Не удалось откатить.");
      setRollingBack(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <Link href="/admin" className="text-sm font-medium text-brand-700 hover:underline">
        ← Дашборд приёма
      </Link>

      {loading && !data ? (
        <div className="skeleton mt-4 h-40 w-full rounded-2xl" />
      ) : error ? (
        <div className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-inset ring-red-100">
          {error}
        </div>
      ) : data ? (
        <>
          <header className="mt-4">
            <h1 className="text-2xl font-bold tracking-tight text-ink-900">
              Прогон #{data.run_id}
            </h1>
            <p className="mt-1 text-sm text-ink-500">
              {data.clinic_name ? `${data.clinic_name} · ` : ""}
              {data.channel === "push" ? "загрузка" : "автосбор"} ·{" "}
              {data.format?.toUpperCase()} · {formatTime(data.created_at)}
            </p>
          </header>

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Stat label="Всего позиций" value={data.counts.positions} />
            <Stat label="В каталоге" value={data.counts.matched} tone="ok" />
            <Stat label="На проверке" value={data.counts.needs_review} tone="warn" />
            <Stat label="Аномалии" value={data.counts.anomalies} tone={data.counts.anomalies > 0 ? "warn" : undefined} />
            <Stat label="Статус" value={data.status} />
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            {data.counts.needs_review > 0 && (
              <Link
                href={`/admin/review?run=${data.run_id}`}
                className="rounded-full bg-amber-500 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-amber-600"
              >
                Проверить {data.counts.needs_review} →
              </Link>
            )}
            {data.counts.anomalies > 0 && (
              <Link
                href={`/admin/review?run=${data.run_id}&filter=anomaly`}
                className="rounded-full border border-red-200 px-5 py-2.5 text-sm font-semibold text-red-600 transition hover:bg-red-50"
              >
                Показать {data.counts.anomalies} аномалий
              </Link>
            )}
            {data.has_original && (
              <button
                type="button"
                onClick={doReprocess}
                disabled={reprocessing || rollingBack}
                className="rounded-full border border-ink-200 px-5 py-2.5 text-sm font-semibold text-ink-700 transition hover:border-brand-300 hover:text-brand-700 disabled:opacity-50"
              >
                {reprocessing ? "Переобрабатываю…" : "Переобработать из оригинала 💾"}
              </button>
            )}
            {data.status !== "rolled_back" && (
              <button
                type="button"
                onClick={doRollback}
                disabled={rollingBack || reprocessing}
                className="rounded-full border border-red-200 px-5 py-2.5 text-sm font-semibold text-red-600 transition hover:bg-red-50 disabled:opacity-50"
              >
                {rollingBack ? "Откатываю…" : "Откатить прогон"}
              </button>
            )}
          </div>
          {msg && <p className="mt-2 text-sm text-brand-700">{msg}</p>}

          <h2 className="mb-3 mt-8 text-base font-semibold text-ink-900">
            Позиции <span className="text-ink-400">({data.positions.length})</span>
          </h2>
          <div className="card overflow-hidden p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-ink-50 text-left text-xs font-medium text-ink-500">
                  <tr>
                    <th className="px-4 py-2.5">Исходное имя</th>
                    <th className="px-4 py-2.5">Нормализовано</th>
                    <th className="px-4 py-2.5">Статус</th>
                    <th className="px-4 py-2.5">Резидент</th>
                    <th className="px-4 py-2.5">Нерезидент</th>
                    <th className="px-4 py-2.5">Увер.</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  {data.positions.map((p) => (
                    <tr key={p.price_id} className="hover:bg-ink-50/50">
                      <td className="px-4 py-2.5 text-ink-600">{p.raw_name}</td>
                      <td className="px-4 py-2.5 font-medium text-ink-800">
                        {p.canonical_name ?? <span className="text-ink-300">—</span>}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="inline-flex items-center gap-1">
                          {p.status === "matched" ? (
                            <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-200">
                              в каталоге
                            </span>
                          ) : (
                            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 ring-1 ring-inset ring-amber-200">
                              на проверке
                            </span>
                          )}
                          {p.is_anomaly && (
                            <span title="Ценовая аномалия" className="text-red-600">⚠</span>
                          )}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-ink-700">
                        {p.price_resident != null ? formatPrice(p.price_resident) : p.price != null ? formatPrice(p.price) : "—"}
                      </td>
                      <td className="px-4 py-2.5 text-ink-500">
                        {p.price_nonresident != null ? formatPrice(p.price_nonresident) : "—"}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-ink-400">
                        {Math.round(p.match_confidence * 100)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: "ok" | "warn" }) {
  const color = tone === "ok" ? "text-brand-700" : tone === "warn" ? "text-amber-600" : "text-ink-900";
  return (
    <div className="card p-4">
      <p className="text-xs font-medium text-ink-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold tracking-tight ${color}`}>
        {typeof value === "number" ? value.toLocaleString("ru-RU") : value}
      </p>
    </div>
  );
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
