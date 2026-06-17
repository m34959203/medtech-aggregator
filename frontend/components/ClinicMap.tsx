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
  cheapestClinicId?: number;
}

export default function ClinicMap({ offers, cheapestClinicId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const points = offers.filter(
    (o): o is PriceOffer & { lat: number; lng: number } =>
      o.lat != null && o.lng != null,
  );

  useEffect(() => {
    if (!API_KEY || points.length === 0) return;
    let map: any;
    let cancelled = false;

    loadYmaps()
      .then((ymaps) => {
        if (cancelled || !containerRef.current) return;
        map = new ymaps.Map(
          containerRef.current,
          {
            center: [points[0].lat, points[0].lng],
            zoom: 12,
            controls: ["zoomControl", "geolocationControl"],
          },
          { suppressMapOpenBlock: true },
        );

        const coords: number[][] = [];
        for (const p of points) {
          const isCheapest = p.clinic_id === cheapestClinicId;
          const body = [
            `<b style="color:#0f766e">${formatPrice(p.price, p.currency)}</b>`,
            isCheapest ? " · 🏆 Лучшая цена" : "",
            `<br><span style="color:#64748b">${p.address || p.district || ""}</span>`,
            p.phone ? `<br><a href="tel:${p.phone.replace(/[^\d+]/g, "")}">${p.phone}</a>` : "",
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
          map.geoObjects.add(placemark);
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
      if (map) map.destroy();
    };
  }, [offers, cheapestClinicId]); // eslint-disable-line react-hooks/exhaustive-deps

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
