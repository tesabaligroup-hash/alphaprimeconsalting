import io

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.kommo.base import KommoContact, KommoLead
from app.models import Partner, User
from app.services.partner_book import enrich


class FakeKommo:
    def __init__(self):
        self.contacts = {
            1: KommoContact(1, "IANA MALAKHOVA", ["+62 811 000 1111"], {"Логин": "ya_malakhova", "code:EMAIL": ["iana@x.com"]}, [10]),
            2: KommoContact(2, "ANNA BAGROVA", ["+7 900 000 22 22"], {}, []),
            3: KommoContact(3, "ANNA BAGROVA", ["+7 900 000 33 33"], {}, []),
        }
        self.leads = {10: KommoLead(10, "Iana", 0, 1, 2, "Оплата получена", {"Партнёр": "Kissunets"}, [1], None, None)}

    def find_contact_ids_by_telegram(self, u):
        return [c.id for c in self.contacts.values() if c.fields.get("Логин", "").lower() == u.lower()]

    def find_contact_ids_by_phone(self, p):
        d = "".join(ch for ch in p if ch.isdigit())
        return [c.id for c in self.contacts.values() if any("".join(ch for ch in x if ch.isdigit()).endswith(d[-9:]) for x in c.phones)]

    def search_contacts(self, q, limit=15):
        return [c for c in self.contacts.values() if q.lower() in c.name.lower()][:limit]

    def get_contact(self, cid):
        return self.contacts.get(cid)

    def get_leads(self, ids):
        return [self.leads[i] for i in ids if i in self.leads]


@pytest.fixture
def db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        u = User(telegram_id=5, telegram_username="Kissunets", phone="+62 812 555 0000")
        s.add(u)
        s.flush()
        s.add(Partner(user_id=u.id, display_name="Евгения Чуркина", codeword="KISSUNETS", payout_details="BCA 123"))
        s.commit()
        yield s


def _book(rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Список партнеров (чистый)"
    ws.append(["ПАРТНЕР", "Комментарий", "Контакт партнера", "Мессенджер", "КЛЮЧЕВОЕ СЛОВО", "СЧЕТ", "БАНК", "ОТ КОГО"])
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_fills_only_empty_cells(db):
    data = _book([
        ["IANA MALAKHOVA", "галерка", "t.me/ya_malakhova", "", "Галерка", "", "", ""],
        ["EVGENIIA CHURKINA", "Киссунец", "t.me/Kissunets", "TG раб", "", "", "", ""],
        ["ANNA BAGROVA", "", "", "", "", "", "", ""],
        ["ПЕРС", "", "", "", "", "", "", ""],
        ["ТАРГЕТ", "ИСТОЧНИК (реклама)", "", "", "", "", "", ""],
    ])
    out, stats = enrich(db, FakeKommo(), data)
    ws = load_workbook(io.BytesIO(out)).active
    hdr = {ws.cell(1, i).value: i for i in range(1, ws.max_column + 1)}
    # Iana: найдена по нику, «ОТ КОГО» — из поля «Партнёр» её сделки → партнёр Kissunets
    assert ws.cell(2, hdr["Kommo"]).value.endswith("1")
    assert ws.cell(2, hdr["Email"]).value == "iana@x.com"
    assert ws.cell(2, 4).value == "TG"
    assert ws.cell(2, 5).value == "Галерка"  # написанное менеджером не меняется
    assert ws.cell(2, 8).value == "ЕВГЕНИЯ ЧУРКИНА"
    # Churkina: в приложении — кодовое слово и реквизиты, «TG раб» не трогаем
    assert ws.cell(3, 5).value == "KISSUNETS" and ws.cell(3, 6).value == "BCA 123" and ws.cell(3, 4).value == "TG раб"
    assert "партнёр" in ws.cell(3, hdr["В приложении"]).value
    # Bagrova: два контакта с таким именем — ничего не подставляем, просим проверить
    assert ws.cell(4, 3).value in (None, "") and "2 похожих" in ws.cell(4, hdr["Проверить"]).value
    assert "не нашла" in ws.cell(5, hdr["Проверить"]).value
    assert ws.cell(6, hdr["Проверить"]).value in (None, "")  # источник пропускаем
    assert stats["rows"] == 4
