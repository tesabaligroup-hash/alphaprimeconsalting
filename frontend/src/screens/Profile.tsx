import { useState } from "react";
import { api, type PartnerData } from "../api";
import { haptic, openExternal } from "../tg";
import { useApp, useLoad } from "../ui";
import { LinkPhoneCard } from "./common";

export default function Profile() {
  const { me, reloadMe, toast } = useApp();
  if (!me) return null;
  const set = async (patch: Record<string, unknown>) => {
    try { await api.patch("/api/profile", patch); reloadMe(); } catch (e) { toast((e as Error).message); }
  };
  return (
    <>
      <header className="top"><span className="kicker">Профиль</span><h1 className="title">{me.first_name || "Мой профиль"}</h1></header>
      <main className="screen">
        <LinkPhoneCard />
        <section className="section">
          <h2 className="h2">Уведомления</h2>
          <label className="tos"><input type="checkbox" checked={me.notify_company_offers} onChange={(e) => set({ notify_company_offers: e.target.checked })} /><span>Получать спецпредложения Alpha Prime</span></label>
          <label className="tos"><input type="checkbox" checked={me.notify_partner_offers} onChange={(e) => set({ notify_partner_offers: e.target.checked })} /><span>Получать предложения наших партнёров</span></label>
        </section>
        {me.is_partner && <PayoutDetails />}
        <section className="section">
          <h2 className="h2">Контакты</h2>
          <button className="btn line" onClick={() => openExternal(`https://wa.me/${me.company.whatsapp}`)}>Написать в WhatsApp</button>
          <span className="small">{me.company.address}</span>
        </section>
      </main>
    </>
  );
}

function PayoutDetails() {
  const { toast } = useApp();
  const { data } = useLoad<PartnerData>("/api/partner");
  const [text, setText] = useState<string | null>(null);
  const save = async () => {
    try { await api.put("/api/partner/payout-details", { details: text ?? "" }); haptic(); toast("Реквизиты сохранены"); } catch (e) { toast((e as Error).message); }
  };
  return (
    <section className="section">
      <h2 className="h2">Реквизиты для выплат</h2>
      <span className="small">Счёт в индонезийском банке на ваше имя или имя вашей компании: банк, номер счёта, имя владельца. Перед первой выплатой менеджер попросит паспорт или KTP.</span>
      <textarea className="input" aria-label="Реквизиты для выплат" value={text ?? ""} onChange={(e) => setText(e.target.value)}
        placeholder={data?.has_payout_details ? "Реквизиты сохранены. Чтобы изменить — впишите новые." : "BCA · 1234567890 · ANNA DIKINA"} maxLength={2000} />
      <button className="btn" disabled={!text?.trim()} onClick={save}>Сохранить реквизиты</button>
    </section>
  );
}
