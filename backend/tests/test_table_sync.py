"""Таблица производства → начисления партнёрам, даты виз, этапы."""
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.kommo.base import KommoContact
from app.kommo.mock import MockKommo
from app.models import Accrual, Base, Partner, User
from app.services import table_sync as ts

DATA = {
    "production": [
        [2, "04.02.2026", "Лена", "Котики на Мотиках", "VOA", "", "ГОТОВО", "KYZLASOVA OLGA", "850 000", "850 000", "0", "175 000"],
        [3, "16.11.2026", "Оксана", "kitsunes", "E33G", "", "Партнерку выплатить", "ANNA DIKINA", "7 900 000", "7 900 000", "0", ""],
        [4, "17.11.2026", "Оксана", "Неизвестный", "C1", "", "1. Подать документы", "IVAN IVANOV", "2 000 000", "2 000 000", "0", ""],
        [5, "17.11.2026", "Оксана", "", "", "", "", "", "", "", "", ""],
    ],
    "renewals": [["E33G", "ANNA DIKINA", "TERBIT", "28.03.2027"], ["E33G", "ANNA DIKINA", "TERBIT", "28.03.2026"],
                 ["C1", "MIKHAIL DIKIN", "", "01/12/2026"], ["VOA", "OLD CLIENT", "Close", "01.12.2026"],
                 ["C1", "NOBODY HERE", "", "-"]],
    "partners": [["Котики на Мотиках", "t.me/kvg100"]],
}


@pytest.fixture
def db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    s = Session(eng)
    for i, (nick, word) in enumerate([("kvg100", "KOTIKI1"), ("kitsunes", "KITSUNES")], start=1):
        u = User(telegram_id=100 + i, first_name=nick, telegram_username=nick)
        s.add(u); s.flush()
        s.add(Partner(user_id=u.id, display_name=nick, codeword=word))
    s.commit()
    return s


def test_parse_and_statuses():
    t = ts.parse_table(DATA)
    assert len(t.rows) == 3 and [r.status for r in t.rows] == ["paid", "to_payout", "in_work"]
    assert t.rows[0].partner_share == 175_000 and t.rows[0].start == date(2026, 2, 4)
    assert ts.parse_date("11/11/2026") == date(2026, 11, 11) and ts.parse_date("-") is None


def test_accruals_from_table(db):
    t = ts.parse_table(DATA)
    notes, rep = ts.sync_accruals(db, t)
    accs = {a.client_display: a for a in db.scalars(select(Accrual))}
    assert accs["Kyzlasova O."].status == "paid" and accs["Kyzlasova O."].amount == 175_000  # «Котики» — через t.me/kvg100
    anna = next(a for a in accs.values() if a.amount == 1_000_000)  # сумма не указана → тариф E33G
    assert anna.status == "to_payout" and anna.to_payout_at
    assert rep["unknown_partners"] == {"Неизвестный": 1} and not notes  # первый проход — без уведомлений
    # статус поменялся в таблице → уведомление партнёру
    DATA2 = {**DATA, "production": [DATA["production"][1][:6] + ["ГОТОВО"] + DATA["production"][1][7:]]}
    notes, _ = ts.sync_accruals(db, ts.parse_table(DATA2))
    assert len(notes) == 1 and "отправлена" in notes[0][1]
    assert len(list(db.scalars(select(Accrual)))) == 2  # Ольга (выплачено) остаётся, строка Анны — одна


def test_kommo_expected_replaced_only_when_in_table(db):
    # «ожидается» по Kommo: Ольга уже есть в таблице у этого партнёра → убираем; Пётр ещё нет → остаётся
    db.add(Accrual(partner_id=1, level=1, kommo_lead_id=555, period="", client_display="Kyzlasova O.", amount=1, status="in_work"))
    db.add(Accrual(partner_id=1, level=1, kommo_lead_id=556, period="", client_display="Petr P.", amount=1, status="in_work"))
    db.commit()
    ts.sync_accruals(db, ts.parse_table(DATA))
    assert not db.scalar(select(Accrual).where(Accrual.kommo_lead_id == 555))
    assert db.scalar(select(Accrual).where(Accrual.kommo_lead_id == 556))


def test_visa_updates_latest_date_and_field():
    k = MockKommo()
    plan, rep = ts.visa_updates(ts.parse_table(DATA), k.all_contacts(), today=date(2026, 11, 17))
    by = {(p["client"], p["field"]): p["date"] for p in plan}
    assert by[("ANNA DIKINA", "ITK до")] == date(2027, 3, 28)  # самая поздняя дата, E33G → ITK
    assert by[("MIKHAIL DIKIN", "Виза до")] == date(2026, 12, 1)
    assert not any(p["client"] == "OLD CLIENT" for p in plan)  # Close — пропускаем


def test_stage_moves_only_single_open_lead(monkeypatch):
    k = MockKommo()
    contacts = [KommoContact(900, "Olga", [], {"Имя Фамилия": "KYZLASOVA OLGA"}, [1003])]
    t = ts.parse_table({"production": [DATA["production"][0][:7] + ["KYZLASOVA OLGA"] + DATA["production"][0][8:]]})
    t.rows[0].start = date(2026, 10, 5)
    moves, doubts = ts.stage_moves(k, t, contacts)
    assert [m["lead_id"] for m in moves] == [1003]
    contacts[0].lead_ids = [1001, 1003]  # две открытые сделки — не трогаем
    moves, doubts = ts.stage_moves(k, t, contacts)
    assert not moves and doubts


def test_stage_moves_skip_waiting_for_money():
    k = MockKommo()
    contacts = [KommoContact(900, "Olga", [], {"Имя Фамилия": "KYZLASOVA OLGA"}, [1001])]  # 1001 — «Ждем доплату»
    t = ts.parse_table({"production": [DATA["production"][0][:7] + ["KYZLASOVA OLGA"] + DATA["production"][0][8:]]})
    moves, doubts = ts.stage_moves(k, t, contacts)
    assert not moves and "проверьте оплату" in doubts[0]


def test_partner_list_contact_and_keyword_and_lead_guard():
    from app.services.table_sync import lead_id_of, parse_table
    t = parse_table({"production": [], "renewals": [],
                     "partners": [["EVGENIIA CHURKINA", "t.me/Kissunets", "Kissunets"], ["Без контакта", "", ""]]})
    assert t.partner_contacts["evgeniia churkina"] == "t.me/Kissunets"
    assert t.partner_contacts["kissunets"] == "t.me/Kissunets"
    assert "без контакта" not in t.partner_contacts
    assert lead_id_of("25887677") == 25887677
    assert lead_id_of("2500000") is None and lead_id_of("2 500 000") is None and lead_id_of("-5500000") is None
