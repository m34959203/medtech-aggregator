"use client";

import { useCallback, useEffect, useState } from "react";
import { authLogin, authLogout, authMe } from "@/lib/api";

/**
 * Гейт админ-зоны (passwordless). Пускает дальше только при валидной сессии.
 * Поддерживает magic-link `?key=<токен>`: ключ автоматически логинит и убирается
 * из URL — администратору не нужно ничего печатать. Ручной ввод ключа — запасной путь.
 */
export default function AdminGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"checking" | "in" | "out">("checking");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);

  const check = useCallback(async () => {
    try {
      const me = await authMe();
      setState(me.authenticated ? "in" : "out");
    } catch {
      setState("out");
    }
  }, []);

  useEffect(() => {
    // magic-link: ?key=... → логин и зачистка URL
    const url = new URL(window.location.href);
    const key = url.searchParams.get("key");
    if (key) {
      authLogin(key)
        .catch(() => {})
        .finally(() => {
          url.searchParams.delete("key");
          window.history.replaceState({}, "", url.toString());
          check();
        });
    } else {
      check();
    }
  }, [check]);

  if (state === "checking") {
    return <div className="mx-auto max-w-md px-4 py-24 text-center text-ink-400">Проверка доступа…</div>;
  }

  if (state === "out") {
    return (
      <div className="mx-auto max-w-md px-4 py-20">
        <div className="card p-6">
          <h1 className="text-lg font-semibold text-ink-900">Админ-зона</h1>
          <p className="mt-1 text-sm text-ink-500">
            Доступ по ключу. Откройте ссылку вида <code>…/admin?key=ВАШ_КЛЮЧ</code> или
            вставьте ключ доступа.
          </p>
          <form
            className="mt-4 flex gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              setError(null);
              try {
                await authLogin(token.trim());
                await check();
              } catch {
                setError("Неверный ключ доступа.");
              }
            }}
          >
            <input
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Ключ доступа"
              className="field flex-1 py-2 text-sm"
            />
            <button
              type="submit"
              className="rounded-full bg-brand-600 px-5 py-2 text-sm font-semibold text-white transition hover:bg-brand-700"
            >
              Войти
            </button>
          </form>
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mx-auto flex max-w-6xl justify-end px-4 pt-4 sm:px-6">
        <button
          type="button"
          onClick={async () => {
            await authLogout();
            setState("out");
          }}
          className="text-xs font-medium text-ink-400 transition hover:text-ink-700"
        >
          Выйти
        </button>
      </div>
      {children}
    </div>
  );
}
