"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  catalogExportUrl,
  getIngestionRuns,
  getIngestionStats,
  issuePortalAccess,
  runScheduled,
  scrapeSite,
  uploadBatch,
} from "@/lib/api";
import type { BatchResult, IngestionRun, IngestionStats } from "@/lib/types";

export default function AdminPage() {
  const [stats, setStats] = useState<IngestionStats | null>(null);
  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([getIngestionStats(), getIngestionRuns(50)]);
      setStats(s);
      setRuns(r);
      setError(null);
    } catch (e) {
      setError(
        e instanceof ApiError ? `Ошибка сервера: ${e.message}` : "Бэкенд недоступен.",
      );
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <header className="mb-8">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-200">
          Кейс 1 · приём данных
        </span>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-ink-900">
          Конвейер приёма прайсов
        </h1>
        <p className="mt-2 max-w-2xl text-ink-600">
          Пакетная обработка архива прайсов клиник, экспорт единого каталога и
          журнал всех прогонов нормализации.
        </p>
        <Link
          href="/admin/review"
          className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline"
        >
          → Очередь на проверку (спорные сопоставления и жалобы)
        </Link>
      </header>

      {error && (
        <div className="mb-6 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-inset ring-red-100">
          {error}
        </div>
      )}

      <HealthBanner stats={stats} />

      <StatsGrid stats={stats} />

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <ExportCard />
        <BatchUploadCard onDone={refresh} />
        <ScrapeCard onDone={refresh} />
        <PortalIssueCard />
      </div>

      <RunsTable runs={runs} />
    </div>
  );
}

function HealthBanner({ stats }: { stats: IngestionStats | null }) {
  if (!stats) return null;
  const alerts: string[] = [];
  if (stats.failed_runs > 0) alerts.push(`${stats.failed_runs} прогонов с ошибкой`);
  if (stats.empty_runs > 0) alerts.push(`${stats.empty_runs} прогонов вернули 0 позиций (источник мог сломаться)`);
  if (stats.reports_new > 0) alerts.push(`${stats.reports_new} жалоб «цена неверная» на проверку`);
  if (alerts.length === 0) {
    return (
      <div className="mb-6 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700 ring-1 ring-inset ring-emerald-100">
        ✓ Конвейер здоров: ошибок и пустых прогонов нет.
      </div>
    );
  }
  return (
    <div className="mb-6 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800 ring-1 ring-inset ring-amber-100">
      <p className="font-medium">⚠ Требует внимания:</p>
      <ul className="mt-1 list-inside list-disc">
        {alerts.map((a) => (
          <li key={a}>{a}</li>
        ))}
      </ul>
    </div>
  );
}

function StatsGrid({ stats }: { stats: IngestionStats | null }) {
  const cards = [
    { label: "Клиник", value: stats?.clinics, hint: stats ? `${stats.cities} городов` : "" },
    { label: "Услуг в справочнике", value: stats?.services },
    { label: "Цен в каталоге", value: stats?.prices },
    { label: "Прогонов приёма", value: stats?.runs },
    {
      label: "На ручной проверке",
      value: stats?.needs_review,
      warn: (stats?.needs_review ?? 0) > 0,
    },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {cards.map((c) => (
        <div key={c.label} className="card p-4">
          <p className="text-xs font-medium text-ink-500">{c.label}</p>
          <p
            className={`mt-1 text-2xl font-bold tracking-tight ${
              c.warn ? "text-amber-600" : "text-ink-900"
            }`}
          >
            {c.value ?? "—"}
          </p>
          {c.hint && <p className="text-xs text-ink-400">{c.hint}</p>}
        </div>
      ))}
    </div>
  );
}

