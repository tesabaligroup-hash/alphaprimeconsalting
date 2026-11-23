import { useRef, useState } from "react";
import { api, openDocument, openMyFile, uploadFile, type MyFile } from "../api";
import { dateNum } from "../format";
import { IDoc, IDownload } from "../icons";
import { ErrorBox, Loading, useApp, useLoad } from "../ui";
import { LinkPhoneCard } from "./common";

type Group = { person: string; files: { uuid: string; name: string; created_at: string | null; service: string; lead_id: number; archived: boolean; valid_until: string | null }[] };

export default function Documents() {
  const { toast } = useApp();
  const { data, error, reload } = useLoad<{ groups: Group[] }>("/api/documents");
  const [tab, setTab] = useState<"ready" | "archive" | "mine">("ready");
  const groups = (data?.groups ?? [])
    .map((g) => ({ ...g, files: g.files.filter((f) => (tab === "archive" ? f.archived : !f.archived)) }))
    .filter((g) => g.files.length);
  return (
    <>
      <header className="top" style={{ gap: 14 }}>
        <h1 className="title">Документы</h1>
        <div className="seg" role="tablist" aria-label="Фильтр">
          <button role="tab" aria-selected={tab === "ready"} onClick={() => setTab("ready")}>Активные</button>
          <button role="tab" aria-selected={tab === "archive"} onClick={() => setTab("archive")}>Архив</button>
          <button role="tab" aria-selected={tab === "mine"} onClick={() => setTab("mine")}>Мои файлы</button>
        </div>
      </header>
      {tab === "mine" ? <main className="screen" style={{ gap: 16 }}><MyFiles /></main> : (
      <main className="screen" style={{ gap: 22 }}>
        <LinkPhoneCard />
        {error && <ErrorBox error={error} onRetry={reload} />}
        {!data && !error && <Loading rows={3} />}
        {data && groups.length === 0 && <div className="empty">{tab === "ready" ? "Активных документов пока нет. Действующие визы и ITK появятся здесь, как только будут готовы." : "Архив пуст."}</div>}
        {groups.map((g) => (
          <section key={g.person} className="section" style={{ gap: 10 }}>
            <h2 className="kicker" style={{ color: "#5E5849", letterSpacing: ".08em", margin: 0 }}>{g.person}</h2>
            {g.files.map((f) => (
              <button key={f.uuid} className="card" onClick={() => openDocument(f.lead_id, f.uuid).catch((e) => toast(e.message))}
                aria-label={`Скачать ${f.name}`} style={{ flexDirection: "row", alignItems: "center", gap: 12, padding: 12 }}>
                <span style={{ width: 44, height: 44, flex: "none", borderRadius: 12, background: "#FAF3E1", display: "flex", alignItems: "center", justifyContent: "center" }}><IDoc color="#7A5C17" /></span>
                <div className="grow"><span className="b">{f.name}</span><span className="small">{f.service}{f.created_at ? ` · ${dateNum(f.created_at)}` : ""}{f.valid_until ? ` · до ${dateNum(f.valid_until)}` : ""}</span></div>
                <span aria-hidden="true" style={{ width: 44, height: 44, flex: "none", borderRadius: 22, border: "1px solid #E8DFC9", display: "flex", alignItems: "center", justifyContent: "center" }}><IDownload /></span>
              </button>
            ))}
          </section>
        ))}
      </main>
      )}
    </>
  );
}

/** Личный сейф: клиент сам хранит паспорт, права, страховку и т.п. */
function MyFiles() {
  const { toast } = useApp();
  const { data, error, reload } = useLoad<{ files: MyFile[]; categories: Record<string, string> }>("/api/my-files");
  const [adding, setAdding] = useState(false);
  const [category, setCategory] = useState("passport");
  const [title, setTitle] = useState("");
  const [until, setUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading rows={2} />;

  const send = async (file: File) => {
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    form.append("category", category);
    form.append("title", title);
    form.append("valid_until", until);
    try {
      await uploadFile("/api/my-files", form);
      toast("Документ сохранён");
      setAdding(false); setTitle(""); setUntil("");
      reload();
    } catch (e) { toast((e as Error).message); }
    finally { setBusy(false); if (input.current) input.current.value = ""; }
  };
  const remove = async (f: MyFile) => {
    if (!window.confirm(`Удалить «${f.title}»?`)) return;
    try { await api.del(`/api/my-files/${f.id}`); reload(); } catch (e) { toast((e as Error).message); }
  };
  const soon = (d: string | null) => d && (new Date(d).getTime() - Date.now()) / 86400000 < 60;

  return (
    <>
      <section className="card cream" style={{ gap: 8 }}>
        <span className="b">Храните важные документы под рукой</span>
        <span className="small">Паспорт, водительские права, страховка, договор аренды — всегда в телефоне, даже без интернета на почте. Файлы видите только вы; храним на защищённом сервере Alpha Prime.</span>
        {!adding && <button className="btn" onClick={() => setAdding(true)}>＋ Загрузить документ</button>}
      </section>

      {adding && (
        <section className="card" style={{ gap: 10 }}>
          <span className="b">Новый документ</span>
          <label className="small">Что это
            <select className="input" value={category} onChange={(e) => setCategory(e.target.value)} style={{ width: "100%", marginTop: 4 }}>
              {Object.entries(data.categories).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="small">Название (необязательно)
            <input className="input" placeholder="Например: Паспорт — разворот с фото" value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: "100%", marginTop: 4 }} />
          </label>
          <label className="small">Действует до (необязательно)
            <input className="input" type="date" value={until} onChange={(e) => setUntil(e.target.value)} style={{ width: "100%", marginTop: 4 }} />
          </label>
          <input ref={input} type="file" accept="image/*,application/pdf" style={{ display: "none" }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) send(f); }} />
          <button className="btn" disabled={busy} onClick={() => input.current?.click()}>{busy ? "Загружаем…" : "Выбрать фото или PDF"}</button>
          <button className="btn line" disabled={busy} onClick={() => setAdding(false)}>Отмена</button>
          <span className="small muted">Фото или PDF до 10 МБ.</span>
        </section>
      )}

      {data.files.length === 0 && !adding && <div className="empty">Здесь пока пусто. Загрузите первый документ — например, паспорт.</div>}
      {data.files.map((f) => (
        <div key={f.id} className="card" style={{ flexDirection: "row", alignItems: "center", gap: 12, padding: 12 }}>
          <button onClick={() => openMyFile(f.id).catch((e) => toast(e.message))} aria-label={`Открыть ${f.title}`}
            style={{ display: "flex", gap: 12, alignItems: "center", flex: 1, background: "none", border: 0, padding: 0, textAlign: "left" }}>
            <span style={{ width: 44, height: 44, flex: "none", borderRadius: 12, background: "#FAF3E1", display: "flex", alignItems: "center", justifyContent: "center" }}><IDoc color="#7A5C17" /></span>
            <div className="grow">
              <span className="b">{f.title}</span>
              <span className="small">{f.category_label}{f.valid_until ? ` · до ${dateNum(f.valid_until)}` : ""}</span>
              {soon(f.valid_until) && <span className="small" style={{ color: "#A1452E", fontWeight: 700 }}>Скоро истекает — пора продлевать</span>}
            </div>
          </button>
          <button aria-label="Удалить" onClick={() => remove(f)} style={{ background: "none", border: 0, color: "#A1452E", fontSize: 13, fontWeight: 700 }}>Удалить</button>
        </div>
      ))}
    </>
  );
}
