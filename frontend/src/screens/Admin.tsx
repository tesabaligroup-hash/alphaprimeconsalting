import { useEffect, useState } from "react";
import { api, type AdminResult } from "../api";
import { useApp } from "../ui";

/** Админ: найти клиента по телефону, @нику или имени и открыть приложение так, как его видит он. */
export default function Admin() {
  const { startViewAs, toast } = useApp();
  const [q, setQ] = useState("");
  const [items, setItems] = useState<AdminResult[] | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 3) { setItems(null); return; }
    const t = setTimeout(async () => {
      setBusy(true);
      try { setItems((await api.get<{ results: AdminResult[] }>(`/api/admin/search?q=${encodeURIComponent(term)}`)).results); }
      catch (e) { toast((e as Error).message); }
      finally { setBusy(false); }
    }, 450);
    return () => clearTimeout(t);
  }, [q, toast]);

  const open = async (r: AdminResult) => {
    try {
      const v = await api.post<{ key: string; name: string }>("/api/admin/view", { key: r.key });
      startViewAs(v.key, v.name);
    } catch (e) { toast((e as Error).message); }
  };

  return (
    <main className="screen">
      <header className="top">
        <span className="kicker">Только для сотрудников</span>
        <h1 className="title">Смотреть как клиент</h1>
        <span className="muted">Введите телефон, @ник или имя — откроется приложение так, как его видит клиент. Менять ничего нельзя, QR и ссылки партнёра — можно.</span>
      </header>
      <section className="card" style={{ gap: 10 }}>
        <input className="input" autoFocus placeholder="+62…, @nick или имя" value={q} onChange={(e) => setQ(e.target.value)} />
        {busy && <span className="small muted">Ищу…</span>}
        {items && items.length === 0 && !busy && <span className="small muted">Никого не нашли. Попробуйте последние цифры телефона или имя латиницей.</span>}
        {items?.map((r) => (
          <button key={r.key} className="row" style={{ textAlign: "left", display: "flex", gap: 10, alignItems: "center", padding: "10px 0", borderTop: "1px solid #EFE7D4", background: "none", width: "100%" }} onClick={() => open(r)}>
            <span style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
              <span className="b">{r.name}</span>
              <span className="small muted">{[r.nick ? "@" + r.nick : null, r.phone].filter(Boolean).join(" · ") || "—"}</span>
            </span>
            <span className="small" style={{ color: r.in_bot ? "#3D6B2E" : "#7A5C17", fontWeight: 700, textAlign: "right" }}>
              {r.in_bot ? "в боте" : "только Kommo"}{r.partner ? " · партнёр" : ""}
            </span>
          </button>
        ))}
      </section>
    </main>
  );
}
