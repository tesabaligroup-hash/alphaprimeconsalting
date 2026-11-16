import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { api, downloadQr, type Codeword, type PartnerData } from "../api";
import { dateLong } from "../format";
import { ICopy, IDownload } from "../icons";
import { haptic, openExternal } from "../tg";
import { BackTop, ErrorBox, Loading, copyText, useApp, useLoad } from "../ui";

type Check = { word: string; ok: boolean; problems: string[] };

export default function Share() {
  const { data, error, reload } = useLoad<PartnerData>("/api/partner");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  return (
    <>
      <BackTop title="Мои ссылки и QR-коды" />
      <main className="screen" style={{ gap: 20 }}>
        {data.codewords.length ? <Words data={data} onChanged={reload} /> : <Codeword first onSaved={reload} />}
      </main>
    </>
  );
}

function Words({ data, onChanged }: { data: PartnerData; onChanged: () => void }) {
  const [sel, setSel] = useState(data.codewords[0].word);
  const [adding, setAdding] = useState(false);
  const current = data.codewords.find((c) => c.word === sel) ?? data.codewords[0];
  const canAdd = data.codewords.length < data.max_codewords;
  return (
    <>
      <section className="section">
        <span className="b" style={{ fontSize: 15 }}>Мои кодовые слова</span>
        <span className="small">У каждого слова — своя ссылка и QR-код. Все клиенты по любому слову закрепляются за вами.</span>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }} role="radiogroup" aria-label="Кодовые слова">
          {data.codewords.map((c) => <WordRow key={c.word} c={c} active={c.word === current.word} onPick={() => { setSel(c.word); setAdding(false); }} />)}
        </div>
        {adding
          ? <Codeword onSaved={(w) => { setAdding(false); if (w) setSel(w); onChanged(); }} onCancel={() => setAdding(false)} />
          : canAdd && <button className="btn gold-line" style={{ alignSelf: "flex-start" }} onClick={() => setAdding(true)}>+ Новое кодовое слово</button>}
      </section>
      {!adding && <Channels key={current.word} c={current} />}
    </>
  );
}

function WordRow({ c, active, onPick }: { c: Codeword; active: boolean; onPick: () => void }) {
  return (
    <button role="radio" aria-checked={active} onClick={onPick} className="card"
      style={{ flexDirection: "row", alignItems: "center", gap: 12, padding: "12px 14px", borderRadius: 16, textAlign: "left", cursor: "pointer",
               border: active ? "2px solid var(--gold)" : "1px solid #E8DFC9", background: active ? "var(--cream)" : "#fff" }}>
      <span style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
        <span style={{ fontWeight: 800, fontSize: 16, letterSpacing: 0.5 }}>{c.word}</span>
        <span className="small">
          {[c.label, c.created_at ? `создано ${dateLong(c.created_at)}` : null].filter(Boolean).join(" · ")}
        </span>
      </span>
      <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
        {c.main && <span className="badge info">Основное</span>}
      </span>
    </button>
  );
}

const LOCAL_RULES = [
  { text: "Не короче 6 символов", test: (w: string) => w.length >= 6 },
  { text: "Только буквы и цифры, без пробелов", test: (w: string) => /^[A-ZА-ЯЁ0-9]+$/.test(w) },
];

