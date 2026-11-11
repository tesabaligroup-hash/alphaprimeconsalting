import { useState } from "react";
import { openDocument } from "../api";
import { dateNum } from "../format";
import { IDoc, IDownload } from "../icons";
import { ErrorBox, Loading, useApp, useLoad } from "../ui";
import { LinkPhoneCard } from "./common";

type Group = { person: string; files: { uuid: string; name: string; created_at: string | null; service: string; lead_id: number; archived: boolean; valid_until: string | null }[] };

export default function Documents() {
  const { toast } = useApp();
  const { data, error, reload } = useLoad<{ groups: Group[] }>("/api/documents");
  const [tab, setTab] = useState<"ready" | "archive">("ready");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading rows={3} />;
  const groups = data.groups
    .map((g) => ({ ...g, files: g.files.filter((f) => (tab === "archive" ? f.archived : !f.archived)) }))
    .filter((g) => g.files.length);
  return (
    <>
      <header className="top" style={{ gap: 14 }}>
        <h1 className="title">Документы</h1>
        <div className="seg" role="tablist" aria-label="Фильтр">
          <button role="tab" aria-selected={tab === "ready"} onClick={() => setTab("ready")}>Готовые</button>
          <button role="tab" aria-selected={tab === "archive"} onClick={() => setTab("archive")}>Архив</button>
        </div>
      </header>
      <main className="screen" style={{ gap: 22 }}>
        <LinkPhoneCard />
        {groups.length === 0 && <div className="empty">{tab === "ready" ? "Готовых документов пока нет. Они появятся здесь, как только услуга будет выполнена." : "Архив пуст."}</div>}
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
    </>
  );
}
