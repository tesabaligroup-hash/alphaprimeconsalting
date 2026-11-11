import { useState } from "react";
import { type NewsItem, type Service } from "../api";
import { dateNum, money } from "../format";
import { tg, haptic, openExternal } from "../tg";
import { useApp } from "../ui";

export function ServiceCardView({ s }: { s: Service }) {
  const { go } = useApp();
  const total = s.steps.length || 4;
  const done = s.steps.filter((x) => x.state === "done").length;
  const showProgress = s.badge_tone === "warn" || s.badge_tone === "info";
  const current = s.steps.find((x) => x.state === "current");
  return (
    <button className="card" onClick={() => go({ name: "service", id: s.lead_id })}>
      <div className="card-row">
        <span className="b" style={{ fontSize: 15 }}>{s.title}{s.person ? ` · ${s.person}` : ""}</span>
        <span className={`badge ${s.badge_tone}`}>{s.badge}</span>
      </div>
      {showProgress ? (
        <>
          <div className="bar"><div style={{ width: `${Math.max(8, (done / total) * 100)}%` }} /></div>
          <div className="card-row muted">
            <span>Этап {Math.min(done + 1, total)} из {total}{current ? ` · ${current.title}` : ""}</span>
            {s.remaining ? <span>Доплата {money(s.remaining)}</span> : s.expected_at ? <span>~ {dateNum(s.expected_at)}</span> : null}
          </div>
        </>
      ) : (
        <div className="muted">{s.valid_until ? `До ${dateNum(s.valid_until)}` : s.expected_at ? `Срок: ${dateNum(s.expected_at)}` : "Подробнее"}</div>
      )}
    </button>
  );
}

export function LinkPhoneCard() {
  const { me, reloadMe, toast } = useApp();
  const [busy, setBusy] = useState(false);
  if (!me || me.linked) return null;
  const share = () => {
    if (tg?.requestContact) {
      setBusy(true);
      tg.requestContact((ok) => {
        setBusy(false);
        if (ok) { haptic(); toast("Спасибо! Ищем ваши услуги…"); setTimeout(reloadMe, 2500); setTimeout(reloadMe, 6000); }
      });
    } else {
      openExternal(`https://t.me/${me.company.bot_username}`);
    }
  };
  return (
    <section className="card cream">
      <span className="serif" style={{ fontSize: 22 }}>{me.has_phone ? "Подключаем ваши услуги" : "Подключите личный кабинет"}</span>
      <span className="small" style={{ fontSize: 14 }}>
        {me.has_phone
          ? "Номер получили. Если услуги не появились — менеджер подключит их вручную в течение рабочего дня."
          : "Поделитесь номером телефона — мы найдём ваши визы, KITAS и документы."}
      </span>
      {!me.has_phone && <button className="btn" disabled={busy} onClick={share} style={{ alignSelf: "flex-start" }}>Поделиться номером</button>}
    </section>
  );
}

export function openNews(n: NewsItem) {
  if (n.link) openExternal(n.link);
}
