// «Чекпоинт» местоположения пользователя: сохраняется в localStorage и
// используется на страницах с поиском (главная/выдача) для учёта расстояния.
// Один источник правды на всё приложение — поставил один раз, работает везде.

export interface SavedGeo {
  lat: number;
  lng: number;
  label?: string; // человекочитаемая метка (если задавали вручную)
  savedAt?: number;
}

const KEY = "medtech_geo";

/** Прочитать сохранённую геопозицию (или null). Безопасно на сервере/без localStorage. */
export function loadGeo(): SavedGeo | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const g = JSON.parse(raw) as SavedGeo;
    if (typeof g?.lat === "number" && typeof g?.lng === "number") return g;
  } catch {
    /* битый json — игнорируем */
  }
  return null;
}

/** Сохранить геопозицию-«чекпоинт». */
export function saveGeo(g: SavedGeo): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify({ ...g, savedAt: Date.now() }));
  } catch {
    /* квота/приватный режим — не критично */
  }
}

/** Сбросить «чекпоинт». */
export function clearGeo(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* no-op */
  }
}

/** Запросить геопозицию у браузера (Promise-обёртка над geolocation API). */
export function requestBrowserGeo(): Promise<{ lat: number; lng: number }> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      reject(new Error("geolocation unavailable"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      (err) => reject(err),
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300_000 },
    );
  });
}
