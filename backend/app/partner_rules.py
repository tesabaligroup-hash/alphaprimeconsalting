"""Правила партнёрской программы (ТЗ «Партнёрская программа Alpha Prime», 11.11.2026).

Здесь только чистые функции без базы данных — их легко проверить тестами.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .tariffs import Tariff

# Значения по умолчанию. Админка может переопределить их (таблица program_settings).
DEFAULTS: dict = {
    "discount_pct": 0.05,  # скидка клиенту, доля маржи
    "plan_a_pct": 0.15,  # план A «Друзья» — партнёру
    "plan_b_l1_pct": 0.10,  # план B «Бизнес» — 1-й уровень
    "plan_b_l2_pct": 0.05,  # план B — 2-й уровень
    "discount_step": 5000,  # скидка округляется вниз до 5 000
    "payout_step": 1000,  # выплаты округляются вниз до 1 000
    "min_payout": 300_000,
    "hold_days": 7,
    "hold_days_gold": 3,
    "referral_days": 90,  # рекомендация действует 90 дней без оплаты
    "attach_months": 12,  # после первой оплаты клиент закреплён на 12 месяцев
    "level2_months": 24,
    "codeword_min_len": 6,
    "top_month_threshold": 11,
    "top_month_bonus": 1_500_000,
    "gold_threshold": 10,
    "gold_bonus": 1_000_000,
    "bonus_fund": 5_000_000,
}

# Базовый стоп-лист кодовых слов. Админка может добавлять свои слова.
BASE_STOP_WORDS = {
    "VISA", "VIZA", "ВИЗА", "VISAS", "ВИЗЫ", "KITAS", "КИТАС", "BALI", "БАЛИ", "INDONESIA", "ИНДОНЕЗИЯ",
    "ALPHA", "PRIME", "ALPHAPRIME", "АЛЬФА", "ПРАЙМ", "АЛЬФАПРАЙМ", "PROMO", "PROMOCODE", "ПРОМО", "ПРОМОКОД",
    "SKIDKA", "СКИДКА", "DISCOUNT", "PARTNER", "ПАРТНЕР", "ПАРТНЁР", "MANAGER", "МЕНЕДЖЕР", "ADMIN", "АДМИН",
    "PRIVET", "ПРИВЕТ", "HELLO", "ЗДРАВСТВУЙТЕ", "VISABALI", "BALIVISA", "KITASBALI", "INVESTOR", "ИНВЕСТОР",
}


def floor_to(value: float, step: int) -> int:
    return int(value // step) * step


@dataclass(frozen=True)
class Payouts:
    margin: int
    discount: int
    client_price: int
    plan_a: int
    plan_b_l1: int
    plan_b_l2: int


def calc_payouts(tariff: Tariff, s: dict = DEFAULTS, deal_price: int | None = None) -> Payouts:
    """Скидка клиенту и выплаты партнёрам по услуге.

    deal_price — фактический бюджет сделки в Kommo. Если менеджер дал скидку больше
    стандартной (бюджет ниже «цены для клиента партнёра»), выплаты считаются от
    фактической маржи: бюджет − себестоимость для партнёров.
    """
    margin = tariff.price - tariff.partner_cost
    discount = floor_to(margin * s["discount_pct"], s["discount_step"])
    client_price = tariff.price - discount
    if deal_price is not None and deal_price < client_price:
        margin = max(deal_price - tariff.partner_cost, 0)
    step = s["payout_step"]
    return Payouts(
        margin=margin,
        discount=discount,
        client_price=client_price,
        plan_a=floor_to(margin * s["plan_a_pct"], step),
        plan_b_l1=floor_to(margin * s["plan_b_l1_pct"], step),
        plan_b_l2=floor_to(margin * s["plan_b_l2_pct"], step),
    )


# ---------- Кодовое слово ----------

CODEWORD_RE = re.compile(r"^[A-ZА-ЯЁ0-9]+$")


def normalize_codeword(word: str) -> str:
    return re.sub(r"\s+", "", word or "").upper()


def codeword_problems(word: str, extra_stop_words: set[str] | None = None, min_len: int = DEFAULTS["codeword_min_len"]) -> list[str]:
    """Список причин, почему слово не подходит. Пустой список — слово подходит (кроме проверки на занятость)."""
    w = normalize_codeword(word)
    problems = []
    if len(w) < min_len:
        problems.append(f"Не короче {min_len} символов")
    if not CODEWORD_RE.match(w or "-"):
        problems.append("Только буквы и цифры, без пробелов")
    stop = BASE_STOP_WORDS | {x.upper() for x in (extra_stop_words or set())}
    if w in stop or any(w.startswith(s) and len(w) - len(s) <= 2 for s in stop if len(s) >= 4):
        # «VISA1», «KITAS22» — тоже общее слово с цифрами
        problems.append("Не общее слово (виза, KITAS, Бали, Alpha Prime…)")
    return problems


# ---------- Даты выплат ----------

def payout_date_for(to_payout_day: date) -> date:
    """В какую дату выплатят начисление, получившее статус «К выплате» в этот день.

    с 21-го числа прошлого месяца по 5-е → 10-го; с 6-го по 20-е → 25-го.
    Перенос выходных/праздников Индонезии — на следующий рабочий день (выходные учитываем, праздники — в админке позже).
    """
    d = to_payout_day
    if d.day <= 5:
        target = d.replace(day=10)
    elif d.day <= 20:
        target = d.replace(day=25)
    else:
        nxt = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
        target = nxt.replace(day=10)
    while target.weekday() >= 5:  # суббота/воскресенье
        target += timedelta(days=1)
    return target


def next_payout_date(today: date) -> date:
    """Ближайшая дата выплаты (10 или 25) начиная с сегодня."""
    for day in (10, 25):
        if today.day <= day:
            d = today.replace(day=day)
            break
    else:
        d = (today.replace(day=1) + timedelta(days=32)).replace(day=10)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


# ---------- Статус начисления ----------

ACCRUAL_LABELS = {
    "awaiting_payment": "Ожидает оплаты",
    "in_work": "В работе",
    "confirmed": "Подтверждено",
    "to_payout": "К выплате",
    "paid": "Выплачено",
    "cancelled": "Отменено",
}


def accrual_status(*, cancelled: bool, fully_paid: bool, result_issued_at: datetime | None,
                   now: datetime, gold: bool, s: dict = DEFAULTS, already_paid: bool = False) -> tuple[str, datetime | None]:
    """Статус начисления по состоянию сделки. Возвращает (статус, конец периода удержания)."""
    if already_paid:
        return "paid", None
    if cancelled:
        return "cancelled", None
    if not fully_paid:
        return "awaiting_payment", None
    if result_issued_at is None:
        return "in_work", None
    hold_until = result_issued_at + timedelta(days=s["hold_days_gold"] if gold else s["hold_days"])
    if now < hold_until:
        return "confirmed", hold_until
    return "to_payout", hold_until


def short_name(full: str | None) -> str:
    """«Мария Кузнецова» → «Мария К.»; «@olga» остаётся как есть. Партнёр не видит полных данных."""
    if not full:
        return "Клиент"
    full = full.strip()
    if full.startswith("@"):
        return full
    parts = full.split()
    if len(parts) == 1:
        return parts[0].capitalize() if parts[0].isupper() else parts[0]
    first = parts[0].capitalize() if parts[0].isupper() else parts[0]
    return f"{first} {parts[1][0].upper()}."
