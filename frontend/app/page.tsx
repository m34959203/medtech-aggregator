import { cookies } from "next/headers";
import Hero from "@/components/Hero";
import SearchExperience from "@/components/SearchExperience";
import { getCategories, getCities, search } from "@/lib/api";
import type { ServiceComparison } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const locale = (await cookies()).get("locale")?.value === "kk" ? "kk" : "ru";
  // Параллельно тянем стартовые данные. Бэкенд может быть недоступен —
  // деградируем мягко до пустых списков, клиент покажет ошибку при поиске.
  const [cities, categories, initialResults] = await Promise.all([
    getCities().catch(() => [] as string[]),
    getCategories().catch(() => [] as string[]),
    search({ limit: 12, locale }).catch(() => [] as ServiceComparison[]),
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
