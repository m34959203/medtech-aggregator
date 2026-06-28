import type { Metadata } from "next";
import { Golos_Text } from "next/font/google";
import { cookies } from "next/headers";
import ChatWidget from "@/components/ChatWidget";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";
import { LangProvider, type Locale } from "@/lib/i18n";
import "./globals.css";

// Дизайн «МедЦена» — шрифт Golos Text. Переменная оставлена как --font-inter,
// чтобы не трогать ссылку в tailwind fontFamily.sans.
const golos = Golos_Text({
  subsets: ["latin", "cyrillic"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "МедЦена — сравнение цен на медуслуги в Казахстане",
  description:
    "Агрегатор цен на медицинские услуги. Сравните стоимость анализов, приёмов врачей и процедур в клиниках Казахстана и выберите выгоднее.",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // Локаль из cookie (RU по умолчанию) — для согласованного SSR с клиентом.
  const initial: Locale = (await cookies()).get("locale")?.value === "kk" ? "kk" : "ru";
  return (
    <html lang={initial} className={golos.variable}>
      <body className="flex min-h-screen flex-col">
        <LangProvider initial={initial}>
          <SiteHeader />
          <main className="flex-1">{children}</main>
          <SiteFooter />
          <ChatWidget />
        </LangProvider>
      </body>
    </html>
  );
}
