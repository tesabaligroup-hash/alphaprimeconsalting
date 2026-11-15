"""Прайс и партнёрские выплаты (таблица «Тарифы партнёрской программы», 15.11.2026).

price         — цена продажи клиенту;
partner_cost  — себестоимость (СЕБЕС);
partner_price — «Цена для парт.»: цена для клиента, который пришёл от партнёра (по его рекламе/рекомендации);
white_label   — цена для партнёров, которые продают нашу услугу под своим брендом;
l1            — «партнер»: фиксированная выплата партнёру 1-го уровня (тот, кто привёл клиента), одинаковая для всех;
l2            — «партнер 2ур»: выплата 2-му уровню (тот, кто привёл к нам этого партнёра — главу кафе, спортзала…).
Услуги без l1 (нет в таблице) — начисление уходит менеджеру на проверку.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Tariff:
    code: str
    name: str
    category: str  # вкладка каталога: kitas / visa / ext / co / buh / other
    price: int
    partner_cost: int
    in_catalog: bool = True  # показывать клиентам во «Всех услугах»
    monthly: bool = False  # ежемесячная услуга — начисление за каждый оплаченный период
    partner_price: int | None = None
    white_label: int | None = None
    market: int | None = None
    l1: int | None = None
    l2: int | None = None


TARIFFS: list[Tariff] = [
    Tariff('VOA', 'Виза по прилету - VoA', 'visa', 750000, 530000, partner_price=712500, white_label=640000, market=900000, l1=50000, l2=10000),
    Tariff('VOA-EXT', 'Продление визы по прилету (VoA)', 'ext', 950000, 500000, partner_price=902500, white_label=725000, market=1200000, l1=50000, l2=10000),
    Tariff('BRIDGE', 'Bridge Visa', 'visa', 3500000, 2500000, partner_price=3325000, white_label=3000000, market=4000000, l1=250000, l2=50000),
    Tariff('C1', 'Виза C1 (на 2 мес)', 'visa', 2000000, 1000000, partner_price=1900000, white_label=1500000, market=2700000, l1=200000, l2=40000),
    Tariff('C1-EXT', 'C1 (продление)', 'ext', 2500000, 1500000, partner_price=2375000, white_label=2000000, market=2800000, l1=200000, l2=40000),
    Tariff('D1-1', 'D1 - 1 год (туристическая мульти виза)', 'visa', 5000000, 3000000, partner_price=4750000, white_label=4000000, market=6500000, l1=200000, l2=40000),
    Tariff('D1-2', 'D1 - 2 года', 'visa', 8000000, 5000000, partner_price=7600000, white_label=6500000, market=10500000, l1=200000, l2=40000),
    Tariff('D1-5', 'D1 - 5 лет', 'visa', 18000000, 10000000, partner_price=17100000, white_label=14000000, market=20000000, l1=200000, l2=40000),
    Tariff('C7 (АРТИСТА)', 'С7 (A/B/C)', 'visa', 3500000, 1500000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('C18', 'C18 Work Trial', 'visa', 5500000, 3500000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('D12-1', 'Виза D12 (на 1 год)', 'visa', 7200000, 5000000, partner_price=6840000, white_label=6100000, market=7500000, l1=350000, l2=70000),
    Tariff('D12-2', 'Виза D12 (на 2 года)', 'visa', 10900000, 7000000, partner_price=10355000, white_label=8950000, market=11500000, l1=400000, l2=80000),
    Tariff('D12-EXT', 'D12 (продление без вылета)', 'ext', 5000000, 3500000, partner_price=4750000, white_label=4250000, market=7000000, l1=250000, l2=50000),
    Tariff('E28A-2-P', 'KITAS Investor (2 года)', 'kitas', 17900000, 9500000, partner_price=17005000, white_label=13700000, market=20000000, l1=1000000, l2=200000),
    Tariff('E28A-1-P', 'KITAS Investor (1 год)', 'kitas', 11900000, 7000000, partner_price=11305000, white_label=9450000, market=13500000, l1=1000000, l2=200000),
    Tariff('E31B/E-1', 'Family KITAS (1 год)', 'kitas', 11900000, 6000000, partner_price=11305000, white_label=8950000, market=13000000, l1=1000000, l2=200000),
    Tariff('E31B/E-2', 'Family KITAS (2 года)', 'kitas', 16000000, 8500000, partner_price=15200000, white_label=12250000, market=18000000, l1=1000000, l2=200000),
    Tariff('E31-EXT-1', 'Продление KITASа присоединения (на 1 год)', 'ext', 12500000, 7000000, partner_price=11875000, white_label=9750000, market=13500000, l1=1000000, l2=200000),
    Tariff('E31-EXT-2', 'Продление KITASа присоединения (на 2 года)', 'ext', 16000000, 9500000, partner_price=15200000, white_label=12750000, market=19500000, l1=1000000, l2=200000),
    Tariff('E33F', 'Пенсионный KITAS на 1 год', 'kitas', 11900000, 7000000, in_catalog=False, partner_price=11305000, white_label=9450000, market=13000000, l1=1000000, l2=200000),
    Tariff('E33F-EXT', 'Продление пенсионного KITASа на 1 год', 'ext', 12500000, 8000000, in_catalog=False, partner_price=11875000, white_label=10250000, market=13500000, l1=1000000, l2=200000),
    Tariff('STUDY-1', 'Школьный китас на 1 год', 'kitas', 13000000, 7000000, in_catalog=False),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('STUDY-2', 'Школьный китас на 2 года', 'kitas', 18000000, 9500000, in_catalog=False),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('E33G', 'KITAS удалёнщика E33G (1 год)', 'kitas', 11900000, 7000000, partner_price=11305000, white_label=9450000, market=13500000, l1=1000000, l2=200000),
    Tariff('E33G-EXT', 'Продление KITAS E33G (удалёнщика)', 'ext', 12500000, 8000000, partner_price=11875000, white_label=10250000, market=13000000, l1=1000000, l2=200000),
    Tariff('DRIVER', 'Водительские права (за 1 категорию)', 'other', 2000000, 1500000, partner_price=None, white_label=1750000, market=2500000, l1=100000, l2=20000),
    Tariff('WORK-PT-05', 'Working KITAS (6 мес)', 'kitas', 34000000, 28000000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('WORK-PT-1', 'Working KITAS (1 год)', 'kitas', 44000000, 38000000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('PMA-1', 'Регистрация компании PT PMA', 'co', 19900000, 15000000, partner_price=18905000, white_label=17450000, market=25000000, l1=1000000, l2=200000),
    Tariff('PMA-2', 'Регистрация компании PT РМА (от 50 млрд.)', 'co', 24900000, 16000000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('ADR', 'Виртуальный офис (год)', 'co', 5000000, 3000000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('PT', 'Регистрация компании PT PMDN', 'co', 13000000, 10000000, partner_price=12350000, white_label=11500000, market=15000000, l1=500000, l2=100000),
    Tariff('CHANGE-KBLI', 'Изменение данных в РМА (1 KBLI)', 'co', 1000000, 500000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('CHANGE-PMA-N', 'Изменение данных в РМА (нотариальные)', 'co', 12000000, 9000000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('COUNT-PT-1', 'Открытие расчет. счета на компанию (с KITAS)', 'co', 2500000, 1500000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('COUNT-PT-2', 'Открытие расчет. счета на компанию (без KITAS)', 'co', 3500000, 2500000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('COUNT-PT-3', 'Открытие расчет. счета на компанию + терминал', 'co', 4500000, 3500000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('BUH-M', 'Ежемесячное ведение', 'buh', 1000000, 500000, monthly=True),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('BUH-Q', 'Квартальные отчеты', 'buh', 2000000, 1000000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('BUH-Y', 'Годовой отчет', 'buh', 3000000, 2000000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('BUH-STAMP', 'Оплата штампа', 'buh', 400000, 200000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('SKTT-1', 'Получение SKTT (Улувату, Беноа, Чангу, Кута, Семиньяк)', 'other', 2500000, 1800000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('SKTT-2', 'Получение SKTT (Убуд)', 'other', 3800000, 3000000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('BD', 'Banjar Domisili', 'other', 2000000, 1500000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('KITAS-CHANGE', 'Перенос Китаса в новый паспорт', 'other', 1500000, 850000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('MUT-KITAS', 'Изменение данных в китас', 'other', 1500000, 850000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('EPO', 'Закрытие китаса (на Бали) (EPO)', 'other', 1500000, 850000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('ETK-OUT', 'Закрытие китаса (удаленно ETK)', 'other', 2500000, 1500000),  # нет в таблице 15.11 — выплаты партнёру решает менеджер
    Tariff('PERSONAL-COUNT', 'Открытие банковской карты (без KITAS)', 'other', 1500000, 50000, partner_price=950000, white_label=775000, market=2000000, l1=450000, l2=90000),
]

BY_CODE: dict[str, Tariff] = {t.code.upper(): t for t in TARIFFS}

# Вкладка «Популярное» — первой в каталоге (порядок важен)
POPULAR_CODES = ["C1", "E33G", "PERSONAL-COUNT", "DRIVER"]

CATEGORY_LABELS = {"popular": "Популярное", "kitas": "KITAS", "visa": "Визы", "ext": "Продления", "co": "Компании", "buh": "Бухгалтерия", "other": "Другое"}


# Коды в поле «Тип услуги» в Kommo, которые называются иначе, чем в прайсе.
# ПРОВЕРИТЬ с руководством: KITAS DEPEND — это Family KITAS; CART BNI — персональная карта BNI.
KOMMO_ALIASES = {
    "KITAS DEPEND-1": "E31B/E-1",
    "KITAS DEPEND-2": "E31B/E-2",
    "CART BNI": "PERSONAL-COUNT",
    "PMA": "PMA-1",
    "PERSONAL": "PERSONAL-COUNT",
    "C7": "C7 (АРТИСТА)",
}


def find_tariffs(code: str | None) -> list[Tariff]:
    """Все известные услуги из мультисписка «Тип услуги» («VOA-EXT, BRIDGE, E33G»)."""
    out = []
    for part in str(code or "").split(","):
        key = part.strip().upper()
        t = BY_CODE.get(key) or BY_CODE.get(KOMMO_ALIASES.get(key, ""))
        if t and t not in out:
            out.append(t)
    return out


def combined_tariff(code: str | None) -> Tariff | None:
    """Несколько услуг в одной сделке → одна «сборная»: цены и себестоимости складываются, маржа — сумма маржей."""
    ts = find_tariffs(code)
    if len(ts) <= 1:
        return ts[0] if ts else None
    known = all(t.l1 is not None for t in ts)
    return Tariff("+".join(t.code for t in ts)[:32], " + ".join(t.name for t in ts), "other",
                  sum(t.price for t in ts), sum(t.partner_cost for t in ts), in_catalog=False,
                  partner_price=sum(t.partner_price or t.price for t in ts),
                  l1=sum(t.l1 for t in ts) if known else None, l2=sum(t.l2 for t in ts) if known else None)


def find_tariff(code: str | None) -> Tariff | None:
    """Тариф по полю «Тип услуги» в Kommo. Поле — мультисписок («E33G, BUH-M»): берём первый известный код."""
    if not code:
        return None
    for part in str(code).split(","):
        key = part.strip().upper()
        t = BY_CODE.get(key) or BY_CODE.get(KOMMO_ALIASES.get(key, ""))
        if t:
            return t
    return None