function Codeword({ onSaved, onCancel, first }: { onSaved: (word?: string) => void; onCancel?: () => void; first?: boolean }) {
  const { toast } = useApp();
  const [word, setWord] = useState("");
  const [label, setLabel] = useState("");
  const [check, setCheck] = useState<Check | null>(null);
  const [busy, setBusy] = useState(false);
  const w = word.replace(/\s+/g, "").toUpperCase();
  const localOk = LOCAL_RULES.every((r) => r.test(w));

  useEffect(() => {
    setCheck(null);
    if (!localOk) return;
    const t = setTimeout(() => {
      api.post<Check>("/api/partner/codeword/check", { word: w }).then(setCheck).catch(() => setCheck(null));
    }, 400);
    return () => clearTimeout(t);
  }, [w, localOk]);

  const serverProblems = (check?.problems ?? []).filter((p) => !LOCAL_RULES.some((r) => r.text === p));
  const allOk = localOk && check?.ok === true;
  const save = async () => {
    setBusy(true);
    try {
      await api.post("/api/partner/codeword", { word: w, label: label.trim() || null });
      haptic();
      toast("Кодовое слово закреплено за вами");
      onSaved(w);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card cream" style={{ gap: 12, borderRadius: 20, padding: 18 }}>
      <div className="card-row">
        <span className="b" style={{ fontSize: 15, fontWeight: 800 }}>{first ? "Ваше кодовое слово" : "Новое кодовое слово"}</span>
        {w && <span className={`badge ${allOk ? "ok" : "warn"}`}>{allOk ? "Свободно" : check === null && localOk ? "Проверяем…" : "Не подходит"}</span>}
      </div>
      <label className="field">Придумайте слово
        <input className="input big" value={word} onChange={(e) => setWord(e.target.value)} maxLength={20} autoComplete="off" autoCapitalize="characters" placeholder="ANNABALI" />
      </label>
      <label className="field">Для чего это слово — видите только вы
        <input className="input" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={64} placeholder="Например: Top Gym, Instagram, друзья" />
      </label>
      <ul className="rules">
        {LOCAL_RULES.map((r) => {
          const ok = r.test(w);
          return <li key={r.text} style={{ color: ok ? "#3D6B2E" : "#9A4A12" }}><span aria-hidden="true">{ok ? "✓" : "✗"}</span>{r.text}</li>;
        })}
        <li style={{ color: serverProblems.length ? "#9A4A12" : check?.ok ? "#3D6B2E" : "#5E5849" }}>
          <span aria-hidden="true">{serverProblems.length ? "✗" : check?.ok ? "✓" : "•"}</span>
          {serverProblems[0] ?? "Не общее слово (виза, KITAS, Бали…) и никем не занято"}
        </li>
      </ul>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn" style={{ flex: 1 }} disabled={!allOk || busy} onClick={save}>Закрепить слово за мной</button>
        {onCancel && <button className="btn gold-line" style={{ minHeight: 48 }} onClick={onCancel}>Отмена</button>}
      </div>
      <span className="small">Друг пишет нам «Я от {w || "ВАШЕГО СЛОВА"}» в любой мессенджер — и закрепляется за вами. Слово остаётся за вами навсегда, удалить или сменить его можно только через менеджера.</span>
    </section>
  );
}

function Channels({ c }: { c: Codeword }) {
  const { toast } = useApp();
  const links = c.links;
  const [ch, setCh] = useState<"tg" | "wa" | "ig">("wa");
  const [qr, setQr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const share = {
    tg: { label: "Telegram", link: links.tg, hint: `QR открывает Telegram менеджеров Alpha Prime с готовым сообщением «${links.text}».`, cta: "Отправить ссылку в Telegram" },
    wa: { label: "WhatsApp", link: links.wa, hint: `QR открывает WhatsApp менеджеров Alpha Prime с готовым сообщением «${links.text}».`, cta: "Отправить ссылку в WhatsApp" },
    ig: { label: "Instagram", link: links.ig, hint: `QR открывает Direct Alpha Prime в Instagram. Готовый текст Instagram не подставляет — друг пишет «${links.text}» сам.`, cta: "Скопировать текст для Direct" },
  }[ch];

  useEffect(() => {
    if (!share.link) { setQr(null); return; }
    QRCode.toDataURL(share.link, { margin: 1, width: 360, color: { dark: "#1C1A16", light: "#FFFFFF" } }).then(setQr).catch(() => setQr(null));
  }, [share.link, ch]);

  const copy = async (text: string, what: string) => toast((await copyText(text)) ? `${what} скопировано` : "Не удалось скопировать");
  const send = () => {
    const msg = `Рекомендую Alpha Prime — визы, KITAS и компании на Бали. Напиши им «${links.text}», получишь скидку.`;
    if (ch === "tg") openExternal(`https://t.me/share/url?url=${encodeURIComponent(links.tg)}&text=${encodeURIComponent(msg)}`);
    else if (ch === "wa") openExternal(`https://wa.me/?text=${encodeURIComponent(`${msg}\n${links.wa}`)}`);
    else copy(msg, "Текст");
  };
  const download = async () => {
    setBusy(true);
    try {
      await downloadQr(c.word, ch);
      haptic();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="section">
      <div className="card-row">
        <span id="share-ch" className="b" style={{ fontSize: 15 }}>QR-код для «{c.word}»</span>
        <button className="icon-btn" style={{ width: 40, height: 40, border: "1px solid #E8DFC9" }} aria-label="Скопировать кодовое слово" onClick={() => copy(links.text, "Кодовое слово")}><ICopy /></button>
      </div>
      <span className="small">Куда друг будет писать?</span>
      <div className="choice3" role="radiogroup" aria-labelledby="share-ch">
        {(["wa", "tg", "ig"] as const).map((id) => (
          <button key={id} role="radio" aria-checked={ch === id} className="chip" onClick={() => setCh(id)}>{{ tg: "Telegram", wa: "WhatsApp", ig: "Instagram" }[id]}</button>
        ))}
      </div>
      <div className="card" style={{ alignItems: "center", gap: 14, borderRadius: 20, padding: 20 }}>
        {qr ? <img className="qr" src={qr} alt={`QR-код: ${share.label}, слово ${c.word}`} /> : <div className="qr" style={{ display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center" }} ><span className="small">Instagram не подключён</span></div>}
        <span className="small" style={{ textAlign: "center", fontSize: 13 }}>{share.hint}</span>
        {share.link && (
          <button className="btn gold block" disabled={busy} onClick={download}><IDownload /> {busy ? "Готовим файл…" : "Скачать QR-код"}</button>
        )}
        {share.link && (
          <div className="copy-row"><span>{share.link.replace("https://", "")}</span><button className="icon-btn" aria-label="Скопировать ссылку" onClick={() => copy(share.link!, "Ссылка")}><ICopy /></button></div>
        )}
        <button className="btn block" onClick={send}>{share.cta}</button>
        {share.link && <span className="small" style={{ textAlign: "center" }}>Файл подходит для печати: QR, «{links.text}» и логотип Alpha Prime.</span>}
      </div>
    </section>
  );
}
