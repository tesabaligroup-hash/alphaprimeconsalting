import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, type Me } from "./api";
import { IBack, IBag, IDoc, IHome, IPeople, IUser } from "./icons";

// ---------- Навигация ----------
export type Route =
  | { name: "home" } | { name: "services"; tab?: "mine" | "all" } | { name: "service"; id: number }
  | { name: "documents" } | { name: "partner" } | { name: "referrals" } | { name: "share" } | { name: "profile" };

type Ctx = { route: Route; go: (r: Route) => void; back: () => void; me: Me | null; reloadMe: () => void; toast: (t: string) => void };
export const AppCtx = createContext<Ctx>(null as unknown as Ctx);
export const useApp = () => useContext(AppCtx);

export function useLoad<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!path) return;
    let alive = true;
    setError(null);
    api.get<T>(path).then((d) => alive && setData(d)).catch((e) => alive && setError(e));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, n, ...deps]);
  const reload = useCallback(() => setN((x) => x + 1), []);
  return { data, error, reload, setData };
}

export function Nav() {
  const { route, go } = useApp();
  const tabs = [
    { key: "home", label: "Главная", icon: IHome, r: { name: "home" } as Route, match: ["home"] },
    { key: "services", label: "Услуги", icon: IBag, r: { name: "services" } as Route, match: ["services", "service"] },
    { key: "documents", label: "Документы", icon: IDoc, r: { name: "documents" } as Route, match: ["documents"] },
    { key: "partner", label: "Партнёрка", icon: IPeople, r: { name: "partner" } as Route, match: ["partner", "referrals", "share"] },
    { key: "profile", label: "Профиль", icon: IUser, r: { name: "profile" } as Route, match: ["profile"] },
  ];
  return (
    <nav className="nav" aria-label="Основное меню">
      <div className="nav-inner">
        {tabs.map((t) => {
          const on = t.match.includes(route.name);
          const Icon = t.icon;
          return (
            <button key={t.key} aria-current={on ? "page" : undefined} onClick={() => go(t.r)}>
              <Icon color={on ? "#7A5C17" : "#6B6556"} />
              {t.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}

export function BackTop({ kicker, title, sub }: { kicker?: string; title: string; sub?: string }) {
  const { back } = useApp();
  return (
    <header className="top">
      <button className="back" aria-label="Назад" onClick={back}><IBack /></button>
      {kicker && <span className="kicker">{kicker}</span>}
      <h1 className="title">{title}</h1>
      {sub && <span className="muted">{sub}</span>}
    </header>
  );
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="screen" aria-busy="true" aria-label="Загрузка">
      {Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton" style={{ height: i === 0 ? 160 : 90 }} />)}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  return (
    <div className="screen"><div className="empty">
      <p>{error.message}</p>
      <button className="btn line" onClick={onRetry}>Повторить</button>
    </div></div>
  );
}

export function Accordion({ title, open: initial = false, children }: { title: string; open?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(initial);
  return (
    <div className="acc" style={{ border: "1px solid #ECE4D2" }}>
      <button className="acc-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>{title}</span>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
      </button>
      {open && <div className="acc-body">{children}</div>}
    </div>
  );
}

export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
