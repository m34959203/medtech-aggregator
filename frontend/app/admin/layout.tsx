"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import AdminGate from "@/components/AdminGate";

// Гейт распространяется на весь /admin/*: содержимое (и его запросы к защищённым
// /api/*) монтируется только после успешной авторизации. Навигация админ-разделов
// видна ТОЛЬКО внутри гейта — обычный пользователь её не видит (публичной ссылки
// на /admin нет, вход по magic-link /admin?key=...).
const TABS = [
  { href: "/admin", label: "Приём данных" },
  { href: "/admin/review", label: "Очередь проверки" },
  { href: "/admin/whatsapp", label: "WhatsApp" },
  { href: "/admin/normalizer", label: "Нормализатор" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <AdminGate>
      <div className="border-b border-ink-100 bg-white">
        <nav className="mx-auto flex max-w-6xl items-center gap-1 px-4 sm:px-6">
          {TABS.map((t) => {
            const active =
              t.href === "/admin" ? pathname === "/admin" : pathname.startsWith(t.href);
            return (
              <Link
                key={t.href}
                href={t.href}
                className={`-mb-px border-b-2 px-3 py-3 text-sm font-medium transition ${
                  active
                    ? "border-brand-600 text-brand-700"
                    : "border-transparent text-ink-500 hover:text-ink-800"
                }`}
              >
                {t.label}
              </Link>
            );
          })}
        </nav>
      </div>
      {children}
    </AdminGate>
  );
}
