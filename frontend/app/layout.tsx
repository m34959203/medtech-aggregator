import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Image from "next/image";
import Link from "next/link";
import ChatWidget from "@/components/ChatWidget";
import "./globals.css";

const inter = Inter({
  subsets: ["latin", "cyrillic"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "МедЦена — сравнение цен на медуслуги в Казахстане",
  description:
    "Агрегатор цен на медицинские услуги. Сравните стоимость анализов, приёмов врачей и процедур в клиниках Казахстана и выберите выгоднее.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru" className={inter.variable}>
      <body className="flex min-h-screen flex-col">
        <SiteHeader />
        <main className="flex-1">{children}</main>
        <SiteFooter />
        <ChatWidget />
      </body>
    </html>
  );
}

function Logo() {
  return (
    <Link href="/" className="group flex items-center gap-2.5">
      <span className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 shadow-glow transition group-hover:scale-105">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          className="h-5 w-5 text-white"
          aria-hidden
        >
          <path
            d="M12 3v18M3 12h18"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        </svg>
      </span>
      <span className="flex flex-col leading-none">
        <span className="text-lg font-bold tracking-tight text-ink-900">
          Мед<span className="text-brand-600">Цена</span>
        </span>
      </span>
    </Link>
  );
}

function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-ink-100/80 bg-[var(--background)]/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Logo />
        <nav className="flex items-center gap-4 text-sm">
          <Link
            href="/compare"
            className="font-medium text-ink-600 transition hover:text-brand-700"
          >
            Сравнение
          </Link>
          <Link
            href="/recipe"
            className="font-medium text-ink-600 transition hover:text-brand-700"
          >
            По рецепту
          </Link>
          {/* «Нормализатор» — внутренний инструмент, живёт в админке (/admin/normalizer).
              Админка скрыта от обычных пользователей: доступ только по прямой
              ссылке /admin?key=ВАШ_КЛЮЧ (magic-link, см. AdminGate). */}
        </nav>
      </div>
    </header>
  );
}

function SiteFooter() {
  return (
    <footer className="border-t border-ink-100 bg-white">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 text-sm text-ink-500 sm:px-6">
        <p className="font-medium text-ink-700">МедЦена</p>
        <p>
          Независимый агрегатор цен на медицинские услуги в Казахстане. Данные с
          сайтов клиник носят справочный характер.
        </p>
        <p className="text-xs text-ink-400">
          © {new Date().getFullYear()} МедЦена. Уточняйте актуальную стоимость в
          клинике.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-x-8 gap-y-4 border-t border-ink-100 pt-4">
          <div className="flex items-center gap-3">
            <span className="text-xs text-ink-400">Организатор хакатона</span>
            <Image
              src="/organizer-logo.gif"
              alt="Логотип организатора хакатона"
              width={132}
              height={59}
              unoptimized
              className="h-auto w-[120px] opacity-90 [filter:brightness(0)]"
            />
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-ink-400">Спонсор хакатона</span>
            <Image
              src="/sponsor-logo.png"
              alt="Логотип спонсора хакатона"
              width={40}
              height={40}
              unoptimized
              className="h-10 w-auto opacity-90"
            />
          </div>
        </div>
      </div>
    </footer>
  );
}
