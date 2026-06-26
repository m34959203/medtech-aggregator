"use client";

import AdminGate from "@/components/AdminGate";

// Гейт распространяется на /admin и /admin/review: содержимое (и его запросы к
// защищённым /api/*) монтируется только после успешной авторизации.
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AdminGate>{children}</AdminGate>;
}
