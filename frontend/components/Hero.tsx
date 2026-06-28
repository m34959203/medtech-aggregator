"use client";

import { useT } from "@/lib/i18n";

export default function Hero() {
  const { t } = useT();
  return (
    <section className="relative overflow-hidden border-b border-ink-100 bg-white">
      <div className="grid-bg absolute inset-0" aria-hidden />
      <div
        className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-brand-200/40 blur-3xl"
        aria-hidden
      />
      <div className="relative mx-auto max-w-6xl px-4 pb-12 pt-14 sm:px-6 sm:pt-16">
        <div className="mx-auto max-w-2xl text-center">
          <span className="badge mb-5 bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-100">
            <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
            {t("hero.badge")}
          </span>
          <h1 className="text-balance text-4xl font-extrabold leading-[1.08] tracking-tight text-ink-900 sm:text-[52px]">
            {t("hero.title1")}{" "}
            <span className="text-brand-600">{t("hero.title2")}</span>
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-pretty text-base leading-relaxed text-ink-500 sm:text-lg">
            {t("hero.subtitle")}
          </p>
        </div>
      </div>
    </section>
  );
}
