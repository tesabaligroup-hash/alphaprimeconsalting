"""Прайс и себестоимость для партнёров (из «Тарифы партнёрской программы Alpha Prime.xlsx», 11.11.2026).

Сгенерировано из таблицы — при изменении прайса правьте здесь или (позже) в админке.
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


TARIFFS: list[Tariff] = [
    Tariff('VOA', 'B1 - eVoA', 'visa', 750000, 500000),
    Tariff('VOA-EXT', 'VOA (продление)', 'ext', 1200000, 850000),
    Tariff('BRIDGE', 'Bridge Visa', 'visa', 5000000, 3500000),
    Tariff('C1', 'C1', 'visa', 2000000, 1000000),
    Tariff('C1-EXT', 'C1 (продление)', 'ext', 2500000, 1500000),
    Tariff('C7 (АРТИСТА)', 'С7 (A/B/C)', 'visa', 3500000, 1500000),
    Tariff('C18', 'C18 Work Trial', 'visa', 5500000, 3500000),
    Tariff('D12-1', 'Pre-Investment D12 (на 1 год)', 'visa', 7000000, 6000000),
    Tariff('D12-2', 'Pre-Investment D12 (на 2 года)', 'visa', 10500000, 8000000),
    Tariff('D12-EXT', 'D12 (продление без вылета)', 'ext', 4500000, 3300000),
    Tariff('E28A-2-P', 'KITAS Investor (2 года)', 'kitas', 18000000, 9500000),
    Tariff('E28A-1-P', 'KITAS Investor (1 год)', 'kitas', 13000000, 7000000),
    Tariff('E31B/E-1', 'Family KITAS (1 год)', 'kitas', 13000000, 6000000),
    Tariff('E31B/E-2', 'Family KITAS (2 года)', 'kitas', 18000000, 8500000),
    Tariff('E33F', 'Пенсионный Китас на 1 год', 'kitas', 12500000, 7000000, in_catalog=False),
    Tariff('STUDY-1', 'Школьный китас на 1 год', 'kitas', 13000000, 7000000, in_catalog=False),
    Tariff('STUDY-2', 'Школьный китас на 2 года', 'kitas', 18000000, 9500000, in_catalog=False),
    Tariff('E33G', 'Китас удаленщика E33G', 'kitas', 10900000, 7000000),
    Tariff('E33G-EXT', 'Продление Китаса удаленщика E33G', 'ext', 12500000, 10000000),
    Tariff('DRIVER', 'Водительские права за 1 категорию', 'other', 2000000, 1500000),
    Tariff('WORK-PT-05', 'Working KITAS (6 мес)', 'kitas', 34000000, 28000000),
    Tariff('WORK-PT-1', 'Working KITAS (1 год)', 'kitas', 44000000, 38000000),
    Tariff('PMA-1', 'Регистрация компании PT РМА (до 50 млрд.)', 'co', 19900000, 13000000),
    Tariff('PMA-2', 'Регистрация компании PT РМА (от 50 млрд.)', 'co', 24900000, 16000000),
    Tariff('ADR', 'Виртуальный офис (год)', 'co', 5000000, 3000000),
    Tariff('PT', 'Регистрация компании РТ', 'co', 13000000, 7500000),
    Tariff('CHANGE-KBLI', 'Изменение данных в РМА (1 KBLI)', 'co', 1000000, 500000),
    Tariff('CHANGE-PMA-N', 'Изменение данных в РМА (нотариальные)', 'co', 12000000, 9000000),
    Tariff('COUNT-PT-1', 'Открытие расчет. счета на компанию (с KITAS)', 'co', 2500000, 1500000),
    Tariff('COUNT-PT-2', 'Открытие расчет. счета на компанию (без KITAS)', 'co', 3500000, 2500000),
    Tariff('COUNT-PT-3', 'Открытие расчет. счета на компанию + терминал', 'co', 4500000, 3500000),
    Tariff('BUH-M', 'Ежемесячное ведение', 'buh', 1000000, 500000, monthly=True),
    Tariff('BUH-Q', 'Квартальные отчеты', 'buh', 2000000, 1000000),
    Tariff('BUH-Y', 'Годовой отчет', 'buh', 3000000, 2000000),
    Tariff('BUH-STAMP', 'Оплата штампа', 'buh', 400000, 200000),
    Tariff('SKTT-1', 'Получение SKTT (Улувату, Беноа, Чангу, Кута, Семиньяк)', 'other', 2500000, 1800000),
    Tariff('SKTT-2', 'Получение SKTT (Убуд)', 'other', 3800000, 3000000),
    Tariff('BD', 'Banjar Domisili', 'other', 2000000, 1500000),
    Tariff('KITAS-CHANGE', 'Перенос Китаса в новый паспорт', 'other', 1500000, 850000),
    Tariff('MUT-KITAS', 'Изменение данных в китас', 'other', 1500000, 850000),
    Tariff('EPO', 'Закрытие китаса (на Бали) (EPO)', 'other', 1500000, 850000),
    Tariff('ETK-OUT', 'Закрытие китаса (удаленно ETK)', 'other', 2500000, 1500000),
    Tariff('PERSONAL-COUNT', 'Открытие персональной банковской карты', 'other', 1500000, 500000),
]

BY_CODE: dict[str, Tariff] = {t.code.upper(): t for t in TARIFFS}

CATEGORY_LABELS = {"kitas": "KITAS", "visa": "Визы", "ext": "Продления", "co": "Компании", "buh": "Бухгалтерия", "other": "Другое"}


# Коды в поле «Тип услуги» в Kommo, которые называются иначе, чем в прайсе.
# ПРОВЕРИТЬ с руководством: KITAS DEPEND — это Family KITAS; CART BNI — персональная карта BNI.
KOMMO_ALIASES = {
    "KITAS DEPEND-1": "E31B/E-1",
    "KITAS DEPEND-2": "E31B/E-2",
    "CART BNI": "PERSONAL-COUNT",
    "PMA": "PMA-1",
    "C7": "C7 (АРТИСТА)",
}


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
