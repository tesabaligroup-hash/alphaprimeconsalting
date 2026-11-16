import { useState } from "react";
import { api, type MyVisas } from "../api";
import { dateLong, inDays } from "../format";
import { haptic } from "../tg";
import { BackTop, ErrorBox, Loading, useApp, useLoad } from "../ui";

/** «Мои визы»: человек сам вписывает визу и дату окончания — бот напомнит о продлении за 20, 15 и 7 дней. */
export default function MyVisasScreen() {
  const { toast } = useApp();
  const { data, error, reload } = useLoad<MyVisas>("/api/my-visas");
  const [state, setState] = useState<MyVisas | null>(null);
  const [type, setType] = useState("");
  const [date, setDate] = useState("");
  const [person, setPerson] = useState("");
  const [busy, setBusy] = useState(false);
  const v = state || data;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!v) return <Loading />;

  const add = async () => {
    setBusy(true);
    try {
      setState(await api.post<MyVisas>("/api/my-visas", { visa_type: type, expires_on: date, person: person || null }));
      haptic();
      setType(""); setDate(""); setPerson("");
      toast("Добавлено — напомним о продлении");
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async (id: number) => {
    try { setState(await api.del<MyVisas>(`/api/my-visas/${id}`)); } catch (e) { toast((e as Error).message); }
  };
  const today = new Date().toISOString().slice(0, 10);

  return (
    <main className="screen" style={{ gap: 16, paddingTop: 0 }}>
      <BackTop kicker="Напоминания" title="Мои визы" />
      <p className="muted" style={{ margin: 0 }}>
        Впишите визу или KITAS — свою и членов семьи. Бот напомнит о продлении за {v.reminders.join(", ")} дней до окончания.
      </p>

      {v.items.length > 0 && (
        <section className="card" style={{ gap: 0, padding: 0 }}>
          {v.items.map((x) => (
            <div key={x.id} className="date-row" style={{ padding: "12px 16px", borderBottom: "1px solid #F0EADB" }}>
              <div className="grow">
                <span className="b">{x.visa_type}</span>
                <span className="muted" style={{ fontSize: 12 }}>
                  {x.person ? `${x.person} · ` : ""}до {dateLong(x.expires_on)} · {x.days_left >= 0 ? inDays(x.days_left) : "срок прошёл"}
                </span>
              </div>
              <button className="link-btn" onClick={() => remove(x.id)} aria-label={`Удалить ${x.visa_type}`}>Удалить</button>
            </div>
          ))}
        </section>
      )}

      <section className="card" style={{ gap: 12 }}>
        <span className="b">Добавить визу</span>
        <label className="field">Какая виза
          <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">Выберите…</option>
            {v.types.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className="field">Дата окончания
          <input className="input" type="date" min={today} value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="field">Чья виза (необязательно)
          <input className="input" value={person} maxLength={80} placeholder="Оставьте пустым, если ваша. Например: муж, дочь Ава" onChange={(e) => setPerson(e.target.value)} />
        </label>
        <button className="btn gold block" disabled={busy || !type || !date} onClick={add}>{busy ? "Сохраняем…" : "Добавить и напоминать"}</button>
      </section>
    </main>
  );
}
