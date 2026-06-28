import { cookies } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import ComparisonView from "@/components/ComparisonView";
import { ApiError, compare, getCities } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ServicePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ city?: string; clinic?: string }>;
}) {
  const { id } = await params;
  const { city = "", clinic = "" } = await searchParams;
  // service_id — uuid-строка из URL (§2.2), без приведения к числу.
  const serviceId = id;
  if (!serviceId) notFound();

  const locale = (await cookies()).get("locale")?.value === "kk" ? "kk" : "ru";
  let initial;
  try {
    initial = await compare(serviceId, { city: city || undefined, sort: "price_asc", locale });
  } catch (e) {
    // 404 — услуга не найдена; 422 — невалидный uuid (старая/числовая ссылка
    // вроде /service/1 после перехода каталога на uuid). И то, и другое → 404-страница,
    // а не падение 500.
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound();
    throw e;
  }

  const cities = await getCities().catch(() => [] as string[]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
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

      <ComparisonView
        serviceId={serviceId}
        initial={initial}
        cities={cities}
        initialCity={city}
        highlightClinicId={clinic || undefined}
      />
    </div>
  );
}
