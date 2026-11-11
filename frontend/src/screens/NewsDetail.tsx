import { useState } from "react";
import { api, type NewsItem } from "../api";
import { haptic, openExternal } from "../tg";
import { BackTop, useApp } from "../ui";

export default function NewsDetail({ item }: { item: NewsItem }) {
  const { toast } = useApp();
  const [state, setState] = useState<"idle" | "busy" | "sent">("idle");
  const interest = async () => {
    setState("busy");
    try {
      await api.post(`/api/news/${item.id}/interest`);
      haptic();
      setState("sent");
      toast("Заявка отправлена — менеджер напишет вам");
    } catch (e) {
      setState("idle");
      toast((e as Error).message);
    }
  };
  return (
    <main className="screen" style={{ gap: 16, paddingTop: 0 }}>
      <BackTop kicker={item.kind === "partner" ? item.partner_name || "Партнёры" : "Новости Alpha Prime"} title={item.title} />
      {item.image && (
        <img src={item.image} alt="" style={{ width: "100%", aspectRatio: "2 / 1", objectFit: "cover", borderRadius: 18, display: "block" }} />
      )}
      {item.body && <p style={{ whiteSpace: "pre-line", lineHeight: 1.55, margin: 0 }}>{item.body}</p>}
      {item.cta && (
        <button className="btn gold block" disabled={state !== "idle"} onClick={interest}>
          {state === "sent" ? "Заявка отправлена ✓" : state === "busy" ? "Отправляем…" : "Узнать подробнее"}
        </button>
      )}
      {item.cta && state === "sent" && <p className="muted" style={{ margin: 0, textAlign: "center" }}>Менеджер свяжется с вами в ближайшее время.</p>}
      {item.link && <button className="btn line block" onClick={() => openExternal(item.link!)}>Открыть ссылку</button>}
    </main>
  );
}
