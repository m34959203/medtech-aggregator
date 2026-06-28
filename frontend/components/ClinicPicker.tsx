"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Partner } from "@/lib/api";

// Поиск-пикер клиники: имя/город вместо ручного UUID. Общий для админ-карточек.
export default function ClinicPicker({
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
          if (selected) onChange("");
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