function ScrapeCard({ onDone }: { onDone: () => void }) {
  const [clinicId, setClinicId] = useState("");
  const [url, setUrl] = useState("");
  const [dynamic, setDynamic] = useState(false);
  const [busy, setBusy] = useState<"" | "scrape" | "scheduled">("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function doScrape() {
    if (!clinicId || !url || busy) return;
    setBusy("scrape");
    setErr(null);
    setMsg(null);
    try {
      const r = await scrapeSite(clinicId, url, dynamic);
      setMsg(`Снято позиций: ${r.items_found} · сопоставлено: ${r.matched} · на проверку: ${r.needs_review}`);
      onDone();
    } catch (e) {
      setErr(e instanceof ApiError ? `Ошибка: ${e.message}` : "Автосбор не удался.");
    } finally {
      setBusy("");
    }
  }

  async function doScheduled() {
    if (busy) return;
    setBusy("scheduled");
    setErr(null);
    setMsg(null);
    try {
      const r = await runScheduled();
      setMsg(`Плановый сбор завершён: источников обработано ${r.report.length}.`);
      onDone();
    } catch (e) {
      setErr(e instanceof ApiError ? `Ошибка: ${e.message}` : "Не удалось запустить сбор.");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="card p-5">
      <h2 className="text-base font-semibold text-ink-900">Автосбор с сайта</h2>
      <p className="mt-1 text-sm text-ink-500">
        Снять прайс с публичной страницы клиники (учитывает robots.txt) или запустить
        плановый сбор по всем включённым источникам — то же, что делает cron.
      </p>

      <div className="mt-4 space-y-3">
        <input
          type="text"
          value={clinicId}
          onChange={(e) => setClinicId(e.target.value)}
          placeholder="clinic_id (uuid)"
          className="field w-full py-2 text-sm"
        />
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://клиника.kz/prices"
          className="field w-full py-2 text-sm"
        />
        <label className="flex items-center gap-2 text-sm text-ink-600">
          <input
            type="checkbox"
            checked={dynamic}
            onChange={(e) => setDynamic(e.target.checked)}
            className="h-4 w-4 rounded border-ink-300"
          />
          Динамический рендер (SPA, медленнее)
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={doScrape}
            disabled={!clinicId || !url || busy !== ""}
            className="inline-flex items-center gap-2 rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-glow transition hover:bg-brand-700 disabled:opacity-50"
          >
            {busy === "scrape" ? "Собираю…" : "Снять прайс по URL"}
          </button>
          <button
            type="button"
            onClick={doScheduled}
            disabled={busy !== ""}
            className="inline-flex items-center gap-2 rounded-full border border-ink-200 px-5 py-2.5 text-sm font-semibold text-ink-700 transition hover:border-brand-300 hover:text-brand-700 disabled:opacity-50"
          >
            {busy === "scheduled" ? "Запускаю…" : "Запустить плановый сбор"}
          </button>
        </div>
        {msg && <p className="text-sm text-brand-700">{msg}</p>}
        {err && <p className="text-sm text-red-600">{err}</p>}
      </div>
    </div>
  );
}

function PortalIssueCard() {
  const [clinicId, setClinicId] = useState("");
  const [link, setLink] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="card p-5">
      <h2 className="text-base font-semibold text-ink-900">Портал клиники</h2>
      <p className="mt-1 text-sm text-ink-500">
        Выдать клинике ссылку для самостоятельной проверки и подтверждения цен
        (автосбор → партнёрский актив).
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <input
          type="text"
          value={clinicId}
          onChange={(e) => setClinicId(e.target.value)}
          placeholder="ID клиники (uuid)"
          className="field max-w-[10rem] py-2 text-sm"
        />
        <button
          type="button"
          disabled={!clinicId}
          onClick={async () => {
            setErr(null);
            setLink(null);
            try {
              const res = await issuePortalAccess(clinicId);
              setLink(res.portal_path);
            } catch {
              setErr("Клиника не найдена.");
            }
          }}
          className="rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
        >
          Выдать ссылку
        </button>
      </div>
      {link && (
        <div className="mt-3 rounded-lg bg-ink-50 p-3 text-sm ring-1 ring-inset ring-ink-100">
          <Link href={link} className="break-all font-medium text-brand-700 hover:underline">
            {link}
          </Link>
        </div>
      )}
      {err && <p className="mt-2 text-sm text-red-600">{err}</p>}
    </div>
  );
}

function ExportCard() {
  return (
    <div className="card p-5">
      <h2 className="text-base font-semibold text-ink-900">Экспорт каталога</h2>
      <p className="mt-1 text-sm text-ink-500">
        Единый нормализованный каталог (услуга · клиника · город · цена · источник)
        одним файлом — выходной артефакт обработки.
      </p>
      <div className="mt-4 flex flex-wrap gap-3">
        <a
          href={catalogExportUrl("xlsx")}
          className="inline-flex items-center gap-2 rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-glow transition hover:bg-brand-700"
        >
          <DownloadIcon /> Excel (.xlsx)
        </a>
        <a
          href={catalogExportUrl("csv")}
          className="inline-flex items-center gap-2 rounded-full border border-ink-200 px-5 py-2.5 text-sm font-semibold text-ink-700 transition hover:border-brand-300 hover:text-brand-700"
        >
          <DownloadIcon /> CSV
        </a>
      </div>
    </div>
  );
}

