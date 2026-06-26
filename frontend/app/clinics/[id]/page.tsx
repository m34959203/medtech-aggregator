import Link from "next/link";
import { notFound } from "next/navigation";
import SourceBadge from "@/components/SourceBadge";
import { ApiError, getClinicProfile } from "@/lib/api";
import { formatDate, formatPrice } from "@/lib/format";
import type { ClinicProfile } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ClinicProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  // clinic_id — uuid-строка из URL (§2.2), без приведения к числу.
  const clinicId = id;
  if (!clinicId) notFound();

  let profile: ClinicProfile;
  try {
    profile = await getClinicProfile(clinicId);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6 sm:py-10">
      <Link
        href="/"
        className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-ink-500 transition hover:gap-2.5 hover:text-brand-700"
      >
        <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4" aria-hidden>
          <path
            d="M16 10H4m0 0 4-4m-4 4 4 4"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        Назад к поиску
      </Link>

      <header className="mb-8 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight text-ink-900 sm:text-3xl">
            {profile.name}
          </h1>
          {profile.rating != null && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-sm font-semibold text-amber-700 ring-1 ring-inset ring-amber-100">
              <span aria-hidden>★</span>
              {profile.rating.toFixed(1)}
            </span>
          )}
          {profile.online_booking && (
            <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-inset ring-emerald-100">
              онлайн-запись
            </span>
          )}
        </div>

        <p className="text-sm text-ink-500">
          {[profile.city, profile.address].filter(Boolean).join(" · ") ||
            "Адрес уточняйте в клинике"}
        </p>

        <dl className="grid grid-cols-1 gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
          {profile.working_hours && (
            <div className="flex items-center gap-2.5">
              <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4 shrink-0 text-ink-400" aria-hidden>
                <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.5" />
                <path d="M10 6v4l2.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <dd className="text-ink-700">{profile.working_hours}</dd>
            </div>
          )}
          {profile.phone && (
            <div className="flex items-center gap-2.5">
              <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4 shrink-0 text-ink-400" aria-hidden>
                <path
                  d="M5 3h2l1.5 4-2 1.5a9 9 0 0 0 4 4l1.5-2 4 1.5v2c0 .5-.4 1-1 1A13 13 0 0 1 4 4c0-.6.4-1 1-1Z"
                  stroke="currentColor"
                  strokeWidth="1.4"
                  strokeLinejoin="round"
                />
              </svg>
              <dd>
                <a
                  href={`tel:${profile.phone.replace(/[^\d+]/g, "")}`}
                  className="font-medium text-ink-700 transition hover:text-brand-700"
                >
                  {profile.phone}
                </a>
              </dd>
            </div>
          )}
          {profile.website && (
            <div className="flex items-center gap-2.5">
              <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4 shrink-0 text-ink-400" aria-hidden>
                <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.5" />
                <path d="M3 10h14M10 3a13 13 0 0 1 0 14M10 3a13 13 0 0 0 0 14" stroke="currentColor" strokeWidth="1.5" />
              </svg>
              <dd>
                <a
                  href={profile.website}
                  target="_blank"
                  rel="noopener noreferrer nofollow"
                  className="font-medium text-brand-700 underline-offset-2 transition hover:underline"
                >
                  Сайт клиники
                </a>
              </dd>
            </div>
          )}
        </dl>
      </header>

      <div className="mb-4 flex items-baseline justify-between gap-4">
        <h2 className="text-lg font-semibold text-ink-900">Все услуги</h2>
        <span className="text-sm text-ink-400">
          {profile.services_count} {pluralServices(profile.services_count)}
        </span>
      </div>

      {profile.services.length === 0 ? (
        <div className="card p-10 text-center text-sm text-ink-500">
          По этой клинике пока нет услуг в каталоге.
        </div>
      ) : (
        <div className="card overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-ink-50 text-left text-xs font-medium text-ink-500">
                <tr>
                  <th className="px-4 py-3">Услуга</th>
                  <th className="px-4 py-3">Цена</th>
                  <th className="px-4 py-3">Срок</th>
                  <th className="px-4 py-3">Источник</th>
                  <th className="px-4 py-3">Актуально с</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {profile.services.map((s, i) => (
                  <tr key={`${s.name}-${i}`} className={`hover:bg-ink-50/50 ${s.is_active ? "" : "opacity-50"}`}>
                    <td className="px-4 py-3 font-medium text-ink-900">{s.name}</td>
                    <td className="px-4 py-3 font-semibold text-brand-700">
                      {formatPrice(s.price, s.currency)}
                    </td>
                    <td className="px-4 py-3 text-ink-600">
                      {s.duration_days != null ? `${s.duration_days} ${pluralDays(s.duration_days)}` : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <SourceBadge source={s.source_type} />
                    </td>
                    <td className="px-4 py-3 text-ink-400">{formatDate(s.valid_from)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="mt-5 rounded-xl bg-amber-50/70 px-4 py-3 text-xs leading-relaxed text-amber-800 ring-1 ring-inset ring-amber-100">
        Данные с сайтов клиник носят справочный характер. Перед визитом уточняйте
        актуальную стоимость напрямую в клинике.
      </p>
    </div>
  );
}

function pluralServices(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "услуга";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return "услуги";
  return "услуг";
}

function pluralDays(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "день";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return "дня";
  return "дней";
}
