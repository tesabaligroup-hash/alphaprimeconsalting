const MONTHS_SHORT = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];

export const money = (n: number | null | undefined) => (n ?? 0).toLocaleString("ru-RU").replace(/ /g, " ");

function parse(iso: string) {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return { y, m, d };
}

export const dateNum = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const { y, m, d } = parse(iso);
  return `${String(d).padStart(2, "0")}.${String(m).padStart(2, "0")}.${y}`;
};

export const dateLong = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const { m, d } = parse(iso);
  return `${d} ${MONTHS[m - 1]}`;
};

export const dayMonth = (iso: string) => {
  const { m, d } = parse(iso);
  return { day: String(d).padStart(2, "0"), month: MONTHS_SHORT[m - 1] };
};

export const dateTime = (iso: string | null | undefined) => {
  if (!iso) return "";
  const t = iso.slice(11, 16);
  return `${dateNum(iso)}${t && t !== "00:00" ? ", " + t : ""}`;
};

export function plural(n: number, one: string, few: string, many: string) {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  if (b === 1) return one;
  return many;
}

export const inDays = (n: number) => (n === 0 ? "сегодня" : `через ${n} ${plural(n, "день", "дня", "дней")}`);

export const initials = (name: string) =>
  name.replace("@", "").split(/\s+/).filter(Boolean).slice(0, 2).map((x) => x[0]?.toUpperCase()).join("") || "•";