function BatchUploadCard({ onDone }: { onDone: () => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [clinicId, setClinicId] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BatchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function submit() {
    if (files.length === 0 || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await uploadBatch(files, clinicId || undefined);
      setResult(res);
      onDone();
    } catch (e) {
      setError(
        e instanceof ApiError ? `Ошибка: ${e.message}` : "Не удалось загрузить архив.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card p-5">
      <h2 className="text-base font-semibold text-ink-900">Пакетный приём архива</h2>
      <p className="mt-1 text-sm text-ink-500">
        Загрузите .zip или несколько прайсов (xlsx/csv/pdf/скан/фото — OCR). Клиника берётся из
        префикса имени файла <code className="rounded bg-ink-100 px-1">«&lt;id&gt;_прайс.xlsx»</code>
        или из общего поля ниже.
      </p>

      <div className="mt-4 space-y-3">
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".zip,.xlsx,.xls,.csv,.pdf,.png,.jpg,.jpeg,.tiff,.webp"
          onChange={(e) => {
            setFiles(Array.from(e.target.files ?? []));
            setResult(null);
          }}
          className="block w-full text-sm text-ink-600 file:mr-3 file:rounded-full file:border-0 file:bg-brand-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-brand-700 hover:file:bg-brand-100"
        />
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="text"
            value={clinicId}
            onChange={(e) => setClinicId(e.target.value)}
            placeholder="clinic_id (uuid) по умолчанию (опц.)"
            className="field max-w-[16rem] py-2 text-sm"
          />
          <button
            type="button"
            onClick={submit}
            disabled={loading || files.length === 0}
            className="inline-flex items-center gap-2 rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-glow transition hover:bg-brand-700 disabled:opacity-50"
          >
            {loading ? "Обрабатываю…" : `Обработать (${files.length})`}
          </button>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>

      {result && (
        <div className="mt-4 rounded-xl bg-ink-50 p-3 text-sm ring-1 ring-inset ring-ink-100">
          <p className="mb-2 font-medium text-ink-700">
            Файлов: {result.totals.files} · успешно: {result.totals.ok} · позиций:{" "}
            {result.totals.items} · на проверку: {result.totals.needs_review}
          </p>
          <ul className="space-y-1">
            {result.files.map((f, i) => (
              <li key={i} className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-xs text-ink-600">{f.file}</span>
                <span className="shrink-0 text-xs">
                  {f.status === "ok" ? (
                    <span className="text-brand-700">
                      {f.items} позиций{f.needs_review ? `, ${f.needs_review} на проверку` : ""}
                    </span>
                  ) : f.status === "empty" ? (
                    <span className="text-amber-600">пусто</span>
                  ) : (
                    <span className="text-red-600">{f.error}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function RunsTable({ runs }: { runs: IngestionRun[] }) {
  return (
    <div className="mt-8">
      <h2 className="mb-3 text-base font-semibold text-ink-900">
        Журнал прогонов <span className="text-ink-400">({runs.length})</span>
      </h2>
      <div className="card overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-ink-50 text-left text-xs font-medium text-ink-500">
              <tr>
                <th className="px-4 py-2.5">#</th>
                <th className="px-4 py-2.5">Канал</th>
                <th className="px-4 py-2.5">Формат</th>
                <th className="px-4 py-2.5">Статус</th>
                <th className="px-4 py-2.5">Позиций</th>
                <th className="px-4 py-2.5">Итог</th>
                <th className="px-4 py-2.5">Время</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {runs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-ink-400">
                    Прогонов пока нет — загрузите архив прайсов выше.
                  </td>
                </tr>
              ) : (
                runs.map((r) => (
                  <tr key={r.id} className="hover:bg-ink-50/50">
                    <td className="px-4 py-2.5 text-ink-400">{r.id}</td>
                    <td className="px-4 py-2.5">
                      <span className="rounded-full bg-ink-100 px-2 py-0.5 text-xs text-ink-600">
                        {r.channel === "push" ? "загрузка" : "автосбор"}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 uppercase text-ink-500">{r.format}</td>
                    <td className="px-4 py-2.5">
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="px-4 py-2.5 font-medium text-ink-800">{r.items_found}</td>
                    <td className="px-4 py-2.5 text-ink-500">{r.message}</td>
                    <td className="px-4 py-2.5 whitespace-nowrap text-xs text-ink-400">
                      {formatTime(r.created_at)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    normalized: "bg-brand-50 text-brand-700 ring-brand-200",
    parsed: "bg-sky-50 text-sky-700 ring-sky-200",
    started: "bg-ink-100 text-ink-600 ring-ink-200",
    error: "bg-red-50 text-red-700 ring-red-200",
  };
  const cls = map[status] ?? "bg-ink-100 text-ink-600 ring-ink-200";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}>
      {status}
    </span>
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

function DownloadIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4" aria-hidden>
      <path
        d="M10 3v10m0 0 4-4m-4 4-4-4M4 16h12"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
