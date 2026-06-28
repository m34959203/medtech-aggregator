"use client";

// Двуязычие RU/KK. Локаль хранится в cookie `locale` (читается и сервером для SSR)
// и в localStorage. UI берёт строки через useT(); ИИ-чат получает locale в запросе.
import { createContext, useCallback, useContext, useEffect, useState } from "react";

export type Locale = "ru" | "kk";
export const LOCALES: Locale[] = ["ru", "kk"];

// Словарь: ключ → перевод. Отсутствующий KK-ключ деградирует к RU, затем к самому ключу.
const M: Record<Locale, Record<string, string>> = {
  ru: {
    "nav.recipe": "По рецепту",
    "nav.all": "Все услуги",
    "lang.ru": "Рус",
    "lang.kk": "Қаз",

    "hero.badge": "Независимый агрегатор · Казахстан",
    "hero.title1": "Сравните цены на медуслуги",
    "hero.title2": "и не переплачивайте",
    "hero.subtitle":
      "Анализы, приёмы врачей, УЗИ, МРТ и процедуры в клиниках Казахстана — в одном месте. Находите выгодную цену рядом с домом.",

    "search.placeholder": "Например: МРТ головного мозга, УЗИ, приём кардиолога…",
    "search.allCities": "Все города",
    "search.allCategories": "Все категории",
    "sort.cheaper": "Дешевле",
    "sort.pricier": "Дороже",
    "sort.closer": "Ближе",
    "geo.enable": "Рядом со мной — учесть расстояние",
    "geo.loading": "Определяем…",
    "geo.on": "Местоположение учтено — показываем расстояние",
    "geo.reset": "сбросить",
    "geo.denied": "Доступ к геолокации отклонён — разрешите его в браузере.",

    "results.popular": "Популярные услуги",
    "results.search": "Результаты поиска",
    "results.empty.title": "Ничего не нашлось",
    "results.empty.text": "Попробуйте изменить запрос, выбрать другой город или сбросить фильтр категории.",
    "results.error.title": "Что-то пошло не так",
    "results.retry": "Повторить",

    "card.from": "от",
    "card.nearest": "До ближайшей клиники с этой услугой",

    "footer.tagline":
      "Независимый агрегатор цен на медицинские услуги в Казахстане. Данные с сайтов клиник носят справочный характер.",
    "footer.disclaimer": "Уточняйте актуальную стоимость в клинике.",
    "footer.organizer": "Организатор хакатона",
    "footer.sponsor": "Спонсор хакатона",

    "chat.title": "Помощник МедЦены",
    "chat.greeting":
      "Здравствуйте! Спросите, где дешевле сделать анализ или приём, или пришлите фото направления — найду цены по клиникам.",
    "chat.placeholder": "Спросите или пришлите фото направления…",
    "chat.send": "Отправить",
  },
  kk: {
    "nav.recipe": "Рецепт бойынша",
    "nav.all": "Барлық қызметтер",
    "lang.ru": "Рус",
    "lang.kk": "Қаз",

    "hero.badge": "Тәуелсіз агрегатор · Қазақстан",
    "hero.title1": "Медқызметтер бағасын салыстырыңыз",
    "hero.title2": "әрі артық төлемеңіз",
    "hero.subtitle":
      "Талдаулар, дәрігер қабылдаулары, УДЗ, МРТ және емшаралар — Қазақстан клиникаларында бір жерде. Үйге жақын тиімді бағаны табыңыз.",

    "search.placeholder": "Мысалы: бас миының МРТ-сы, УДЗ, кардиолог қабылдауы…",
    "search.allCities": "Барлық қалалар",
    "search.allCategories": "Барлық санаттар",
    "sort.cheaper": "Арзанырақ",
    "sort.pricier": "Қымбатырақ",
    "sort.closer": "Жақынырақ",
    "geo.enable": "Маған жақын — қашықтықты ескеру",
    "geo.loading": "Анықталуда…",
    "geo.on": "Орналасуыңыз ескерілді — қашықтық көрсетіледі",
    "geo.reset": "тазалау",
    "geo.denied": "Геолокацияға рұқсат берілмеді — браузерде рұқсат етіңіз.",

    "results.popular": "Танымал қызметтер",
    "results.search": "Іздеу нәтижелері",
    "results.empty.title": "Ештеңе табылмады",
    "results.empty.text": "Сұранысты өзгертіп, басқа қаланы таңдап немесе санат сүзгісін тазалап көріңіз.",
    "results.error.title": "Бірдеңе дұрыс болмады",
    "results.retry": "Қайталау",

    "card.from": "бастап",
    "card.nearest": "Осы қызметі бар ең жақын клиникаға дейін",

    "footer.tagline":
      "Қазақстандағы медициналық қызметтер бағасының тәуелсіз агрегаторы. Клиника сайттарынан алынған деректер анықтамалық сипатта.",
    "footer.disclaimer": "Нақты бағаны клиникада нақтылаңыз.",
    "footer.organizer": "Хакатон ұйымдастырушысы",
    "footer.sponsor": "Хакатон демеушісі",

    "chat.title": "МедЦена көмекшісі",
    "chat.greeting":
      "Сәлеметсіз бе! Қай жерде талдау не қабылдау арзанырақ екенін сұраңыз немесе жолдама суретін жіберіңіз — клиникалар бойынша бағаны табамын.",
    "chat.placeholder": "Сұрақ қойыңыз немесе жолдама суретін жіберіңіз…",
    "chat.send": "Жіберу",
  },
};

interface Ctx {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string) => string;
}
const LangCtx = createContext<Ctx>({ locale: "ru", setLocale: () => {}, t: (k) => k });

export function LangProvider({
  initial = "ru",
  children,
}: {
  initial?: Locale;
  children: React.ReactNode;
}) {
  const [locale, setLoc] = useState<Locale>(initial);

  useEffect(() => {
    const m = document.cookie.match(/(?:^|; )locale=(ru|kk)/);
    const c = (m?.[1] as Locale | undefined) ?? null;
    if (c && c !== locale) setLoc(c);
    document.documentElement.lang = c ?? locale;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setLocale = useCallback((l: Locale) => {
    setLoc(l);
    document.cookie = `locale=${l}; path=/; max-age=31536000; samesite=lax`;
    try {
      localStorage.setItem("locale", l);
    } catch {
      /* приватный режим */
    }
    document.documentElement.lang = l;
  }, []);

  const t = useCallback(
    (key: string) => M[locale][key] ?? M.ru[key] ?? key,
    [locale],
  );

  return <LangCtx.Provider value={{ locale, setLocale, t }}>{children}</LangCtx.Provider>;
}

export const useT = () => useContext(LangCtx);

export function LanguageSwitcher() {
  const { locale, setLocale } = useT();
  return (
    <div className="flex items-center rounded-full border border-ink-200 bg-white p-0.5 text-xs font-semibold">
      {LOCALES.map((l) => (
        <button
          key={l}
          type="button"
          onClick={() => setLocale(l)}
          aria-pressed={locale === l}
          className={`rounded-full px-2.5 py-1 transition ${
            locale === l ? "bg-brand-600 text-white" : "text-ink-500 hover:text-ink-800"
          }`}
        >
          {l === "ru" ? "Рус" : "Қаз"}
        </button>
      ))}
    </div>
  );
}
