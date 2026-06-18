"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  confirmAllPortal,
  editPortalPrice,
  getPortal,
  uploadPortalPricelist,
} from "@/lib/api";
import { formatPrice } from "@/lib/format";
import type { PortalPrice, PortalView } from "@/lib/types";

export default function ClinicPortalPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;
  const [data, setData] = useState<PortalView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setData(await getPortal(token));
      setError(null);
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 404
          ? "Доступ не найден. Проверьте ссылку из письма."
          : "Не удалось загрузить данные.",
      );
    }
  }, [token]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-20 text-center">
        <p className="text-lg font-medium text-ink-700">{error}</p>
      </div>
    );
  }
  if (!data) {
    return <div className="mx-auto max-w-3xl px-4 py-20 text-center text-ink-400">Загрузка…</div>;
  }

  const total = data.prices.length;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      <header className="mb-6">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-200">
          Кабинет клиники
        </span>
        <h1 className="mt-3 text-2xl font-bold tracking-tight text-ink-900 sm:text-3xl">
          {data.clinic.name}
        </h1>
        <p className="mt-1 text-sm text-ink-500">
          {[data.clinic.city, data.clinic.address].filter(Boolean).join(" · ")}
        </p>
        <p className="mt-3 max-w-xl text-sm text-ink-600">
          Мы собрали цены вашей клиники из открытых источников. Проверьте их,
          поправьте при необходимости и подтвердите — подтверждённые цены
          помечаются как официальные и не перезаписываются автосбором.
        </p>
      </header>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <span className="text-sm text-ink-500">
          Подтверждено <b className="text-ink-800">{data.confirmed_count}</b> из {total}
        </span>
        <button
          type="button"
          disabled={busy || data.confirmed_count === total}
          onClick={async () => {
            setBusy(true);
            try {
              await confirmAllPortal(token);
              await refresh();
            } finally {
              setBusy(false);
            }
          }}
          className="rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
        >
          Подтвердить все цены
        </button>
        <UploadOwn token={token} onDone={refresh} />
      </div>

      <div className="card overflow-hidden p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-ink-50 text-left text-xs font-medium text-ink-500">
              <tr>
                <th className="px-4 py-2.5">Услуга</th>
                <th className="px-4 py-2.5">В прайсе</th>
                <th className="px-4 py-2.5">Цена</th>
                <th className="px-4 py-2.5">Статус</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {data.prices.map((p) => (
                <PriceRow key={p.price_id} token={token} price={p} onDone={refresh} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function PriceRow({ token, price, onDone }: { token: string; price: PortalPrice; onDone: () => void }) {
  const [value, setValue] = useState(String(price.price));
  const [saving, setSaving] = useState(false);
  const changed = Number(value) !== price.price && Number(value) > 0;

  return (
    <tr className="hover:bg-ink-50/50">
      <td className="px-4 py-2.5 font-medium text-ink-900">{price.service}</td>
      <td className="px-4 py-2.5 text-xs text-ink-400">«{price.raw_name}»</td>
      <td className="px-4 py-2.5">
        <div className="flex items-center gap-2">
          <input
            value={value}
            onChange={(e) => setValue(e.target.value.replace(/[^\d]/g, ""))}
            inputMode="numeric"
            className="field w-24 py-1.5 text-sm"
          />
          <span className="text-xs text-ink-400">{price.currency}</span>
          {changed && (
            <button
              type="button"
              disabled={saving}
              onClick={async () => {
                setSaving(true);
                try {
                  await editPortalPrice(token, price.price_id, Number(value));
                  await onDone();
                } finally {
                  setSaving(false);
                }
              }}
              className="rounded-lg bg-brand-600 px-2.5 py-1 text-xs font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50"
            >
              {saving ? "…" : "Сохранить"}
            </button>
          )}
        </div>
      </td>
      <td className="px-4 py-2.5">
        {price.confirmed ? (
          <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
            ✓ подтверждено
          </span>
        ) : (
          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
            из автосбора
          </span>
        )}
      </td>
    </tr>
  );
}

function UploadOwn({ token, onDone }: { token: string; onDone: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,.xls,.csv,.pdf"
        className="hidden"
        onChange={async (e) => {
          const f = e.target.files?.[0];
          if (!f) return;
          setBusy(true);
          try {
            await uploadPortalPricelist(token, f);
            await onDone();
          } finally {
            setBusy(false);
            if (inputRef.current) inputRef.current.value = "";
          }
        }}
      />
      <button
        type="button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        className="rounded-full border border-ink-200 px-4 py-2 text-sm font-medium text-ink-700 transition hover:border-brand-300 hover:text-brand-700 disabled:opacity-50"
      >
        {busy ? "Загрузка…" : "Загрузить свой прайс"}
      </button>
    </>
  );
}
