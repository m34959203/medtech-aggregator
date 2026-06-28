"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  createSource,
  deleteSource,
  getPartners,
  getSources,
  patchSource,
  runScheduled,
  scrapeSite,
} from "@/lib/api";
import type { Partner } from "@/lib/api";
import type { IngestSource } from "@/lib/types";
import ClinicPicker from "@/components/ClinicPicker";

export default function SourcesPage() {
  const [sources, setSources] = useState<IngestSource[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setSources(await getSources());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? `Ошибка: ${e.message}` : "Бэкенд недоступен.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    getPartners().then(setPartners).catch(() => setPartners([]));
  }, [refresh]);

  const lastRun = sources
    .map((s) => s.last_run_at)
    .filter(Boolean)
    .sort()
    .at(-1);
  const enabledCount = sources.filter((s) => s.enabled).length;

  async function runNow() {
    setMsg(null);
    try {
      await runScheduled();
      setMsg("Плановый сбор запущен в фоне — прогоны появятся в журнале.");
    } catch (e) {
      setError(e instanceof ApiError ? `Ошибка: ${e.message}` : "Не удалось запустить.");
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
      <Link href="/admin" className="text-sm font-medium text-brand-700 hover:underline">
        ← Дашборд приёма
      </Link>
      <header className="mt-4 mb-6">
        <h1 className="text-3xl font-bold tracking-tight text-ink-900">Источники автосбора</h1>
        <p className="mt-2 text-ink-600">
          Список сайтов для парсинга. Включённые источники собираются по расписанию и
          кнопкой «Запустить сейчас».
        </p>
      </header>

      {/* Расписание */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-brand-50 px-4 py-3 ring-1 ring-inset ring-brand-100">
        <div className="text-sm text-brand-900">
          <p className="font-medium">⏱ Автосбор по расписанию: каждые 6 часов (cron)</p>
          <p className="text-xs text-brand-700">
            Включено источников: {enabledCount} из {sources.length}
            {lastRun && <> · последний прогон источника: {formatTime(lastRun)}</>}
          </p>
        </div>
        <button
          type="button"
          onClick={runNow}
          className="rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700"
        >
          Запустить сейчас
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-inset ring-red-100">
          {error}
        </div>
      )}
      {msg && (
        <div className="mb-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700 ring-1 ring-inset ring-emerald-100">
          {msg}
        </div>
      )}

      <AddSourceForm partners={partners} onAdded={refresh} onError={setError} />

      <h2 className="mb-3 mt-8 text-base font-semibold text-ink-900">
        Источники <span className="text-ink-400">({sources.length})</span>
      </h2>
      {loading ? (
        <div className="skeleton h-40 w-full rounded-2xl" />
      ) : sources.length === 0 ? (
        <div className="card p-10 text-center text-sm text-ink-500">
          Источников нет — добавьте сайт клиники выше.
        </div>
      ) : (
        <div className="card overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-ink-50 text-left text-xs font-medium text-ink-500">
                <tr>
                  <th className="px-4 py-2.5">Сбор</th>
                  <th className="px-4 py-2.5">Клиника</th>
                  <th className="px-4 py-2.5">Тип</th>
                  <th className="px-4 py-2.5">URL</th>
                  <th className="px-4 py-2.5">Прогонов</th>
                  <th className="px-4 py-2.5">Последний</th>
                  <th className="px-4 py-2.5"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {sources.map((s) => (
                  <SourceRow key={s.id} src={s} onChanged={refresh} onError={setError} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function SourceRow({
  src,
  onChanged,
  onError,
}: {
  src: IngestSource;
  onChanged: () => void;
  onError: (m: string) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function toggle() {
    setBusy(true);
    try {
      await patchSource(src.id, { enabled: !src.enabled });
      onChanged();
    } catch (e) {
      onError(e instanceof ApiError ? `Ошибка: ${e.message}` : "Не удалось обновить.");
    } finally {
      setBusy(false);
    }
  }

  async function scrapeNow() {
    setBusy(true);
    try {
      const r = await scrapeSite(src.clinic_id, src.url_or_endpoint, false);
      onError("");
      alert(`Снято: ${r.items_found} · сопоставлено: ${r.matched} · на проверку: ${r.needs_review}`);
      onChanged();
    } catch (e) {
      onError(e instanceof ApiError ? `Ошибка: ${e.message}` : "Сбор не удался.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Удалить источник «${src.url_or_endpoint}»? История прогонов сохранится.`)) {
      return;
    }
    setBusy(true);
    try {
      await deleteSource(src.id);
      onChanged();
    } catch (e) {
      onError(e instanceof ApiError ? `Ошибка: ${e.message}` : "Не удалось удалить.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr className={`hover:bg-ink-50/50 ${src.enabled ? "" : "opacity-55"}`}>
      <td className="px-4 py-2.5">
        <button
          type="button"
          onClick={toggle}
          disabled={busy}
          role="switch"
          aria-checked={src.enabled}
          title={src.enabled ? "Выключить из автосбора" : "Включить в автосбор"}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition ${
            src.enabled ? "bg-brand-600" : "bg-ink-300"
          } disabled:opacity-50`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${
              src.enabled ? "translate-x-4" : "translate-x-0.5"
            }`}
          />
        </button>
      </td>
      <td className="px-4 py-2.5 font-medium text-ink-800">{src.clinic_name ?? "—"}</td>
      <td className="px-4 py-2.5">
        <span className="rounded-full bg-ink-100 px-2 py-0.5 text-xs text-ink-600">{src.type}</span>
      </td>
      <td className="max-w-[18rem] truncate px-4 py-2.5 text-ink-500" title={src.url_or_endpoint}>
        <a href={src.url_or_endpoint} target="_blank" rel="noopener noreferrer" className="hover:text-brand-700 hover:underline">
          {src.url_or_endpoint}
        </a>
      </td>
      <td className="px-4 py-2.5 text-ink-600">{src.runs}</td>
      <td className="whitespace-nowrap px-4 py-2.5 text-xs text-ink-400">
        {src.last_run_at ? formatTime(src.last_run_at) : "—"}
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 text-right">
        <button
          type="button"
          onClick={scrapeNow}
          disabled={busy}
          className="mr-2 text-xs font-medium text-brand-700 hover:underline disabled:opacity-50"
        >
          снять сейчас
        </button>
        <button
          type="button"
          onClick={remove}
          disabled={busy}
          className="text-xs font-medium text-red-600 hover:underline disabled:opacity-50"
        >
          удалить
        </button>
      </td>
    </tr>
  );
}

function AddSourceForm({
  partners,
  onAdded,
  onError,
}: {
  partners: Partner[];
  onAdded: () => void;
  onError: (m: string) => void;
}) {
  const [clinicId, setClinicId] = useState("");
  const [url, setUrl] = useState("");
  const [type, setType] = useState("web_scrape");
  const [busy, setBusy] = useState(false);

  async function add() {
    if (!clinicId || !url.trim() || busy) return;
    setBusy(true);
    try {
      await createSource({ clinic_id: clinicId, type, url: url.trim() });
      setUrl("");
      setClinicId("");
      onError("");
      onAdded();
    } catch (e) {
      onError(e instanceof ApiError ? `Ошибка: ${e.message}` : "Не удалось добавить.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card p-5">
      <h2 className="text-base font-semibold text-ink-900">Добавить сайт для парсинга</h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-12 sm:items-center">
        <div className="sm:col-span-4">
          <ClinicPicker value={clinicId} onChange={setClinicId} partners={partners} />
        </div>
        <div className="sm:col-span-2">
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="field w-full py-2 text-sm"
            aria-label="Тип источника"
          >
            <option value="web_scrape">веб-парсинг</option>
            <option value="api">API</option>
          </select>
        </div>
        <div className="sm:col-span-4">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://клиника.kz/prices"
            className="field w-full py-2 text-sm"
          />
        </div>
        <div className="sm:col-span-2">
          <button
            type="button"
            onClick={add}
            disabled={!clinicId || !url.trim() || busy}
            className="w-full rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
          >
            {busy ? "Добавляю…" : "Добавить"}
          </button>
        </div>
      </div>
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
