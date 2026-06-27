/**
 * Расстояние между двумя точками по формуле гаверсинуса (радиус Земли 6371 км).
 * @returns расстояние в километрах
 */
export function haversineKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const toRad = (deg: number): number => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

/**
 * Форматирует расстояние для отображения: null/undefined → «—»,
 * меньше 1 км → метры, иначе километры с одним знаком после точки.
 */
export function formatDistance(km: number | null | undefined): string {
  if (km === null || km === undefined) return "—";
  if (km < 1) return `${Math.round(km * 1000)} м`;
  return `${km.toFixed(1)} км`;
}
