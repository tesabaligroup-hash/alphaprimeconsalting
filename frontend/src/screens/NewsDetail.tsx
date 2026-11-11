import { type NewsItem } from "../api";
import { openExternal } from "../tg";
import { BackTop } from "../ui";
import { InterestButton } from "./common";

export default function NewsDetail({ item }: { item: NewsItem }) {
  return (
    <main className="screen" style={{ gap: 16, paddingTop: 0 }}>
      <BackTop kicker={item.kind === "partner" ? item.partner_name || "Партнёры" : "Новости Alpha Prime"} title={item.title} />
      {item.image && (
        <img src={item.image} alt="" style={{ width: "100%", aspectRatio: "2 / 1", objectFit: "cover", borderRadius: 18, display: "block" }} />
      )}
      {item.cta && <InterestButton id={item.id} />}
      {item.body && <p style={{ whiteSpace: "pre-line", lineHeight: 1.55, margin: 0 }}>{item.body}</p>}
      {item.link && <button className="btn line block" onClick={() => openExternal(item.link!)}>Открыть ссылку</button>}
    </main>
  );
}
