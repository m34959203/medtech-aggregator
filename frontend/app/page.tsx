import SearchExperience from "@/components/SearchExperience";
import { getCategories, getCities, search } from "@/lib/api";
import type { ServiceComparison } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  // Параллельно тянем стартовые данные. Бэкенд может быть недоступен —
  // деградируем мягко до пустых списков, клиент покажет ошибку при поиске.
  const [cities, categories, initialResults] = await Promise.all([
    getCities().catch(() => [] as string[]),
    getCategories().catch(() => [] as string[]),
    search({ limit: 12 }).catch(() => [] as ServiceComparison[]),
  ]);

  return (
    <>
      <Hero />
      <SearchExperience
        cities={cities}
        categories={categories}
        initialResults={initialResults}
      />
    </>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-ink-100 bg-white">
      <div className="grid-bg absolute inset-0" aria-hidden />
      <div
        className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-brand-200/40 blur-3xl"
        aria-hidden
      />
      <div className="relative mx-auto max-w-6xl px-4 pb-12 pt-14 sm:px-6 sm:pt-16">
        <div className="max-w-3xl">
          <span className="badge mb-5 bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-100">
            <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
            Независимый агрегатор · Казахстан
          </span>
          <h1 className="text-balance text-4xl font-extrabold leading-[1.08] tracking-tight text-ink-900 sm:text-[52px]">
            Сравните цены на медуслуги{" "}
            <span className="text-brand-600">и&nbsp;не переплачивайте</span>
          </h1>
          <p className="mt-5 max-w-xl text-pretty text-base leading-relaxed text-ink-500 sm:text-lg">
            Анализы, приёмы врачей, УЗИ, МРТ и процедуры в клиниках Казахстана —
            в одном месте. Находите выгодную цену рядом с домом.
          </p>
        </div>
      </div>
    </section>
  );
}
