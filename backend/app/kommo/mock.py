"""Тестовые данные вместо Kommo — для разработки и показа, пока нет доступа к CRM.

Совпадает с примерами на макетах: Анна (KITAS E33G с доплатой), сын Миша (Family KITAS),
бухгалтерия PT PMA; друзья партнёра — Денис, Мария, Ольга.
"""
from datetime import datetime as _dt, timedelta, timezone

from .base import KommoContact, KommoFile, KommoLead, StatusChange

_BALI = timezone(timedelta(hours=8))


class datetime(_dt):  # noqa: N801 — даты Kommo: полночь по времени Бали, независимо от сервера
    def timestamp(self):
        return _dt(self.year, self.month, self.day, self.hour, self.minute, tzinfo=_BALI).timestamp()


NOW = datetime(2026, 11, 11, 10, 0)

_STATUSES = {
    1: "Ждем $", 2: "Оплата получена", 3: "Передано в производство", 4: "Услуга готова",
    5: "Ждем доплату", 6: "Ждет продления", 7: "Думает", 142: "Успешно реализовано", 143: "Закрыто и не реализовано",
}


def _lead(i, name, price, status, fields, contacts, created_days_ago=10):
    return KommoLead(id=i, name=name, price=price, pipeline_id=13724291, status_id=status, status_name=_STATUSES[status],
                     fields=fields, contact_ids=contacts, created_at=NOW - timedelta(days=created_days_ago),
                     updated_at=NOW - timedelta(days=1))


LEADS = {
    1001: _lead(1001, "Анна — E33G", 10_900_000, 5,
                {"Тип услуги": "E33G", "Оплатил": 7_000_000, "Долг": 3_900_000, "Дедлайн": int((NOW + timedelta(days=17)).timestamp())}, [501], 13),
    1002: _lead(1002, "Миша — Family KITAS", 13_000_000, 6,
                {"Тип услуги": "KITAS DEPEND-1", "Оплатил": 13_000_000, "Долг": 0,
                 "raw:Документы клиенту": [{"file_uuid": "f-kitas-m", "file_name": "Family KITAS — Миша.pdf"},
                                           {"file_uuid": "f-itk-m", "file_name": "ITK — Миша.pdf"}]}, [502, 501], 300),
    1003: _lead(1003, "PT PMA — бухгалтерия", 1_000_000, 3,
                {"Тип услуги": "BUH-M, CHANGE-KBLI", "Оплатил": 1_000_000, "Дедлайн": int(datetime(2026, 12, 15).timestamp())}, [501], 40),
    1004: _lead(1004, "Анна — C1", 2_000_000, 142,
                {"Тип услуги": "C1", "Оплатил": 2_000_000}, [501], 160),
    # Друзья партнёра ANNABALI
    2001: _lead(2001, "Денис — KITAS Investor", 17_575_000, 4,
                {"Тип услуги": "E28A-2-P", "Оплатил": 17_575_000, "Партнёр": "ANNABALI"}, [601], 30),
    2002: _lead(2002, "Мария — E33G", 10_705_000, 3,
                {"Тип услуги": "E33G", "Оплатил": 10_705_000, "Партнёр": "ANNABALI"}, [602], 8),
    2003: _lead(2003, "Ольга — PT PMA", 19_555_000, 1,
                {"Тип услуги": "PMA-1", "Оплатил": 0, "Долг": 19_555_000, "Партнёр": "ANNABALI"}, [603], 3),
}

CONTACTS = {
    501: KommoContact(501, "Анна", ["+62 812 0000 0001"], {"Имя Фамилия": "ANNA DIKINA", "Гражданство": "RUSIA",
                                                              "Паспорт до": int(datetime(2032, 3, 18).timestamp())}, [1001, 1002, 1003, 1004]),
    502: KommoContact(502, "Миша", [], {"Имя Фамилия": "MIKHAIL DIKIN", "ITK до": int(datetime(2027, 2, 2).timestamp())}, [1002]),
    601: KommoContact(601, "Денис Р.", ["+62 812 0000 0002"], {"Имя Фамилия": "DENIS ROMANOV"}, [2001]),
    602: KommoContact(602, "Мария К.", ["+62 812 0000 0003"], {"Имя Фамилия": "MARIA KUZNETSOVA"}, [2002]),
    603: KommoContact(603, "@olga_bali", ["+62 812 0000 0004"], {}, [2003]),
}

HISTORY = {
    1001: [StatusChange(1, "Ждем $", datetime(2026, 11, 4, 11, 5)), StatusChange(5, "Ждем доплату", datetime(2026, 11, 6, 9, 30))],
    1002: [StatusChange(4, "Услуга готова", datetime(2026, 2, 2, 12, 0)), StatusChange(6, "Ждет продления", datetime(2026, 2, 3, 9, 0))],
    1003: [StatusChange(2, "Оплата получена", datetime(2026, 10, 2, 10, 0)), StatusChange(3, "Передано в производство", datetime(2026, 10, 3, 10, 0))],
    2001: [StatusChange(2, "Оплата получена", datetime(2026, 10, 15, 10, 0)), StatusChange(4, "Услуга готова", datetime(2026, 11, 2, 15, 0))],
    2002: [StatusChange(2, "Оплата получена", datetime(2026, 11, 5, 10, 0)), StatusChange(3, "Передано в производство", datetime(2026, 11, 6, 10, 0))],
}

FILES = {
    1004: [KommoFile("f-c1", "КЛИЕНТУ — Виза C1 e-Visa.pdf", datetime(2026, 6, 12)),
           KommoFile("f-chat", "photo", datetime(2026, 6, 1))],  # вложение из чата — клиенту не показывается
    1002: [KommoFile("f-kitas-m", "Family KITAS — Миша.pdf", datetime(2026, 2, 2)), KommoFile("f-itk-m", "ITK — Миша.pdf", datetime(2026, 2, 2)),
           KommoFile("f-other", "CV_OTHER_PERSON.pdf", datetime(2026, 2, 1))],
}


class MockKommo:
    created: list[dict] = []

    def find_contact_ids_by_phone(self, phone: str) -> list[int]:
        d = "".join(ch for ch in phone if ch.isdigit())
        return [c.id for c in CONTACTS.values() if any("".join(ch for ch in p if ch.isdigit()).endswith(d[-9:]) for p in c.phones)]

    def find_contact_ids_by_telegram(self, username: str) -> list[int]:
        u = (username or "").lstrip("@").lower()
        return [c.id for c in CONTACTS.values() if str(c.fields.get("Логин", "")).lower() == u]

    def get_contact(self, contact_id: int):
        return CONTACTS.get(contact_id)

    def get_contacts(self, contact_ids):
        return [CONTACTS[i] for i in contact_ids if i in CONTACTS]

    def get_leads(self, lead_ids):
        return [LEADS[i] for i in lead_ids if i in LEADS]

    def get_status_history(self, lead_id):
        return HISTORY.get(lead_id, [])

    def get_lead_files(self, lead_id):
        return FILES.get(lead_id, [])

    def get_file_download_url(self, uuid):
        return None

    def get_leads_updated_since(self, since):
        return list(LEADS.values())

    def create_lead(self, *, title, contact_name, phone=None, telegram=None, note=None, tags=None, contact_id=None, price=None):
        self.created.append({"title": title, "contact_name": contact_name, "phone": phone, "telegram": telegram, "note": note,
                             "tags": tags, "contact_id": contact_id, "price": price})
        return 9000 + len(self.created)
