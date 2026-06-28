"use client";

import Link from "next/link";
import { LanguageSwitcher, useT } from "@/lib/i18n";

export default function SiteHeader() {
  const { t } = useT();
  return (
    <header className="sticky top-0 z-30 border-b border-ink-100/80 bg-[var(--background)]/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link href="/" className="group flex items-center gap-2.5">
          <span className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 shadow-glow transition group-hover:scale-105">
            <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5 text-white" aria-hidden>
              <path d="M12 3v18M3 12h18" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
          </span>
          <span className="text-lg font-bold tracking-tight text-ink-900">
            Мед<span className="text-brand-600">Цена</span>
          </span>
        </Link>
        <nav className="flex items-center gap-3 text-sm sm:gap-4">
          <Link
            href="/recipe"
            className="font-medium text-ink-600 transition hover:text-brand-700"
          >
            {t("nav.recipe")}
          </Link>
          <LanguageSwitcher />
        </nav>
      </div>
    </header>
  );
}
