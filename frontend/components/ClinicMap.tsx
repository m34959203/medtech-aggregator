"use client";

import { useEffect, useMemo } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { formatPrice } from "@/lib/format";
import type { PriceOffer } from "@/lib/types";

// Маркер для самой дешёвой клиники (брендовый цвет) и для остальных.
function pinIcon(color: string, ring: string) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
      <path d="M17 0C7.6 0 0 7.6 0 17c0 12 17 27 17 27s17-15 17-27C34 7.6 26.4 0 17 0z" fill="${color}"/>
      <circle cx="17" cy="17" r="7" fill="#ffffff"/>
      <circle cx="17" cy="17" r="4" fill="${ring}"/>
    </svg>`;
  return L.divIcon({
    html: svg,
    className: "",
    iconSize: [34, 44],
    iconAnchor: [17, 44],
    popupAnchor: [0, -40],
  });
}

const cheapIcon = pinIcon("#059473", "#022c25");
const normalIcon = pinIcon("#94a3b8", "#334155");

interface Props {
  offers: PriceOffer[];
  cheapestClinicId?: number;
}

export default function ClinicMap({ offers, cheapestClinicId }: Props) {
  const points = useMemo(
    () =>
      offers.filter(
        (o): o is PriceOffer & { lat: number; lng: number } =>
          o.lat != null && o.lng != null,
      ),
    [offers],
  );

  if (points.length === 0) {
    return (
      <div className="flex h-full min-h-[320px] items-center justify-center rounded-2xl border border-dashed border-ink-200 bg-ink-50 text-sm text-ink-400">
        Координаты клиник недоступны для отображения на карте
      </div>
    );
  }

  const center: [number, number] = [
    points.reduce((s, p) => s + p.lat, 0) / points.length,
    points.reduce((s, p) => s + p.lng, 0) / points.length,
  ];

  return (
    <MapContainer
      center={center}
      zoom={12}
      scrollWheelZoom={false}
      className="h-full min-h-[320px] w-full"
      style={{ minHeight: 320 }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds points={points.map((p) => [p.lat, p.lng] as [number, number])} />
      {points.map((p, i) => {
        const isCheapest = p.clinic_id === cheapestClinicId;
        return (
          <Marker
            key={`${p.clinic_id}-${i}`}
            position={[p.lat, p.lng]}
            icon={isCheapest ? cheapIcon : normalIcon}
          >
            <Popup>
              <div className="space-y-1">
                <p className="font-semibold text-ink-900">{p.clinic_name}</p>
                <p className="text-xs text-ink-500">{p.district}</p>
                <p className="text-base font-bold text-brand-700">
                  {formatPrice(p.price, p.currency)}
                </p>
                {isCheapest && (
                  <p className="text-xs font-medium text-brand-600">
                    🏆 Лучшая цена
                  </p>
                )}
              </div>
            </Popup>
          </Marker>
        );
      })}
    </MapContainer>
  );
}

/** Подгоняет вьюпорт под все маркеры. */
function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 13);
      return;
    }
    map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 14 });
  }, [map, points]);
  return null;
}
