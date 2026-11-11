import { useState } from "react";
import { api, type PartnerData } from "../api";
import { dateLong, money, plural } from "../format";
import { IAddUser, IQr } from "../icons";
import { haptic } from "../tg";
import { Accordion, ErrorBox, Loading, useApp, useLoad } from "../ui";

export default function Partner() {
  const { me } = useApp();
  if (!me) return <Loading />;
  return me.is_partner ? <Dashboard /> : <Join />;
}

function Join() {
  const { reloadMe, toast } = useApp();
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const join = async () => {
    setBusy(true);
    try {
      await api.post("/api/partner/join", { accept_terms: true });
      haptic();
      reloadMe();
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <header className="top"><span className="kicker">Партнёрская программа</span><h1 className="title">Рекомендуйте Alpha Prime</h1></header>
      <main className="screen">
        <section className="dark">
          <span className="serif" style={{ fontSize: 24, color: "#E3C77F", lineHeight: 1.2 }}>Друг получает скидку, вы — вознаграждение</span>
          <span className="muted" style={{ fontSize: 14, lineHeight: 1.5 }}>За каждую услугу, которую ваш друг закажет и оплатит в течение 12 месяцев: визы, KITAS, продления, компании, бухгалтерия.</span>
        </section>
        <section className="section" style={{ gap: 10, fontSize: 14, lineHeight: 1.5 }}>
          <h2 className="h2">Как это работает</h2>
          <div className="legend"><i style={{ background: "#C9A24B" }} /><span>Придумайте своё кодовое слово и получите личную ссылку и QR-код.</span></div>
          <div className="legend"><i style={{ background: "#C9A24B" }} /><span>Друг пишет нам «Я от вашего слова» или приходит по ссылке — и закрепляется за вами.</span></div>
          <div className="legend"><i style={{ background: "#C9A24B" }} /><span>Когда друг оплатит услугу и получит результат, вознаграждение станет доступно к выплате. Выплаты — 10 и 25 числа.</span></div>
          <div className="note-warn">Вознаграждение — только за друзей, которые заказали и оплатили услугу. За саму рекомендацию ничего не начисляется.</div>
        </section>
        <label className="tos">
          <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
          <span>Я принимаю условия партнёрской программы: нельзя рекомендовать себя, обещать сроки или цены не из прайса, принимать деньги от клиента от имени Alpha Prime.</span>
        </label>
        <button className="btn" disabled={!agree || busy} onClick={join}>Стать партнёром</button>
      </main>
    </>
  );
}

function Dashboard() {
  const { go } = useApp();
  const { data, error, reload } = useLoad<PartnerData>("/api/partner");
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const { balance: b, bonuses: bo, rules } = data;
  const pct = (have: number, need: number) => `${Math.min(100, Math.round((have / need) * 100))}%`;
  const left = bo.top_month.need - bo.top_month.have;
  return (
    <>
      <header className="top">
        <div className="top-row">
          <div><span className="kicker">Партнёрка{data.partner.gold ? " · Gold" : ""}</span><h1 className="title">Ваш баланс</h1></div>
          {data.partner.codeword && <span className="badge muted" style={{ border: "1px solid #E8DFC9", background: "#fff", padding: "6px 12px" }}>{data.partner.codeword}</span>}
        </div>
      </header>
      <main className="screen">
        <section className="dark">
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className="muted" style={{ fontSize: 12 }}>К выплате</span>
            <span style={{ fontSize: 34, fontWeight: 800, lineHeight: 1, color: "#E3C77F" }}>{money(b.to_payout)} <span style={{ fontSize: 15, fontWeight: 700 }}>IDR</span></span>
            <span className="muted">Ближайшая выплата — {dateLong(b.next_payout)}</span>
          </div>
          <div style={{ height: 1, background: "#3A362E" }} />
          <div className="grid2">
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}><span className="muted" style={{ fontSize: 12 }}>Ожидается</span><span className="b" style={{ fontSize: 16 }}>{money(b.expected)}</span></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}><span className="muted" style={{ fontSize: 12 }}>Выплачено всего</span><span className="b" style={{ fontSize: 16 }}>{money(b.paid_total)}</span></div>
          </div>
        </section>

        <div style={{ marginTop: -12 }}>
          <Accordion title="Как считается баланс?" open remember="partner-balance">
            <div className="note-warn">Вознаграждение начисляется только за друзей, которые заказали и оплатили услугу Alpha Prime. За саму рекомендацию, без заказа и оплаты, ничего не начисляется.</div>
            <div className="legend"><i style={{ background: "#B5AE9E" }} /><span><b>Ожидается</b> — друг заказал услугу, но ещё не оплатил её полностью или услуга в работе. Сумма показана заранее.</span></div>
            <div className="legend"><i style={{ background: "#3D6B2E" }} /><span><b>К выплате</b> — друг оплатил 100%, результат выдан и прошло {rules.hold_days} {plural(rules.hold_days, "день", "дня", "дней")} проверки (для Gold — {rules.hold_days_gold}).</span></div>
            <div className="legend"><i style={{ background: "#C9A24B" }} /><span><b>Выплачено</b> — деньги отправлены 10 или 25 числа.</span></div>
            <span className="muted">Выплаты от {money(rules.min_payout)} IDR, меньшая сумма копится и не сгорает. При возврате денег клиенту сумма вычитается из следующих начислений.</span>
          </Accordion>
        </div>

        <section className="grid2">
          <button className="btn gold" onClick={() => go({ name: "share" })}><IQr /> Моя ссылка и код</button>
          <button className="btn line" onClick={() => go({ name: "referrals" })}><IAddUser /> Добавить друга</button>
        </section>

        <section className="section">
          <h2 className="h2">Бонусы и статусы</h2>
          <div className="card">
            <div className="card-row"><span className="b">Топ месяца · {money(bo.top_month.amount)}</span><span className="muted">{bo.top_month.have} из {bo.top_month.need}</span></div>
            <div className="bar thick"><div style={{ width: pct(bo.top_month.have, bo.top_month.need) }} /></div>
            <span className="small">{left > 0 ? `Ещё ${left} ${plural(left, "оплативший клиент", "оплативших клиента", "оплативших клиентов")} в этом месяце` : "Порог месяца выполнен 🎉"}</span>
          </div>
          <div className="card">
            <div className="card-row"><span className="b">Статус Gold · {money(bo.gold.amount)}</span><span className="muted">{bo.gold.have} из {bo.gold.need}</span></div>
            <div className="bar thick"><div style={{ width: pct(bo.gold.have, bo.gold.need), background: "#1C1A16" }} /></div>
            <span className="small">До конца квартала — {bo.gold.days_left} {plural(bo.gold.days_left, "день", "дня", "дней")}</span>
          </div>
          <Accordion title="Как получить бонус и Gold?">
            <div><b>Топ месяца — {money(bo.top_month.amount)} IDR</b><br />Если за календарный месяц {bo.top_month.need} и больше ваших друзей полностью оплатили услуги. Выплата — 25 числа следующего месяца.</div>
            <div><b>Статус Gold — {money(bo.gold.amount)} IDR за квартал</b><br />Если за квартал оплатили {bo.gold.need} и больше друзей. Gold действует весь следующий квартал: выплаты через {rules.hold_days_gold} дня вместо {rules.hold_days}, личный менеджер, значок Gold.</div>
            <div><b>Как считаем</b><br />Считаем людей, а не услуги: друг с тремя услугами — это 1 клиент. Отмены и возвраты не учитываются. Оба бонуса можно получить одновременно.</div>
          </Accordion>
        </section>

        <section className="section">
          <div className="section-head"><h2 className="h2">Ваши друзья</h2><button className="link-btn" onClick={() => go({ name: "referrals" })}>Все</button></div>
          {data.friends.length === 0 ? (
            <div className="card muted">Здесь появятся друзья, которые заказали услугу по вашей рекомендации.</div>
          ) : (
            <div className="card" style={{ padding: "0 16px", gap: 0 }}>
              {data.friends.slice(0, 5).map((f, i) => <FriendRow key={i} f={f} />)}
            </div>
          )}
          <span className="small">Сумма — ваше вознаграждение за друга, в IDR.</span>
        </section>

        {!data.has_payout_details && (
          <button className="card cream" onClick={() => go({ name: "profile" })}>
            <span className="b">Укажите реквизиты для выплат</span>
            <span className="small">Без них мы не сможем перевести вознаграждение. Это можно сделать в профиле.</span>
          </button>
        )}
      </main>
    </>
  );
}

export function FriendRow({ f }: { f: PartnerData["friends"][number] }) {
  const tone = f.status === "to_payout" || f.status === "paid" ? "#3D6B2E" : f.status === "cancelled" ? "#6B6556" : undefined;
  const label = f.status === "to_payout" && f.payout_date ? `К выплате · ${dateLong(f.payout_date)}`
    : f.status === "confirmed" && f.payout_date ? `Подтверждено · выплата ${dateLong(f.payout_date)}`
    : f.status === "cancelled" && f.cancel_reason ? `Отменено · ${f.cancel_reason}` : f.status_label;
  return (
    <div className="list-row">
      <div className="grow"><span className="b">{f.name}{f.level === 2 ? " · 2-й уровень" : ""}</span><span style={{ fontSize: 12, color: tone ?? "#5E5849", fontWeight: tone ? 600 : 400 }}>{label}</span></div>
      <span className="amount" style={{ color: tone, textDecoration: f.status === "cancelled" ? "line-through" : undefined }}>{money(f.amount)}</span>
    </div>
  );
}
