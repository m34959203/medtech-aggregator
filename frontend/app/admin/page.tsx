"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  catalogExportUrl,
  getIngestionRuns,
  getIngestionStats,
  getPartners,
  issuePortalAccess,
  runScheduled,
  scrapeSite,
  uploadArchive,
  uploadBatch,
  waStatus,
} from "@/lib/api";
import type { Partner, WaStatus } from "@/lib/api";
import type { BatchResult, IngestionRun, IngestionStats } from "@/lib/types";

const AUTO_REFRESH_MS = 30_000;

export default function AdminPage() {
  const [stats, setStats] = useState<IngestionStats | null>(null);
  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [wa, setWa] = useState<WaStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const [s, r, w] = await Promise.all([
        getIngestionStats(),
        getIngestionRuns(50),
        waStatus().catch(() => null), // туннель опционален — не валим дашборд
      ]);
      setStats(s);
      setRuns(r);
      setWa(w);
      setUpdatedAt(Date.now());
      setError(null);
    } catch (e) {
      setError(
        e instanceof ApiError ? `Ошибка сервера: ${e.message}` : "Бэкенд недоступен.",
      );
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }, []);

  // Список клиник для пикеров — грузим один раз.
  useEffect(() => {
    getPartners()
      .then(setPartners)
      .catch(() => setPartners([]));
  }, []);

  // Первичная загрузка + авто-обновление статистики/журнала/WA.
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, AUTO_REFRESH_MS);
    return () => clearInterval(t);
  }, [refresh]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <header className="mb-8">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
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
          </div>
          <RefreshControl updatedAt={updatedAt} refreshing={refreshing} onRefresh={refresh} />
        </div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-sm font-medium">
          <Link href="/admin/review" className="text-brand-700 hover:underline">
            → Очередь на проверку
          </Link>
          <Link href="/admin/whatsapp" className="text-brand-700 hover:underline">
            → WhatsApp-туннель
          </Link>
          <Link href="/admin/normalizer" className="text-brand-700 hover:underline">
            → Нормализатор
          </Link>
        </div>
      </header>

      {error && (
        <div className="mb-6 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-inset ring-red-100">
          {error}
        </div>
      )}

      <div className="mb-6 grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <HealthBanner stats={stats} loading={loading} />
        </div>
        <WaStatusCard wa={wa} loading={loading} />
      </div>

      <StatsGrid stats={stats} loading={loading} />

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <ExportCard />
        <BatchUploadCard onDone={refresh} partners={partners} />
        <ScrapeCard onDone={refresh} partners={partners} />
        <PortalIssueCard partners={partners} />
      </div>

      <RunsTable runs={runs} loading={loading} />
    </div>
  );
}

