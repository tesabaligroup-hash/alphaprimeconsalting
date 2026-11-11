import { openDocument, type Service } from "../api";
import { dateNum, dateTime, money } from "../format";
import { ICheck, IDownload } from "../icons";
import { openExternal } from "../tg";
import { BackTop, ErrorBox, Loading, useApp, useLoad } from "../ui";

type Detail = { service: Service; files: { uuid: string; name: string; created_at: string | null }[] };

export default function ServiceDetail({ id }: { id: number }) {
  const { me, toast } = useApp();
  const { data, error, reload } = useLoad<Detail>(`/api/services/${id}`);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const s = data.service;
  const wa = me?.company.whatsapp;
  const paidPct = s.price && s.paid != null ? Math.min(100, Math.round((s.paid / s.price) * 100)) : null;
  return (
    <>
      <BackTop kicker="Моя услуга" title={s.title} sub={[s.code, s.person].filter(Boolean).join(" · ")} />
      <main className="screen">
        <section className="grid3" aria-label="Ключевые даты">
          {[["Старт", s.started_at], [s.valid_until ? "Выдана" : "Готовность ~", s.valid_until ? s.issued_at : s.expected_at], ["Действует до", s.valid_until]].map(([l, v]) => (
            <div key={l} style={{ background: "#FBF7EC", borderRadius: 14, padding: 12, display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ fontSize: 11, color: "#5E5849" }}>{l}</span><span className="b">{dateNum(v)}</span>
            </div>
          ))}
        </section>

        <section className="section">
          <h2 className="h2">Этапы</h2>
          <ol className="steps">
            {s.steps.map((st, i) => {
              const last = i === s.steps.length - 1;
              const isPay = st.title === "Оплата" && st.state === "current" && s.remaining;
              return (
                <li key={i}>
                  <div className="rail">
                    <span className={`node ${st.state}`}>{st.state === "done" && <ICheck color="#fff" />}</span>
                    {!last && <span className={`line${st.state === "done" ? " done" : ""}`} />}
                  </div>
                  <div className="txt" style={last ? { paddingBottom: 0 } : undefined}>
                    <span style={{ fontWeight: st.state === "todo" ? 600 : 700, fontSize: 15, color: st.state === "current" ? "#7A5C17" : st.state === "todo" ? "#6B6556" : undefined }}>
                      {st.title}{st.state === "current" ? " — сейчас" : ""}
                    </span>
                    <span style={{ fontSize: 13, color: isPay ? "#9A4A12" : "#5E5849", fontWeight: isPay ? 600 : 400 }}>
                      {isPay ? `Внесено ${money(s.paid)} · осталось ${money(s.remaining)}` : st.at ? dateTime(st.at) : st.state === "todo" && last && s.expected_at ? `~ ${dateNum(s.expected_at)}` : ""}
                    </span>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>

        {s.price > 0 && (
          <section className="card">
            <h2 className="h2" style={{ fontSize: 22 }}>Оплата</h2>
            <div className="card-row"><span className="muted" style={{ fontSize: 14 }}>Стоимость</span><span className="b">{money(s.price)} IDR</span></div>
            {s.paid != null && <div className="card-row"><span className="muted" style={{ fontSize: 14 }}>Оплачено</span><span className="b">{money(s.paid)} IDR</span></div>}
            {paidPct != null && <div className="bar"><div style={{ width: `${paidPct}%` }} /></div>}
            {s.remaining ? (
              <>
                <div className="card-row" style={{ padding: "12px 14px", borderRadius: 12, background: "#FCEEE3", color: "#9A4A12" }}>
                  <span className="b">Осталось доплатить</span><span style={{ fontWeight: 800, fontSize: 16 }}>{money(s.remaining)} IDR</span>
                </div>
                {wa && <button className="btn" onClick={() => openExternal(`https://wa.me/${wa}?text=${encodeURIComponent(`Здравствуйте! Пришлите реквизиты для доплаты по услуге ${s.title}`)}`)}>Получить реквизиты для доплаты</button>}
              </>
            ) : s.paid != null && s.paid >= s.price ? <span className="b" style={{ color: "#3D6B2E" }}>Оплачено полностью</span> : null}
          </section>
        )}

        <section className="section">
          <h2 className="h2" style={{ fontSize: 22 }}>Файлы по услуге</h2>
          {data.files.length === 0 && <div className="card muted" style={{ borderStyle: "dashed" }}>Готовые документы появятся здесь, как только будут готовы.</div>}
          {data.files.map((f) => (
            <button key={f.uuid} className="card" onClick={() => openDocument(s.lead_id, f.uuid).catch((e) => toast(e.message))}
              style={{ flexDirection: "row", alignItems: "center" }} aria-label={`Скачать ${f.name}`}>
              <div className="grow"><span className="b">{f.name}</span>{f.created_at && <span className="small">{dateNum(f.created_at)}</span>}</div>
              <IDownload />
            </button>
          ))}
        </section>

        {wa && <button className="btn line" onClick={() => openExternal(`https://wa.me/${wa}`)}>Написать менеджеру</button>}
      </main>
    </>
  );
}
