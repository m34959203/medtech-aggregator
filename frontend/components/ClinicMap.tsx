"use client";

import { useEffect, useRef, useState } from "react";
import { formatPrice } from "@/lib/format";
import type { PriceOffer } from "@/lib/types";

// Данные для модалки «отправить координаты в WhatsApp».
interface WaShareData {
  clinicName: string;
  address: string;
  lat: number;
  lng: number;
  text: string; // готовый encodeURIComponent-текст для wa.me
}

// Ключ вшивается в бандл на build (NEXT_PUBLIC_*). Без ключа карта не грузится —
// показываем понятный плейсхолдер вместо битого виджета.
const API_KEY = process.env.NEXT_PUBLIC_YANDEX_MAPS_API_KEY || "";

// Скрипт Яндекс.Карт грузим один раз на всё приложение.
let ymapsPromise: Promise<unknown> | null = null;
function loadYmaps(): Promise<any> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  const w = window as unknown as { ymaps?: any };
  if (w.ymaps?.Map) return Promise.resolve(w.ymaps);
  if (!ymapsPromise) {
    ymapsPromise = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = `https://api-maps.yandex.ru/2.1/?apikey=${API_KEY}&lang=ru_RU`;
      s.async = true;
      s.onload = () => w.ymaps.ready(() => resolve(w.ymaps));
      s.onerror = () => reject(new Error("yandex maps failed to load"));
      document.head.appendChild(s);
    });
  }
  return ymapsPromise as Promise<any>;
}

interface Props {
  offers: PriceOffer[];
  cheapestClinicId?: string; // uuid клиники (§2.2)
  // Клиника, выбранная в списке карточек: на неё центрируемся и открываем балун.
  activeClinicId?: string; // uuid клиники (§2.2)
  // Обратная связь: клик по метке выделяет карточку в списке.
  onSelectClinic?: (clinicId: string) => void;
}

