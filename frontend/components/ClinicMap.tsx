"use client";

import { useEffect, useRef } from "react";
import { formatPrice } from "@/lib/format";
import type { PriceOffer } from "@/lib/types";

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
        // Текст координат на клинику — по id; кнопка балуна передаёт только id,
        // чтобы в inline-onclick не попадал произвольный текст с кавычками.
        const waTexts: Record<string, string> = {};
        (window as unknown as { __medtechWaSend?: (id: string) => void }).__medtechWaSend = (
          id: string,
        ) => {
          const el = document.getElementById(`wa-in-${id}`) as HTMLInputElement | null;
          const digits = (el?.value || "").replace(/[^0-9]/g, "");
          if (digits.length < 10) {
            // eslint-disable-next-line no-alert
            alert("Введите номер с кодом страны, например +7 700 123 45 67");
            el?.focus();
            return;
          }
          window.open(`https://wa.me/${digits}?text=${waTexts[id] || ""}`, "_blank", "noopener");
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
          waTexts[p.clinic_id] = waText;
          // Форма WhatsApp: поле номера + кнопка → wa.me/<номер> с адресом и маршрутом.
          const waForm =
            `<div style="margin-top:10px">` +
            `<div style="font-size:12px;color:#64748b;margin-bottom:5px">📍 Отправить координаты в WhatsApp:</div>` +
            `<div style="display:flex;gap:6px;align-items:stretch">` +
            `<input id="wa-in-${p.clinic_id}" type="tel" inputmode="tel" autocomplete="tel"` +
            ` placeholder="+7 700 000 00 00"` +
            ` style="flex:1;min-width:0;width:100%;padding:7px 9px;border:1px solid #d1d5db;` +
            `border-radius:8px;font-size:13px;outline:none" />` +
            `<button type="button"` +
            ` onclick="window.__medtechWaSend&&window.__medtechWaSend('${p.clinic_id}')"` +
            ` style="flex:none;display:inline-flex;align-items:center;gap:5px;padding:7px 13px;` +
            `background:#25D366;color:#fff;border:none;border-radius:8px;font-weight:600;` +
            `font-size:13px;line-height:1;cursor:pointer">Отправить</button>` +
            `</div></div>`;
          const body = [
            `<b style="color:#0f766e">${formatPrice(p.price, p.currency)}</b>`,
            isCheapest ? " · 🏆 Лучшая цена" : "",
            `<br><span style="color:#64748b">${addr}</span>`,
            p.phone ? `<br><a href="tel:${p.phone.replace(/[^\d+]/g, "")}">${p.phone}</a>` : "",
            waForm,
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

  return <div ref={containerRef} className="h-full min-h-[320px] w-full rounded-xl" />;
}
