import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { api, type PartnerData } from "../api";
import { ICopy } from "../icons";
import { haptic, openExternal } from "../tg";
import { BackTop, ErrorBox, Loading, copyText, useApp, useLoad } from "../ui";

type Check = { word: string; ok: boolean; problems: string[] };

export default function Share() {
  const { data, error, reload } = useLoad<PartnerData>("/api/partner");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  return (
    <>
      <BackTop title="Моя ссылка и код" />
      <main className="screen" style={{ gap: 20 }}>
        {data.partner.codeword && data.links ? <Channels word={data.partner.codeword} links={data.links} /> : <Codeword onSaved={reload} />}
      </main>
    </>
  );
}

const LOCAL_RULES = [
  { text: "Не короче 6 символов", test: (w: string) => w.length >= 6 },
  { text: "Только буквы и цифры, без пробелов", test: (w: string) => /^[A-ZА-ЯЁ0-9]+$/.test(w) },
];

function Codeword({ onSaved }: { onSaved: () => void }) {
  const { toast } = useApp();
  const [word, setWord] = useState("");
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
      await api.post("/api/partner/codeword", { word: w });
      haptic();
      toast("Кодовое слово закреплено за вами");
      onSaved();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="card cream" style={{ gap: 12, borderRadius: 20, padding: 18 }}>
      <div className="card-row">
        <span className="b" style={{ fontSize: 15, fontWeight: 800 }}>Ваше кодовое слово</span>
        {w && <span className={`badge ${allOk ? "ok" : "warn"}`}>{allOk ? "Свободно" : check === null && localOk ? "Проверяем…" : "Не подходит"}</span>}
      </div>
      <label className="field">Придумайте слово
        <input className="input big" value={word} onChange={(e) => setWord(e.target.value)} maxLength={20} autoComplete="off" autoCapitalize="characters" placeholder="ANNABALI" />
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
      <button className="btn" disabled={!allOk || busy} onClick={save}>Закрепить слово за мной</button>
      <span className="small">Друг пишет нам «Я от {w || "ВАШЕГО СЛОВА"}» в любой мессенджер — и закрепляется за вами. После закрепления сменить слово можно только через менеджера.</span>
    </section>
  );
}

function Channels({ word, links }: { word: string; links: NonNullable<PartnerData["links"]> }) {
  const { toast } = useApp();
  const [ch, setCh] = useState<"tg" | "wa" | "ig">("tg");
  const [qr, setQr] = useState<string | null>(null);
  const share = {
    tg: { label: "Telegram", link: links.tg, hint: "QR открывает чат с нашим ботом — друг закрепляется за вами автоматически.", cta: "Отправить ссылку в Telegram" },
    wa: { label: "WhatsApp", link: links.wa, hint: `QR открывает WhatsApp Alpha Prime с готовым сообщением «${links.text}».`, cta: "Отправить ссылку в WhatsApp" },
    ig: { label: "Instagram", link: links.ig, hint: `В Instagram ссылки не закрепляют автоматически: друг должен написать в Direct «${links.text}».`, cta: "Скопировать текст для Direct" },
  }[ch];

  useEffect(() => {
    if (!share.link) { setQr(null); return; }
    QRCode.toDataURL(share.link, { margin: 1, width: 360, color: { dark: "#1C1A16", light: "#FFFFFF" } }).then(setQr).catch(() => setQr(null));
  }, [share.link]);

  const copy = async (text: string, what: string) => toast((await copyText(text)) ? `${what} скопировано` : "Не удалось скопировать");
  const send = () => {
    const msg = `Рекомендую Alpha Prime — визы, KITAS и компании на Бали. Напиши им «${links.text}», получишь скидку.`;
    if (ch === "tg") openExternal(`https://t.me/share/url?url=${encodeURIComponent(links.tg)}&text=${encodeURIComponent(msg)}`);
    else if (ch === "wa") openExternal(`https://wa.me/?text=${encodeURIComponent(`${msg}\n${links.wa}`)}`);
    else copy(msg, "Текст");
  };

  return (
    <>
      <section className="card cream" style={{ gap: 10, borderRadius: 20, padding: 18 }}>
        <div className="card-row"><span className="b" style={{ fontSize: 15, fontWeight: 800 }}>Ваше кодовое слово</span><span className="badge ok">Закреплено</span></div>
        <div style={{ display: "flex", gap: 8 }}>
          <span className="input big" style={{ flex: 1, display: "flex", alignItems: "center" }}>{word}</span>
          <button className="icon-btn" style={{ width: 52, height: 52, border: "1px solid #E8DFC9" }} aria-label="Скопировать кодовое слово" onClick={() => copy(links.text, "Кодовое слово")}><ICopy /></button>
        </div>
        <span className="small">Друг пишет нам «{links.text}» в любой мессенджер — и закрепляется за вами. Сменить слово можно через менеджера.</span>
      </section>

      <section className="section">
        <span id="share-ch" className="b" style={{ fontSize: 15 }}>Куда друг будет писать?</span>
        <div className="choice3" role="radiogroup" aria-labelledby="share-ch">
          {(["tg", "wa", "ig"] as const).map((id) => (
            <button key={id} role="radio" aria-checked={ch === id} className="chip" onClick={() => setCh(id)}>{{ tg: "Telegram", wa: "WhatsApp", ig: "Instagram" }[id]}</button>
          ))}
        </div>
        <div className="card" style={{ alignItems: "center", gap: 14, borderRadius: 20, padding: 20 }}>
          {qr ? <img className="qr" src={qr} alt={`QR-код: ${share.label}`} /> : <div className="qr" style={{ display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center" }} ><span className="small">Для Instagram QR не нужен — друг пишет слово в Direct</span></div>}
          <span className="small" style={{ textAlign: "center", fontSize: 13 }}>{share.hint}</span>
          {share.link && (
            <div className="copy-row"><span>{share.link.replace("https://", "")}</span><button className="icon-btn" aria-label="Скопировать ссылку" onClick={() => copy(share.link!, "Ссылка")}><ICopy /></button></div>
          )}
          <button className="btn block" onClick={send}>{share.cta}</button>
        </div>
      </section>
    </>
  );
}
