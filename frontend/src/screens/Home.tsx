import { type Home as HomeData } from "../api";
import { dayMonth, dateLong, inDays } from "../format";
import { ICal } from "../icons";
import { openExternal } from "../tg";
import { ErrorBox, Loading, useApp, useLoad } from "../ui";
import { LinkPhoneCard, ServiceCardView, openNews } from "./common";

export default function Home() {
  const { me, go } = useApp();
  const { data, error, reload } = useLoad<HomeData>("/api/home", [me?.linked]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const c = me?.company;
  return (
    <>
      <header className="top">
        <span className="kicker">Alpha Prime</span>
        <h1 className="title" style={{ fontSize: 28 }}>Добрый день{me?.first_name ? `, ${me.first_name}` : ""}</h1>
      </header>
      <main className="screen">
        <LinkPhoneCard />

        {data.dates.length > 0 && (
          <section className="dark" aria-label="Ближайшие важные даты">
            <div className="kicker" style={{ color: "#E3C77F", letterSpacing: ".08em", display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
              <ICal color="#E3C77F" /> {data.dates.length > 1 ? "Ближайшие важные даты" : "Ближайшая важная дата"}
            </div>
            <div>
              {data.dates.map((d, i) => {
                const dm = dayMonth(d.date);
                return (
                  <div className="date-row" key={i}>
                    <span className="date-num"><b>{dm.day}</b><span>{dm.month}</span></span>
                    <div className="grow"><span className="b">{d.title}</span><span className="muted" style={{ fontSize: 12 }}>{d.person} · {inDays(d.days_left)}</span></div>
                  </div>
                );
              })}
            </div>
            {data.dates.some((d) => d.kind === "expiry") && (
              <button className="btn light" style={{ alignSelf: "flex-start", minHeight: 44 }}
                onClick={() => c && openExternal(`https://wa.me/${c.whatsapp}?text=${encodeURIComponent("Здравствуйте! Хочу узнать о продлении")}`)}>
                Узнать о продлении
              </button>
            )}
          </section>
        )}

        {data.services.length > 0 && (
          <section className="section">
            <div className="section-head"><h2 className="h2">Мои услуги</h2><button className="link-btn" onClick={() => go({ name: "services", tab: "mine" })}>Все</button></div>
            {data.services.slice(0, 4).map((s) => <ServiceCardView key={s.lead_id} s={s} />)}
          </section>
        )}

        <section className="section">
          <h2 className="h2">Новости Alpha Prime</h2>
          {data.banners.length > 0 && (
            <div className="hscroll">
              {data.banners.map((b) => (
                <button key={b.id} className={`banner${b.image ? " has-img" : ""}`} style={{ width: data.banners.length > 1 ? "88%" : "100%", flex: "none", backgroundImage: b.image ? `url(${b.image})` : undefined }}
                  onClick={() => openNews(b)}>
                  <span style={{ fontWeight: 800, fontSize: 18, lineHeight: 1.25 }}>{b.title}</span>
                  {b.body && <span style={{ fontSize: 13 }}>{b.body}</span>}
                </button>
              ))}
            </div>
          )}
          {data.news.map((n) => (
            <button key={n.id} className="news-row" onClick={() => openNews(n)}>
              <div className="thumb" style={{ backgroundImage: n.image ? `url(${n.image})` : undefined }} />
              <div className="grow"><span className="muted" style={{ fontSize: 12 }}>{dateLong(n.date)}</span><span className="b" style={{ lineHeight: 1.35 }}>{n.title}</span></div>
            </button>
          ))}
          {data.banners.length + data.news.length === 0 && <p className="muted">Скоро здесь появятся новости.</p>}
        </section>

        {data.partner_news.length > 0 && (
          <section className="section">
            <h2 className="h2">От наших партнёров</h2>
            <div className="hscroll">
              {data.partner_news.map((n) => (
                <button key={n.id} className="pcard" onClick={() => openNews(n)}>
                  <div className="img" style={{ backgroundImage: n.image ? `url(${n.image})` : undefined }}>{n.image ? "" : "ПАРТНЁР ALPHA PRIME"}</div>
                  <div className="body"><span className="b">{n.partner_name}</span><span className="muted" style={{ lineHeight: 1.4 }}>{n.title}</span></div>
                </button>
              ))}
            </div>
          </section>
        )}

        <section className="card cream" style={{ borderRadius: 20, padding: 20 }}>
          <span className="serif" style={{ fontSize: 24, lineHeight: 1.15 }}>Рекомендуйте нас друзьям</span>
          <span className="small" style={{ fontSize: 14 }}>Друг получает скидку, а вы — вознаграждение за каждую оплаченную им услугу.</span>
          <button className="btn" style={{ alignSelf: "flex-start", minHeight: 44 }} onClick={() => go({ name: "partner" })}>
            {me?.is_partner ? "Партнёрский кабинет" : "Стать партнёром"}
          </button>
        </section>

        {c && (
          <section className="section">
            <h2 className="h2">Связаться с нами</h2>
            <div className="grid3">
              {c.telegram && <button className="btn line" style={{ minHeight: 44, borderColor: "#ECE4D2" }} onClick={() => openExternal(`https://t.me/${c.telegram}`)}>Telegram</button>}
              <button className="btn line" style={{ minHeight: 44, borderColor: "#ECE4D2" }} onClick={() => openExternal(`https://wa.me/${c.whatsapp}`)}>WhatsApp</button>
              <button className="btn line" style={{ minHeight: 44, borderColor: "#ECE4D2" }} onClick={() => openExternal(`https://maps.google.com/?q=${encodeURIComponent(c.address)}`)}>Офис</button>
            </div>
          </section>
        )}
      </main>
    </>
  );
}
