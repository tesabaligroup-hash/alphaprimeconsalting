import { useState } from "react";
import { api, type Catalog, type Service } from "../api";
import { money } from "../format";
import { haptic } from "../tg";
import { ErrorBox, Loading, useApp, useLoad } from "../ui";
import { LinkPhoneCard, ServiceCardView } from "./common";

export default function Services({ initialTab }: { initialTab?: "mine" | "all" }) {
  const { me } = useApp();
  const [tab, setTab] = useState<"mine" | "all">(initialTab ?? (me?.linked ? "mine" : "all"));
  return (
    <>
      <header className="top" style={{ gap: 14 }}>
        <h1 className="title">Услуги</h1>
        <div className="seg" role="tablist" aria-label="Раздел">
          <button role="tab" aria-selected={tab === "mine"} onClick={() => setTab("mine")}>Мои услуги</button>
          <button role="tab" aria-selected={tab === "all"} onClick={() => setTab("all")}>Все услуги</button>
        </div>
      </header>
      {tab === "mine" ? <Mine /> : <All />}
    </>
  );
}

function Mine() {
  const { data, error, reload } = useLoad<{ services: Service[]; archive: Service[] }>("/api/services");
  const [showArchive, setShowArchive] = useState(false);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading rows={2} />;
  return (
    <main className="screen" style={{ gap: 12 }}>
      <LinkPhoneCard />
      {data.services.map((s) => <ServiceCardView key={s.lead_id} s={s} />)}
      {data.services.length === 0 && <div className="empty">Активных услуг пока нет.<br />Выберите нужную во вкладке «Все услуги».</div>}
      {data.archive.length > 0 && (
        <>
          <button className="btn line" style={{ borderColor: "#ECE4D2" }} onClick={() => setShowArchive(!showArchive)}>
            {showArchive ? "Скрыть архив" : `Архив завершённых услуг (${data.archive.length})`}
          </button>
          {showArchive && data.archive.map((s) => <ServiceCardView key={s.lead_id} s={s} />)}
        </>
      )}
    </main>
  );
}

function All() {
  const { toast } = useApp();
  const { data, error, reload } = useLoad<Catalog>("/api/catalog");
  const [cat, setCat] = useState<string | null>(null);
  const [sent, setSent] = useState<Set<string>>(new Set());
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading rows={4} />;
  const active = data.categories.find((c) => c.id === cat) ?? data.categories[0];
  const order = async (code: string) => {
    try {
      await api.post("/api/orders", { code });
      haptic();
      setSent(new Set(sent).add(code));
      toast("Заявка отправлена — менеджер свяжется с вами");
    } catch (e) {
      toast((e as Error).message);
    }
  };
  return (
    <main className="screen" style={{ gap: 10, paddingTop: 0 }}>
      <div className="chips" role="tablist" aria-label="Категории">
        {data.categories.map((c) => (
          <button key={c.id} role="tab" className="chip" aria-selected={c.id === active.id} onClick={() => setCat(c.id)}>{c.label}</button>
        ))}
      </div>
      {active.items.map((s) => (
        <div key={s.code} className="card" style={{ flexDirection: "row", alignItems: "center", gap: 12, padding: 14 }}>
          <div className="grow"><span className="b" style={{ lineHeight: 1.35 }}>{s.name}</span><span className="muted">{money(s.price)} IDR</span></div>
          <button className="btn gold-line" disabled={sent.has(s.code)} onClick={() => order(s.code)}>{sent.has(s.code) ? "Отправлено" : "Заказать"}</button>
        </div>
      ))}
      <span className="small" style={{ paddingTop: 6 }}>После нажатия «Заказать» менеджер получает заявку и связывается с вами.</span>
    </main>
  );
}
