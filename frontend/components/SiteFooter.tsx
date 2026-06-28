"use client";

import Image from "next/image";
import { useT } from "@/lib/i18n";

export default function SiteFooter() {
  const { t } = useT();
  const year = 2026;
  return (
    <footer className="border-t border-ink-100 bg-white">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 text-sm text-ink-500 sm:px-6">
        <p className="font-medium text-ink-700">МедЦена</p>
        <p>{t("footer.tagline")}</p>
        <p className="text-xs text-ink-400">© {year} МедЦена. {t("footer.disclaimer")}</p>
        <div className="mt-4 flex flex-wrap items-center gap-x-8 gap-y-4 border-t border-ink-100 pt-4">
          <div className="flex items-center gap-3">
            <span className="text-xs text-ink-400">{t("footer.organizer")}</span>
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
            <span className="text-xs text-ink-400">{t("footer.sponsor")}</span>
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
