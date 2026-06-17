import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-4 px-4 py-24 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-50 text-brand-500">
        <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8" aria-hidden>
          <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8" />
          <path
            d="m16.5 16.5 4 4M8 11h6"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      </div>
      <h1 className="text-xl font-bold text-ink-900">Услуга не найдена</h1>
      <p className="text-sm text-ink-500">
        Возможно, услуга была удалена или ссылка устарела.
      </p>
      <Link href="/" className="btn-primary mt-2">
        Вернуться к поиску
      </Link>
    </div>
  );
}
