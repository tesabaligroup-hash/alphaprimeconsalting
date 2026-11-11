import { useState } from "react";
import { api, type PartnerData } from "../api";
import { initials } from "../format";
import { haptic } from "../tg";
import { BackTop, ErrorBox, Loading, useApp, useLoad } from "../ui";
import { FriendRow } from "./Partner";

const CHANNELS = [
  { id: "tg", label: "Telegram", field: "Ник в Telegram", ph: "@username", type: "text" },
  { id: "wa", label: "WhatsApp", field: "Номер WhatsApp", ph: "+62 8…", type: "tel" },
  { id: "ig", label: "Instagram", field: "Ник в Instagram", ph: "@username", type: "text" },
] as const;

export default function Referrals() {
  const { toast } = useApp();
  const { data, error, reload } = useLoad<PartnerData>("/api/partner");
  const [name, setName] = useState("");
  const [ch, setCh] = useState<(typeof CHANNELS)[number]["id"]>("tg");
  const [contact, setContact] = useState("");
  const [who, setWho] = useState<"self" | "us">("self");
  const [busy, setBusy] = useState(false);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const active = CHANNELS.find((c) => c.id === ch)!;
  const paid = data.friends.filter((f) => f.status !== "cancelled" && f.status !== "awaiting_payment").length;

  const submit = async () => {
    if (!name.trim() || contact.trim().length < 3) { toast("Укажите имя и контакт друга"); return; }
    setBusy(true);
    try {
      await api.post("/api/partner/referrals", { name, channel: ch, contact, who_writes: who });
      haptic();
      toast("Отправлено! Менеджер проверит в течение 2 рабочих дней");
      setName(""); setContact("");
      reload();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <BackTop title="Мои рекомендации" sub={`${data.friends.length + data.referrals.length} друзей · ${paid} оплатили`} />
      <main className="screen" style={{ gap: 18 }}>
        <form className="card cream" onSubmit={(e) => { e.preventDefault(); submit(); }} style={{ gap: 12 }}>
          <span className="b" style={{ fontSize: 15 }}>Добавить друга</span>
          <label className="field">Имя<input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Например, Иван" maxLength={128} /></label>
          <div className="field">
            <span id="ch-label">Где с ним связаться</span>
            <div className="choice3" role="radiogroup" aria-labelledby="ch-label">
              {CHANNELS.map((c) => (
                <button type="button" key={c.id} role="radio" aria-checked={c.id === ch} className="chip" onClick={() => setCh(c.id)}>{c.label}</button>
              ))}
            </div>
          </div>
          <label className="field">{active.field}<input className="input" type={active.type} value={contact} onChange={(e) => setContact(e.target.value)} placeholder={active.ph} maxLength={128} /></label>
          <div className="field">
            <span id="who-label">Кто напишет первым?</span>
            <div role="radiogroup" aria-labelledby="who-label" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {([["self", "Друг напишет сам", "Я передал ему контакты Alpha Prime"], ["us", "Напишите ему, пожалуйста", "Менеджер свяжется с другом первым"]] as const).map(([id, t, sub]) => (
                <button type="button" key={id} role="radio" aria-checked={who === id} className="option" onClick={() => setWho(id)}>
                  <span className="dot" aria-hidden="true" />
                  <span style={{ display: "flex", flexDirection: "column", gap: 2 }}><b style={{ fontSize: 14, color: "#1C1A16" }}>{t}</b><span className="small">{sub}</span></span>
                </button>
              ))}
            </div>
          </div>
          <button className="btn" type="submit" disabled={busy}>Отправить на проверку</button>
          <span className="small">Менеджер проверит и подтвердит закрепление в течение 2 рабочих дней</span>
        </form>

        <section style={{ display: "flex", flexDirection: "column" }}>
          {data.friends.map((f, i) => <FriendRow key={`f${i}`} f={f} />)}
          {data.referrals.map((r) => (
            <div className="list-row" key={`r${r.id}`}>
              <span className="avatar grey">{initials(r.name)}</span>
              <div className="grow">
                <span className="b">{r.name}</span>
                <span style={{ fontSize: 12, color: "#5E5849" }}>{r.status === "rejected" && r.reject_reason ? `Отменено · ${r.reject_reason}` : r.status_label}</span>
              </div>
              <span className="muted">—</span>
            </div>
          ))}
          {data.friends.length + data.referrals.length === 0 && <div className="empty">Пока никого. Поделитесь ссылкой или добавьте друга вручную.</div>}
        </section>
      </main>
    </>
  );
}
