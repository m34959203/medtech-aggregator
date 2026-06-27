"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { chat, chatVision, ApiError } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import type { ChatOffer } from "@/lib/types";

interface UIMessage {
  role: "user" | "assistant";
  content: string;
  offers?: ChatOffer[];
  recognized?: string[]; // распознанные с фото услуги (OCR)
}

const GREETING: UIMessage = {
  role: "assistant",
  content:
    "Здравствуйте! Я помощник МедЦена. Подскажу, где дешевле сделать анализ, " +
    "УЗИ или попасть на приём врача. Что ищете?",
};

const SUGGESTIONS = [
  "Где дешевле общий анализ крови?",
  "УЗИ брюшной полости в Алматы",
  "Сколько стоит приём терапевта?",
];

const telHref = (phone: string) => `tel:${phone.replace(/[^\d+]/g, "")}`;
// Маршрут в Яндекс.Картах: по координатам клиники (как на /service и /recipe).
const routeHref = (lat: number, lng: number) =>
  `https://yandex.ru/maps/?rtext=~${lat},${lng}&rtt=auto`;
// service_id распознанной услуги ищем среди офферов (recognized = canonical_name).
const serviceIdFor = (name: string, offers?: ChatOffer[]) =>
  offers?.find((o) => o.service === name)?.service_id;