function RefreshControl({
  updatedAt,
  refreshing,
  onRefresh,
}: {
  updatedAt: number | null;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const [, force] = useState(0);
  // Перерисовка раз в 10с, чтобы «N сек назад» не залипало.
  useEffect(() => {
    const t = setInterval(() => force((n) => n + 1), 10_000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="flex items-center gap-2 text-xs text-ink-400">
      <span>{updatedAt ? `обновлено ${ago(updatedAt)}` : "—"}</span>
      <button
        type="button"
        onClick={onRefresh}
        disabled={refreshing}
        className="inline-flex items-center gap-1.5 rounded-full border border-ink-200 px-3 py-1.5 font-medium text-ink-600 transition hover:border-brand-300 hover:text-brand-700 disabled:opacity-50"
      >
        <svg
          viewBox="0 0 20 20"
          fill="none"
          className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
          aria-hidden
        >
          <path
            d="M15.3 8A5.5 5.5 0 1 0 16 11"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
          />
          <path d="M16 4v4h-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Обновить
      </button>
    </div>
  );
}

function HealthBanner({ stats, loading }: { stats: IngestionStats | null; loading: boolean }) {
  if (loading && !stats) return <div className="skeleton h-[58px] w-full rounded-xl" />;
  if (!stats) return null;
  const alerts: string[] = [];
  if (stats.failed_runs > 0) alerts.push(`${stats.failed_runs} прогонов с ошибкой`);
  if (stats.empty_runs > 0) alerts.push(`${stats.empty_runs} прогонов вернули 0 позиций (источник мог сломаться)`);
  if (stats.reports_new > 0) alerts.push(`${stats.reports_new} жалоб «цена неверная» на проверку`);
  if (alerts.length === 0) {
    return (
      <div className="flex h-full items-center rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700 ring-1 ring-inset ring-emerald-100">
        ✓ Конвейер здоров: ошибок и пустых прогонов нет.
      </div>
    );
  }
  return (
    <div className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800 ring-1 ring-inset ring-amber-100">
      <p className="font-medium">⚠ Требует внимания:</p>
      <ul className="mt-1 list-inside list-disc">
        {alerts.map((a) => (
          <li key={a}>{a}</li>
        ))}
      </ul>
    </div>
  );
}

function WaStatusCard({ wa, loading }: { wa: WaStatus | null; loading: boolean }) {
  if (loading && !wa) return <div className="skeleton h-[58px] w-full rounded-xl" />;
  const status = wa?.status ?? "disconnected";
  const connected = status === "connected";
  const dot = connected
    ? "bg-emerald-500"
    : status === "qr_ready" || status === "connecting"
      ? "bg-amber-500"
      : "bg-ink-300";
  const label = connected
    ? "WhatsApp подключён"
    : status === "qr_ready"
      ? "Готов к привязке (QR)"
      : status === "connecting"
        ? "Подключение…"
        : "WhatsApp не привязан";
  return (
    <Link
      href="/admin/whatsapp"
      className="card flex items-center justify-between gap-3 p-4 transition hover:border-brand-300"
    >
      <div className="flex items-center gap-2.5">
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${dot}`} />
        <div>
          <p className="text-sm font-medium text-ink-800">{label}</p>
          {connected && wa?.phoneNumber ? (
            <p className="text-xs text-ink-400">+{wa.phoneNumber}</p>
          ) : (
            <p className="text-xs text-ink-400">Открыть привязку →</p>
          )}
        </div>
      </div>
      <svg viewBox="0 0 24 24" className="h-6 w-6 shrink-0 text-emerald-500" fill="currentColor" aria-hidden>
        <path d="M12 2a10 10 0 00-8.6 15l-1.3 4.7 4.8-1.3A10 10 0 1012 2zm5.8 14.2c-.2.7-1.4 1.3-2 1.4-.5.1-1.2.1-1.9-.1-.4-.1-1-.3-1.7-.6-3-1.3-4.9-4.3-5-4.5-.2-.2-1.2-1.6-1.2-3s.7-2.1 1-2.4c.2-.3.5-.3.7-.3h.5c.2 0 .4 0 .6.5l.8 2c.1.2.1.4 0 .5l-.3.5-.4.4c-.1.1-.3.3-.1.6.1.3.7 1.1 1.5 1.8 1 .9 1.8 1.1 2.1 1.3.2.1.4.1.5-.1l.6-.8c.2-.3.4-.2.6-.1l1.9.9c.3.1.4.2.5.3 0 .2 0 .8-.2 1.3z" />
      </svg>
    </Link>
  );
}

function StatsGrid({ stats, loading }: { stats: IngestionStats | null; loading: boolean }) {
  if (loading && !stats) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="skeleton h-[78px] rounded-2xl" />
        ))}
      </div>
    );
  }
  const cards = [
    { label: "Клиник", value: stats?.clinics, hint: stats ? `${stats.cities} городов` : "" },
    { label: "Услуг в справочнике", value: stats?.services },
    { label: "Цен в каталоге", value: stats?.prices },
    { label: "Прогонов приёма", value: stats?.runs },
    {
      label: "На ручной проверке",
      value: stats?.needs_review,
      warn: (stats?.needs_review ?? 0) > 0,
      href: "/admin/review",
    },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {cards.map((c) => {
        const inner = (
          <>
            <p className="text-xs font-medium text-ink-500">{c.label}</p>
            <p
              className={`mt-1 text-2xl font-bold tracking-tight ${
                c.warn ? "text-amber-600" : "text-ink-900"
              }`}
            >
              {c.value != null ? c.value.toLocaleString("ru-RU") : "—"}
            </p>
            {c.hint && <p className="text-xs text-ink-400">{c.hint}</p>}
            {c.href && <p className="text-xs font-medium text-brand-600">Открыть очередь →</p>}
          </>
        );
        return c.href ? (
          <Link key={c.label} href={c.href} className="card p-4 transition hover:border-brand-300">
            {inner}
          </Link>
        ) : (
          <div key={c.label} className="card p-4">
            {inner}
          </div>
        );
      })}
    </div>
  );
}

// Поиск-пикер клиники: имя/город вместо ручного UUID.
function ClinicPicker({
  value,
  onChange,
  partners,
  placeholder,
}: {
  value: string;
  onChange: (id: string) => void;
  partners: Partner[];
  placeholder?: string;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const selected = partners.find((p) => p.partner_id === value) || null;

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    const list = s
      ? partners.filter(
          (p) => p.name.toLowerCase().includes(s) || (p.city || "").toLowerCase().includes(s),
        )
      : partners;
    return list.slice(0, 40);
  }, [q, partners]);

  const display = selected ? `${selected.name}${selected.city ? ` · ${selected.city}` : ""}` : q;

  return (
    <div ref={boxRef} className="relative">
      <input
        type="text"
        value={display}
        onChange={(e) => {
          setQ(e.target.value);
          if (selected) onChange(""); // правка текста сбрасывает выбор
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder={placeholder ?? "Клиника — начните вводить название"}
        className="field w-full py-2 text-sm"
        role="combobox"
        aria-expanded={open}
        autoComplete="off"
      />
      {selected && (
        <button
          type="button"
          onClick={() => {
            onChange("");
            setQ("");
          }}
          aria-label="Сбросить"
          className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-700"
        >
          ✕
        </button>
      )}
      {open && (
        <ul className="absolute left-0 right-0 top-full z-20 mt-1 max-h-64 overflow-auto rounded-xl border border-ink-200 bg-white py-1 shadow-lg">
          {filtered.length === 0 ? (
            <li className="px-3 py-2 text-sm text-ink-400">
              {partners.length === 0 ? "Список клиник загружается…" : "Ничего не найдено"}
            </li>
          ) : (
            filtered.map((p) => (
              <li key={p.partner_id}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(p.partner_id);
                    setQ("");
                    setOpen(false);
                  }}
                  className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm text-ink-700 transition hover:bg-brand-50"
                >
                  <span className="truncate">
                    {p.name}
                    {p.city && <span className="text-ink-400"> · {p.city}</span>}
                  </span>
                  <span className="shrink-0 text-xs text-ink-300">{p.services_count}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

function ScrapeCard({ onDone, partners }: { onDone: () => void; partners: Partner[] }) {
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
        <ClinicPicker value={clinicId} onChange={setClinicId} partners={partners} />
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

function PortalIssueCard({ partners }: { partners: Partner[] }) {
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
      <div className="mt-4 space-y-3">
        <ClinicPicker value={clinicId} onChange={setClinicId} partners={partners} />
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

function BatchUploadCard({ onDone, partners }: { onDone: () => void; partners: Partner[] }) {
  const [files, setFiles] = useState<File[]>([]);
  const [clinicId, setClinicId] = useState("");
  const [archiveMode, setArchiveMode] = useState(true); // Кейс 2 (MedArchive) — по умолчанию
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BatchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function submit() {
    if (files.length === 0 || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = archiveMode
        ? await uploadArchive(files, clinicId || undefined)
        : await uploadBatch(files, clinicId || undefined);
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
        или из пикера ниже.
        {archiveMode && (
          <span className="mt-1 block text-brand-700">
            Режим MedArchive: цены резидент/нерезидент раздельно, валидации (нерезидент≥резидент,
            аномалия&nbsp;&gt;50%), <b>оригиналы сохраняются</b> для повторной обработки.
          </span>
        )}
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
        <div className="grid gap-3 sm:grid-cols-2">
          <ClinicPicker
            value={clinicId}
            onChange={setClinicId}
            partners={partners}
            placeholder="Клиника по умолчанию (опц.)"
          />
          <label className="inline-flex items-center gap-2 text-sm text-ink-600">
            <input
              type="checkbox"
              checked={archiveMode}
              onChange={(e) => {
                setArchiveMode(e.target.checked);
                setResult(null);
              }}
              className="h-4 w-4 rounded border-ink-300 text-brand-600"
            />
            Режим MedArchive (Кейс 2)
          </label>
        </div>
        <button
          type="button"
          onClick={submit}
          disabled={loading || files.length === 0}
          className="inline-flex items-center gap-2 rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-glow transition hover:bg-brand-700 disabled:opacity-50"
        >
          {loading ? "Обрабатываю…" : `Обработать (${files.length})`}
        </button>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>

      {result && <CompletionPanel result={result} />}
    </div>
  );
}

// Панель завершения приёма: статус + судьба позиций + переходы (ревью/прогон).
function CompletionPanel({ result }: { result: BatchResult }) {
  const t = result.totals;
  const auto = Math.max(0, t.items - t.needs_review);
  const okFiles = result.files.filter((f) => f.status === "ok");
  return (
    <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
      <p className="flex items-center gap-2 font-semibold text-emerald-800">
        <span>✅</span> Обработка завершена · файлов: {t.ok}/{t.files}
      </p>

      {/* Судьба позиций — отвечает на «куда делись» */}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Fate label="Всего позиций" value={t.items} />
        <Fate label="В каталоге · видны" value={auto} tone="ok" hint="авто-сопоставлено" />
        <Fate label="На проверке · скрыты" value={t.needs_review} tone="warn" hint="до подтверждения" />
        {typeof t.anomalies === "number" && (
          <Fate label="Аномалии цены" value={t.anomalies} tone={t.anomalies > 0 ? "warn" : undefined} />
        )}
      </div>
      {typeof t.stored === "number" && t.stored > 0 && (
        <p className="mt-2 text-xs text-emerald-700">💾 оригиналов сохранено: {t.stored} (доступна переобработка)</p>
      )}
      {result.truncated && (
        <p className="mt-2 text-xs text-amber-600">
          Приём обрезан по лимиту файлов — загрузите остаток отдельным архивом.
        </p>
      )}

      {/* Конечные действия по каждому прогону */}
      <div className="mt-3 space-y-2">
        {okFiles.map((f, i) => (
          <div
            key={i}
            className="flex flex-col gap-2 rounded-lg bg-white p-3 ring-1 ring-inset ring-emerald-100 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-ink-800">
                {f.stored && <span title="оригинал сохранён">💾 </span>}
                {f.file}
                {f.run_id != null && <span className="text-ink-400"> · прогон #{f.run_id}</span>}
              </p>
              <p className="text-xs text-ink-500">
                {f.items ?? 0} позиций
                {f.needs_review ? ` · ${f.needs_review} на проверку` : ""}
                {typeof f.anomalies === "number" && f.anomalies > 0 ? ` · ${f.anomalies} аном.` : ""}
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              {f.run_id != null && (f.needs_review ?? 0) > 0 && (
                <Link
                  href={`/admin/review?run=${f.run_id}`}
                  className="rounded-full bg-amber-500 px-4 py-2 text-xs font-semibold text-white transition hover:bg-amber-600"
                >
                  Проверить {f.needs_review} →
                </Link>
              )}
              {f.run_id != null && typeof f.anomalies === "number" && f.anomalies > 0 && (
                <Link
                  href={`/admin/review?run=${f.run_id}&filter=anomaly`}
                  className="rounded-full border border-red-200 px-4 py-2 text-xs font-semibold text-red-600 transition hover:bg-red-50"
                >
                  {f.anomalies} аномалий
                </Link>
              )}
              {f.run_id != null && (
                <Link
                  href={`/admin/runs/${f.run_id}`}
                  className="rounded-full border border-ink-200 px-4 py-2 text-xs font-semibold text-ink-700 transition hover:border-brand-300 hover:text-brand-700"
                >
                  Открыть прогон
                </Link>
              )}
            </div>
          </div>
        ))}
        {result.files
          .filter((f) => f.status !== "ok")
          .map((f, i) => (
            <p key={`e${i}`} className="text-xs">
              <span className="font-mono text-ink-600">{f.file}</span> —{" "}
              {f.status === "empty" ? (
                <span className="text-amber-600">пусто</span>
              ) : (
                <span className="text-red-600">{f.error}</span>
              )}
            </p>
          ))}
      </div>
    </div>
  );
}

function Fate({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: number;
  tone?: "ok" | "warn";
  hint?: string;
}) {
  const color = tone === "ok" ? "text-emerald-700" : tone === "warn" ? "text-amber-600" : "text-ink-900";
  return (
    <div className="rounded-lg bg-white p-2.5 ring-1 ring-inset ring-emerald-100">
      <p className={`text-xl font-bold tracking-tight ${color}`}>{value.toLocaleString("ru-RU")}</p>
      <p className="text-[11px] font-medium leading-tight text-ink-500">{label}</p>
      {hint && <p className="text-[10px] text-ink-400">{hint}</p>}
    </div>
  );
}

function RunsTable({ runs, loading }: { runs: IngestionRun[]; loading: boolean }) {
  const router = useRouter();
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
              {loading && runs.length === 0 ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={7} className="px-4 py-2.5">
                      <div className="skeleton h-5 w-full rounded" />
                    </td>
                  </tr>
                ))
              ) : runs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-ink-400">
                    Прогонов пока нет — загрузите архив прайсов выше.
                  </td>
                </tr>
              ) : (
                runs.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => router.push(`/admin/runs/${r.id}`)}
                    className="cursor-pointer hover:bg-ink-50/50"
                    title="Открыть прогон"
                  >
                    <td className="px-4 py-2.5 font-medium text-brand-700">#{r.id}</td>
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

function ago(ts: number): string {
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 10) return "только что";
  if (sec < 60) return `${sec} сек назад`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} мин назад`;
  return `${Math.round(min / 60)} ч назад`;
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
