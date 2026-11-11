import { tg } from "./tg";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (tg?.initData) headers["X-Telegram-Init-Data"] = tg.initData;
  else headers["X-Dev-User"] = "1"; // работает только когда сервер в режиме разработки
  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (!res.ok) {
    let msg = "Что-то пошло не так. Попробуйте ещё раз.";
    try {
      const data = await res.json();
      if (typeof data.detail === "string") msg = data.detail;
    } catch {
      /* пусто */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json();
}

export const api = {
  get: <T,>(p: string) => request<T>("GET", p),
  post: <T,>(p: string, b?: unknown) => request<T>("POST", p, b),
  put: <T,>(p: string, b?: unknown) => request<T>("PUT", p, b),
  patch: <T,>(p: string, b?: unknown) => request<T>("PATCH", p, b),
};

/** Получает временную ссылку на файл и открывает/скачивает его средствами Telegram. */
export async function openDocument(leadId: number, uuid: string) {
  const { url, name } = await request<{ url: string; name: string }>("POST", `/api/documents/${leadId}/${uuid}/link`);
  const w = tg as unknown as { downloadFile?: (p: { url: string; file_name: string }) => void } | undefined;
  if (w?.downloadFile) w.downloadFile({ url, file_name: name });
  else if (tg) tg.openLink(url);
  else window.open(url, "_blank", "noopener");
}

// ---------- Типы ответов ----------
export type Step = { title: string; state: "done" | "current" | "todo"; at: string | null };
export type Service = {
  lead_id: number; title: string; code: string | null; person: string; badge: string;
  badge_tone: "warn" | "ok" | "info" | "muted"; archived: boolean; step_index: number; steps: Step[];
  price: number; paid: number | null; remaining: number | null; started_at: string | null;
  expected_at: string | null; issued_at: string | null; valid_until: string | null;
};
export type ImportantDate = { date: string; title: string; person: string; lead_id: number | null; days_left: number; kind: string };
export type NewsItem = { id: number; kind: string; is_banner: boolean; title: string; body: string | null; partner_name: string | null; image: string | null; link: string | null; date: string | null };
export type Me = {
  first_name: string | null; linked: boolean; has_phone: boolean; is_partner: boolean; language: string;
  notify_partner_offers: boolean; notify_company_offers: boolean;
  company: { whatsapp: string; telegram: string; instagram: string; address: string; maps_query: string; bot_username: string };
};
export type Home = { dates: ImportantDate[]; services: Service[]; banners: NewsItem[]; news: NewsItem[]; partner_news: NewsItem[] };
export type Catalog = { categories: { id: string; label: string; items: { code: string; name: string; price: number }[] }[] };
export type Friend = { name: string; status: string; status_label: string; amount: number; level: number; payout_date: string | null; cancel_reason: string | null };
export type ReferralItem = { id: number; name: string; status: string; status_label: string; reject_reason: string | null; channel: string; expires_at: string | null };
export type PartnerData = {
  partner: { name: string; codeword: string | null; kind: string; plan: string; gold: boolean; gold_until: string | null };
  balance: { to_payout: number; expected: number; paid_total: number; next_payout: string; min_payout: number };
  bonuses: { top_month: { have: number; need: number; amount: number }; gold: { have: number; need: number; amount: number; days_left: number } };
  rules: { hold_days: number; hold_days_gold: number; min_payout: number };
  friends: Friend[]; referrals: ReferralItem[];
  links: { tg: string; wa: string; ig: string | null; text: string } | null;
  has_payout_details: boolean;
};