// Уникальные service_id ответа (для CTA «Собрать корзину» → /recipe?services=…).
const basketIds = (offers?: ChatOffer[]) =>
  Array.from(new Set((offers ?? []).map((o) => o.service_id))).filter(Boolean);

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<UIMessage[]>([GREETING]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || loading) return;
    const history: UIMessage[] = [...messages, { role: "user", content: q }];
    setMessages(history);
    setInput("");
    setLoading(true);
    try {
      // Бэкенду отправляем только роль+текст (без UI-полей offers).
      const payload = history
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({ role: m.role, content: m.content }));
      const res = await chat(payload);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.reply, offers: res.offers },
      ]);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? "Сервис временно недоступен. Попробуйте ещё раз чуть позже."
          : "Не удалось связаться с помощником. Проверьте соединение.";
      setMessages((prev) => [...prev, { role: "assistant", content: msg }]);
    } finally {
      setLoading(false);
    }
  }

  // OCR-путь: фото/скан направления → распознавание услуг → ответ по витрине.
  async function sendImage(file: File) {
    if (!file || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: `📷 ${file.name}` }]);
    setLoading(true);
    try {
      const res = await chatVision(file);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.reply, offers: res.offers, recognized: res.recognized },
      ]);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? "Не удалось распознать изображение. Попробуйте более чёткое фото."
          : "Не удалось связаться с помощником. Проверьте соединение.";
      setMessages((prev) => [...prev, { role: "assistant", content: msg }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {/* Плавающая кнопка */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Закрыть помощник" : "Открыть помощник"}
        className="fixed bottom-5 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-brand-600 text-white shadow-glow transition hover:scale-105 hover:bg-brand-700 active:scale-95 sm:bottom-6 sm:right-6"
      >
        {open ? (
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" aria-hidden>
            <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" aria-hidden>
            <path
              d="M21 11.5a8.5 8.5 0 01-12.5 7.5L3 20l1.1-3.3A8.5 8.5 0 1121 11.5z"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinejoin="round"
            />
            <circle cx="8.5" cy="11.5" r="1" fill="currentColor" />
            <circle cx="12" cy="11.5" r="1" fill="currentColor" />
            <circle cx="15.5" cy="11.5" r="1" fill="currentColor" />
          </svg>
        )}
      </button>

      {/* Панель чата */}
      {open && (
        <div className="fixed inset-x-3 bottom-24 z-40 flex max-h-[70vh] flex-col overflow-hidden rounded-3xl border border-ink-200 bg-white shadow-card-hover animate-fade-up sm:inset-x-auto sm:right-6 sm:w-[26rem]">
          {/* Шапка */}
          <div className="flex items-center gap-3 border-b border-ink-100 bg-brand-600 px-4 py-3 text-white">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/15">
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden>
                <path d="M12 3v18M3 12h18" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
              </svg>
            </span>
            <div className="leading-tight">
              <p className="text-sm font-semibold">Помощник МедЦена</p>
              <p className="text-xs text-white/75">Поиск и сравнение цен на медуслуги</p>
            </div>
          </div>

          {/* Лента сообщений */}
          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto bg-ink-50/60 px-4 py-4">
            {messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                <div className="max-w-[85%] space-y-2">
                  <div
                    className={
                      m.role === "user"
                        ? "whitespace-pre-wrap rounded-2xl rounded-br-sm bg-brand-600 px-3.5 py-2.5 text-sm text-white"
                        : "whitespace-pre-wrap rounded-2xl rounded-bl-sm bg-white px-3.5 py-2.5 text-sm text-ink-800 ring-1 ring-inset ring-ink-100"
                    }
                  >
                    {m.content}
                  </div>
                  {m.recognized && m.recognized.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1">
                      <span className="text-[10px] text-ink-400">Распознано:</span>
                      {m.recognized.slice(0, 8).map((r, j) => {
                        const sid = serviceIdFor(r, m.offers);
                        const cls =
                          "rounded-full bg-brand-50 px-2 py-0.5 text-[10px] font-medium text-brand-700 ring-1 ring-inset ring-brand-100";
                        // Чип услуги → полное сравнение /service/{id} (карта + запись).
                        return sid ? (
                          <Link key={j} href={`/service/${sid}`} className={cls + " transition hover:bg-brand-100"}>
                            {r} →
                          </Link>
                        ) : (
                          <span key={j} className={cls}>
                            {r}
                          </span>
                        );
                      })}
                    </div>
                  )}
                  {m.offers && m.offers.length > 0 && (
                    <div className="space-y-1.5">
                      {m.offers.slice(0, 5).map((o, j) => (
                        <div
                          key={j}
                          className={
                            "rounded-xl border px-3 py-2 text-xs " +
                            (o.is_cheapest
                              ? "border-brand-200 bg-brand-50"
                              : "border-ink-100 bg-white")
                          }
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-semibold text-ink-800">{o.clinic_name}</span>
                            <span className="whitespace-nowrap font-bold text-brand-700">
                              {formatPrice(o.price, o.currency)}
                            </span>
                          </div>
                          <div className="mt-0.5 flex items-center gap-2 text-ink-500">
                            <span className="truncate">
                              {o.is_cheapest && <span className="mr-1">🏆</span>}
                              {o.service}
                              {o.district || o.city
                                ? ` · ${o.district || o.city}`
                                : ""}
                            </span>
                          </div>
                          {/* Конечные действия (CTA): из результата — к услуге/клинике */}
                          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                            <Link
                              href={`/service/${o.service_id}?clinic=${o.clinic_id}`}
                              className="rounded-lg bg-brand-600 px-2.5 py-1 text-[11px] font-semibold text-white transition hover:bg-brand-700"
                            >
                              Сравнить и записаться
                            </Link>
                            {o.lat != null && o.lng != null && (
                              <a
                                href={routeHref(o.lat, o.lng)}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="font-medium text-brand-600 hover:underline"
                              >
                                Маршрут
                              </a>
                            )}
                            {o.phone && (
                              <a href={telHref(o.phone)} className="font-medium text-brand-600 hover:underline">
                                Позвонить
                              </a>
                            )}
                          </div>
                        </div>
                      ))}
                      {/* Итоговый CTA: из чата — в готовый выгодный маршрут «всё в одной клинике» */}
                      {basketIds(m.offers).length > 0 && (
                        <Link
                          href={`/recipe?services=${basketIds(m.offers).join(",")}`}
                          className="flex items-center justify-center gap-1.5 rounded-xl border border-brand-200 bg-brand-50 px-3 py-2 text-xs font-semibold text-brand-700 transition hover:bg-brand-100"
                        >
                          🛒 Собрать корзину
                        </Link>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="flex gap-1 rounded-2xl rounded-bl-sm bg-white px-4 py-3 ring-1 ring-inset ring-ink-100">
                  {[0, 150, 300].map((d) => (
                    <span
                      key={d}
                      className="h-2 w-2 animate-bounce rounded-full bg-ink-300"
                      style={{ animationDelay: `${d}ms` }}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Подсказки на старте */}
            {messages.length === 1 && !loading && (
              <div className="flex flex-wrap gap-2 pt-1">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => send(s)}
                    className="rounded-full border border-brand-200 bg-white px-3 py-1.5 text-xs text-brand-700 transition hover:bg-brand-50"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Ввод */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex items-center gap-2 border-t border-ink-100 bg-white px-3 py-2.5"
          >
            <input
              ref={fileRef}
              type="file"
              accept="image/*,.pdf,.png,.jpg,.jpeg,.webp,.tiff"
              capture="environment"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) sendImage(f);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={loading}
              aria-label="Прикрепить фото направления"
              title="Фото/скан направления — распознаю услуги"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-ink-200 text-ink-500 transition hover:border-brand-300 hover:text-brand-700 disabled:opacity-40"
            >
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden>
                <path d="M4 8.5A2.5 2.5 0 016.5 6h1l1-1.5h6L16 6h1.5A2.5 2.5 0 0120 8.5v8A2.5 2.5 0 0117.5 19h-11A2.5 2.5 0 014 16.5v-8z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
                <circle cx="12" cy="12.5" r="3" stroke="currentColor" strokeWidth="1.6" />
              </svg>
            </button>
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Спросите или пришлите фото направления…"
              className="flex-1 rounded-full border border-ink-200 bg-ink-50 px-4 py-2.5 text-sm text-ink-800 outline-none transition focus:border-brand-400 focus:bg-white focus:ring-2 focus:ring-brand-100"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              aria-label="Отправить"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden>
                <path d="M4 12l16-8-6 8 6 8-16-8z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
              </svg>
            </button>
          </form>

          <p className="bg-white px-4 pb-3 text-center text-[10px] leading-tight text-ink-400">
            Помощник использует только цены из базы агрегатора. Стоимость справочная — уточняйте в клинике.
          </p>
        </div>
      )}
    </>
  );
}