export default function ClinicMap({
  offers,
  cheapestClinicId,
  activeClinicId,
  onSelectClinic,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  // Модалка «отправить координаты в WhatsApp» (React, вместо inline-формы в балуне).
  const [waModal, setWaModal] = useState<WaShareData | null>(null);
  const waDataRef = useRef<Record<string, WaShareData>>({});
  const mapRef = useRef<any>(null);
  // clinic_id -> placemark, чтобы открывать балун без пересборки карты.
  const placemarksRef = useRef<Map<string, any>>(new Map());
  // Держим актуальный колбэк, не пересобирая карту при его изменении.
  const onSelectRef = useRef(onSelectClinic);
  onSelectRef.current = onSelectClinic;

  const points = offers.filter(
    (o): o is PriceOffer & { lat: number; lng: number } =>
      o.lat != null && o.lng != null,
  );

  // Сборка карты и меток — зависит только от данных.
  useEffect(() => {
    if (!API_KEY || points.length === 0) return;
    let cancelled = false;
    placemarksRef.current = new Map();

    loadYmaps()
      .then((ymaps) => {
        if (cancelled || !containerRef.current) return;
        const map = new ymaps.Map(
          containerRef.current,
          {
            center: [points[0].lat, points[0].lng],
            zoom: 12,
            controls: ["zoomControl", "geolocationControl"],
          },
          { suppressMapOpenBlock: true },
        );
        mapRef.current = map;

        const coords: number[][] = [];
        // Мост из балуна (Yandex HTML, вне React) в React-стейт: кнопка передаёт
        // только id, бридж открывает модалку с данными клиники.
        waDataRef.current = {};
        (window as unknown as { __medtechWaOpen?: (id: string) => void }).__medtechWaOpen = (
          id: string,
        ) => {
          const d = waDataRef.current[id];
          if (d) setWaModal(d);
        };
        for (const p of points) {
          const isCheapest = p.clinic_id === cheapestClinicId;
          const addr = p.address || p.district || "";
          // Маршрут до точки для навигатора (от текущего местоположения).
          const routeUrl = `https://yandex.ru/maps/?rtext=~${p.lat},${p.lng}&rtt=auto`;
          // Точка на карте по координатам (открывается в любом навигаторе).
          const pinUrl = `https://yandex.ru/maps/?pt=${p.lng},${p.lat}&z=17`;
          // Текст для WhatsApp: название, адрес, координаты, точка на карте и маршрут.
          const waText = encodeURIComponent(
            [
              p.clinic_name,
              addr || null,
              `Координаты: ${p.lat.toFixed(6)}, ${p.lng.toFixed(6)}`,
              `На карте: ${pinUrl}`,
              `Маршрут: ${routeUrl}`,
            ]
              .filter((s) => s != null && s !== "")
              .join("\n"),
          );
          waDataRef.current[p.clinic_id] = {
            clinicName: p.clinic_name,
            address: addr,
            lat: p.lat,
            lng: p.lng,
            text: waText,
          };
          // Кнопка в балуне просто открывает React-модалку (через бридж по id).
          const waBtn =
            `<button type="button"` +
            ` onclick="window.__medtechWaOpen&&window.__medtechWaOpen('${p.clinic_id}')"` +
            ` style="display:inline-flex;align-items:center;gap:6px;margin-top:10px;` +
            `padding:7px 12px;background:#25D366;color:#fff;border:none;border-radius:8px;` +
            `font-weight:600;font-size:13px;line-height:1;cursor:pointer">` +
            `📍 Отправить в WhatsApp</button>`;
          const body = [
            `<b style="color:#0f766e">${formatPrice(p.price, p.currency)}</b>`,
            isCheapest ? " · 🏆 Лучшая цена" : "",
            `<br><span style="color:#64748b">${addr}</span>`,
            p.phone ? `<br><a href="tel:${p.phone.replace(/[^\d+]/g, "")}">${p.phone}</a>` : "",
            waBtn,
          ].join("");
          const placemark = new ymaps.Placemark(
            [p.lat, p.lng],
            {
              balloonContentHeader: p.clinic_name,
              balloonContentBody: body,
              iconCaption: formatPrice(p.price, p.currency),
            },
            {
              preset: isCheapest
                ? "islands#greenStretchyIcon"
                : "islands#grayStretchyIcon",
              iconColor: isCheapest ? "#059473" : "#64748b",
            },
          );
          // Клик по метке выделяет соответствующую карточку в списке.
          placemark.events.add("click", () => onSelectRef.current?.(p.clinic_id));
          map.geoObjects.add(placemark);
          // Первая метка для клиники — её и открываем при выборе карточки.
          if (!placemarksRef.current.has(p.clinic_id)) {
            placemarksRef.current.set(p.clinic_id, placemark);
          }
          coords.push([p.lat, p.lng]);
        }

        if (coords.length > 1) {
          map.setBounds(map.geoObjects.getBounds(), {
            checkZoomRange: true,
            zoomMargin: 40,
          });
        } else {
          map.setCenter(coords[0], 14);
        }
      })
      .catch(() => {
        /* сеть/ключ недоступны — плейсхолдер ниже остаётся */
      });

    return () => {
      cancelled = true;
      if (mapRef.current) {
        mapRef.current.destroy();
        mapRef.current = null;
      }
      placemarksRef.current = new Map();
    };
  }, [offers, cheapestClinicId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Реакция на выбор карточки: плавно центрируемся и открываем балун клиники.
  useEffect(() => {
    if (activeClinicId == null) return;
    const map = mapRef.current;
    const placemark = placemarksRef.current.get(activeClinicId);
    if (!map || !placemark) return;
    const coords = placemark.geometry.getCoordinates();
    map.panTo(coords, { flying: true, duration: 350 });
    placemark.balloon.open();
  }, [activeClinicId]);

  if (!API_KEY) {
    return (
      <div className="flex h-full min-h-[320px] items-center justify-center rounded-2xl border border-dashed border-ink-200 bg-ink-50 px-6 text-center text-sm text-ink-400">
        Карта временно недоступна (не задан ключ Яндекс.Карт)
      </div>
    );
  }
  if (points.length === 0) {
    return (
      <div className="flex h-full min-h-[320px] items-center justify-center rounded-2xl border border-dashed border-ink-200 bg-ink-50 text-sm text-ink-400">
        Координаты клиник недоступны для отображения на карте
      </div>
    );
  }

  return (
    <>
      <div ref={containerRef} className="h-full min-h-[320px] w-full rounded-xl" />
      {waModal && <WaShareModal data={waModal} onClose={() => setWaModal(null)} />}
    </>
  );
}

// Модалка ввода номера → отправка координат клиники в WhatsApp на этот номер.
function WaShareModal({ data, onClose }: { data: WaShareData; onClose: () => void }) {
  const [phone, setPhone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  function send() {
    const digits = phone.replace(/[^0-9]/g, "");
    if (digits.length < 10) {
      setError("Введите номер с кодом страны, например +7 700 123 45 67");
      return;
    }
    window.open(`https://wa.me/${digits}?text=${data.text}`, "_blank", "noopener");
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 p-4 animate-fade-up"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-card-hover"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-base font-semibold text-ink-900">
            Отправить координаты в WhatsApp
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="-mr-1 -mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-ink-400 transition hover:bg-ink-50 hover:text-ink-700"
          >
            <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" aria-hidden>
              <path d="M6 6l8 8M14 6l-8 8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="mt-2 rounded-xl bg-ink-50 px-3 py-2 text-sm">
          <p className="font-medium text-ink-800">{data.clinicName}</p>
          {data.address && <p className="text-ink-500">{data.address}</p>}
          <p className="mt-1 font-mono text-xs text-ink-400">
            {data.lat.toFixed(6)}, {data.lng.toFixed(6)}
          </p>
        </div>

        <label className="mt-4 block text-sm font-medium text-ink-700">
          Номер получателя
        </label>
        <input
          ref={inputRef}
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          value={phone}
          onChange={(e) => {
            setPhone(e.target.value);
            setError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") send();
          }}
          placeholder="+7 700 000 00 00"
          className="mt-1 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm text-ink-800 outline-none transition focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
        />
        {error && <p className="mt-1.5 text-xs text-red-600">{error}</p>}

        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-full border border-ink-200 px-4 py-2.5 text-sm font-medium text-ink-600 transition hover:bg-ink-50"
          >
            Отмена
          </button>
          <button
            type="button"
            onClick={send}
            className="flex flex-[1.4] items-center justify-center gap-2 rounded-full bg-[#25D366] px-4 py-2.5 text-sm font-semibold text-white transition hover:brightness-95"
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden>
              <path d="M12 2a10 10 0 00-8.6 15l-1.3 4.7 4.8-1.3A10 10 0 1012 2zm5.8 14.2c-.2.7-1.4 1.3-2 1.4-.5.1-1.2.1-1.9-.1-.4-.1-1-.3-1.7-.6-3-1.3-4.9-4.3-5-4.5-.2-.2-1.2-1.6-1.2-3s.7-2.1 1-2.4c.2-.3.5-.3.7-.3h.5c.2 0 .4 0 .6.5l.8 2c.1.2.1.4 0 .5l-.3.5-.4.4c-.1.1-.3.3-.1.6.1.3.7 1.1 1.5 1.8 1 .9 1.8 1.1 2.1 1.3.2.1.4.1.5-.1l.6-.8c.2-.3.4-.2.6-.1l1.9.9c.3.1.4.2.5.3 0 .2 0 .8-.2 1.3z" />
            </svg>
            Отправить
          </button>
        </div>
      </div>
    </div>
  );
}
