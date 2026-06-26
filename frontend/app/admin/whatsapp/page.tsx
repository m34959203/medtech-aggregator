"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  waConnect,
  waDisconnect,
  waLimits,
  waLogout,
  waStatus,
  type WaLimits,
  type WaStatus,
} from "@/lib/api";

const LABELS: Record<WaStatus["status"], string> = {
  disconnected: "Не подключено",
  connecting: "Подключение…",
  qr_ready: "Ожидает сканирования QR",
  connected: "Подключено",
};

const DOT: Record<WaStatus["status"], string> = {
  disconnected: "bg-ink-300",
  connecting: "bg-amber-400 animate-pulse",
  qr_ready: "bg-amber-400 animate-pulse",
  connected: "bg-emerald-500",
};

export default function WhatsAppAdminPage() {
  const [status, setStatus] = useState<WaStatus | null>(null);
  const [limits, setLimits] = useState<WaLimits | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await waStatus();
      setStatus(s);
      setError(null);
      // лимиты тянем, когда туннель подключён (иначе 400 от шлюза не нужен)
      if (s.status === "connected") {
        waLimits().then(setLimits).catch(() => {});
      }
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.status === 503
            ? "WhatsApp-туннель не настроен на сервере (WA_GATEWAY_URL/WA_API_SECRET)."
            : `Ошибка: ${e.message}`
          : "Бэкенд недоступен.",
      );
    }
  }, []);

  // Поллинг статуса: ловим появление QR и переход в connected.
  useEffect(() => {
    refresh();
    timer.current = setInterval(refresh, 2500);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [refresh]);

  const connect = async () => {
    setBusy(true);
    try {
      await waConnect();
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Не удалось запустить подключение.");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      await waDisconnect();
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    if (!confirm("Выйти из WhatsApp и стереть сессию? Потребуется новая привязка по QR.")) return;
    setBusy(true);
    try {
      await waLogout();
      setLimits(null);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const st = status?.status ?? "disconnected";

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <header className="mb-8">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200">
          WhatsApp-туннель
        </span>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-ink-900">
          Привязка WhatsApp
        </h1>
        <p className="mt-2 max-w-xl text-ink-600">
          Подключите номер WhatsApp как связанное устройство — платформа сможет
          отправлять и принимать сообщения через туннель.
        </p>
      </header>

      {error && (
        <div className="mb-6 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-inset ring-red-100">
          {error}
        </div>
      )}

      <div className="card p-6">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <span className={`h-2.5 w-2.5 rounded-full ${DOT[st]}`} />
            <span className="font-medium text-ink-900">{LABELS[st]}</span>
            {status?.phoneNumber && (
              <span className="text-sm text-ink-500">· +{status.phoneNumber}</span>
            )}
          </div>
          <div className="flex gap-2">
            {st === "connected" ? (
              <>
                <button
                  onClick={disconnect}
                  disabled={busy}
                  className="rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm font-medium text-ink-700 transition hover:bg-ink-50 disabled:opacity-50"
                >
                  Отключить
                </button>
                <button onClick={logout} disabled={busy} className="text-sm font-medium text-red-600 hover:underline disabled:opacity-50">
                  Выйти и стереть
                </button>
              </>
            ) : (
              <button onClick={connect} disabled={busy || st === "connecting" || st === "qr_ready"} className="btn-primary text-sm">
                {busy ? "…" : "Подключить"}
              </button>
            )}
          </div>
        </div>

        {/* QR для сканирования */}
        {st === "qr_ready" && status?.qrCode && (
          <div className="mt-6 flex flex-col items-center gap-4 border-t border-ink-100 pt-6">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={status.qrCode}
              alt="QR для привязки WhatsApp"
              width={264}
              height={264}
              className="rounded-xl ring-1 ring-ink-100"
            />
            <ol className="max-w-sm list-decimal space-y-1 pl-5 text-sm text-ink-600">
              <li>Откройте WhatsApp на телефоне.</li>
              <li>Настройки → <b>Связанные устройства</b> → «Привязка устройства».</li>
              <li>Наведите камеру на QR. Код обновляется автоматически.</li>
            </ol>
          </div>
        )}

        {st === "connecting" && (
          <p className="mt-6 border-t border-ink-100 pt-6 text-sm text-ink-500">
            Генерируется QR-код… подождите несколько секунд.
          </p>
        )}
      </div>

      {/* Анти-бан / лимиты */}
      {limits && (
        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Лимит/сутки" value={String(limits.dailyLimit)} />
          <Stat label="Отправлено 24ч" value={String(limits.sentLast24h)} />
          <Stat label="Осталось" value={String(limits.remaining)} />
          <Stat label="В очереди" value={String(limits.queueDepth)} />
        </div>
      )}
      {st === "connected" && (
        <p className="mt-4 text-xs text-ink-400">
          Антибан: имитация набора {limits?.humanize ? "вкл" : "выкл"} · отправка только тем,
          кто написал первым: {limits?.requireClientInitiated ? "вкл" : "выкл"}.
        </p>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="card px-4 py-3">
      <div className="text-xs text-ink-400">{label}</div>
      <div className="mt-0.5 text-xl font-semibold text-ink-900">{value}</div>
    </div>
  );
}
