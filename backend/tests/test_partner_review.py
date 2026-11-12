"""Партнёрка: сделки с «Другое» и старые сделки уходят менеджеру на проверку; совпадение по нику Telegram."""
import os
import tempfile
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/t.db")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.kommo.base import KommoLead  # noqa: E402
from app.kommo.mock import MockKommo  # noqa: E402
from app.models import Base, Partner, User  # noqa: E402
from app.services.partner import sync_lead  # noqa: E402

DONE = 142


def _db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return Session(eng)


def _lead(service, partner="aplebedev", lead_id=17063039):
    return KommoLead(id=lead_id, name="Roman", price=5_000_000, pipeline_id=13724291, status_id=DONE, status_name="Успешно реализовано",
                     fields={"Партнёр": partner, "Тип услуги": service}, contact_ids=[],
                     updated_at=datetime(2026, 7, 7))


def test_unknown_service_and_old_deal_go_to_review_then_approve():
    db = _db()
    u = User(telegram_id=5, telegram_username="APLebedev", first_name="Андрей")
    db.add(u); db.flush()
    p = Partner(user_id=u.id, kind="private", display_name="Андрей", created_at=datetime(2026, 11, 1))
    db.add(p); db.flush()
    kommo = MockKommo()

    (acc,) = sync_lead(db, kommo, _lead("Другое"))  # партнёр найден по нику Telegram
    assert acc.partner_id == p.id and acc.status == "review" and acc.amount == 0

    acc.manual_code = "D12-EXT"
    (acc,) = sync_lead(db, kommo, _lead("Другое"))
    assert acc.status == "review" and acc.amount > 0  # сумма есть, но сделка старая — ждём решения

    acc.decision = "approved"
    (acc,) = sync_lead(db, kommo, _lead("Другое"))
    assert acc.status == "to_payout"

    acc.decision = "paid"
    (acc,) = sync_lead(db, kommo, _lead("Другое"))
    assert acc.status == "paid"


def test_new_deal_with_known_service_needs_no_review():
    db = _db()
    u = User(telegram_id=6, telegram_username="x")
    db.add(u); db.flush()
    db.add(Partner(user_id=u.id, kind="private", display_name="X", codeword="XWOLF7", created_at=datetime(2026, 1, 1)))
    db.flush()
    (acc,) = sync_lead(db, MockKommo(), _lead("D12-EXT", partner="xwolf7", lead_id=1))
    assert acc.status == "to_payout" and acc.amount > 0


def test_autofill_partner_for_referral_lead_and_next_deals():
    from app.models import Referral
    from app.services.partner import autofill_partner
    from app.timeutil import utcnow

    db = _db()
    u = User(telegram_id=7, telegram_username="lena")
    db.add(u); db.flush()
    p = Partner(user_id=u.id, kind="private", display_name="Лена", codeword="LENAWOLF", created_at=datetime(2026, 1, 1))
    db.add(p); db.flush()
    db.add(Referral(partner_id=p.id, friend_name="Олег", channel="tg", contact="@oleg", status="attached",
                    attached_at=utcnow(), kommo_lead_id=501))
    db.flush()
    kommo = MockKommo()

    first = KommoLead(id=501, name="Рекомендация: Олег", price=0, pipeline_id=13724291, status_id=1, status_name="Распределение",
                      fields={}, contact_ids=[777], updated_at=datetime(2026, 11, 12))
    assert autofill_partner(db, kommo, first) == p and kommo.partner_set[501] == "LENAWOLF"
    assert p.kommo_partner_value == "LENAWOLF"

    nxt = KommoLead(id=502, name="Олег KITAS", price=0, pipeline_id=13724291, status_id=1, status_name="Ждем $",
                    fields={}, contact_ids=[777], updated_at=datetime(2026, 11, 12))
    assert autofill_partner(db, kommo, nxt) == p and kommo.partner_set[502] == "LENAWOLF"

    manual_no = KommoLead(id=503, name="Олег", price=0, pipeline_id=13724291, status_id=1, status_name="Ждем $",
                          fields={"Партнёр": "Нет"}, contact_ids=[777], updated_at=datetime(2026, 11, 12))
    assert autofill_partner(db, kommo, manual_no) is None  # «Нет» от менеджера не трогаем


def test_weekly_report_lists_problem_deals():
    from app.services.quality import lead_problems

    bad = _lead("Другое", partner="")
    bad.status_name = "Ждем $"
    probs = lead_problems(bad)
    assert any("Тип услуги" in x for x in probs) and any("Партнёр" in x for x in probs)
    good = _lead("D12-EXT", partner="Нет")
    good.status_name = "Ждем $"
    good.contact_ids = [1]
    assert lead_problems(good) == []


def test_partner_found_by_russian_spelling_in_kommo():
    db = _db()
    u = User(telegram_id=11, telegram_username="kitsunes")
    db.add(u); db.flush()
    p = Partner(user_id=u.id, kind="private", display_name="Kitsunes", codeword="KITSUNE8", created_at=datetime(2026, 1, 1))
    db.add(p); db.flush()
    from app.services.partner import find_partner_for_lead
    assert find_partner_for_lead(db, _lead("E33G", partner="Кицунес")) == p
    assert find_partner_for_lead(db, _lead("E33G", partner="Другой человек")) is None


def test_multi_service_deal_sums_all_services_and_early_stage_is_not_review():
    from app.tariffs import combined_tariff
    t = combined_tariff("VOA-EXT, BRIDGE, E33G")
    assert t.code == "VOA-EXT+BRIDGE+E33G" and t.price == sum(x.price for x in [combined_tariff("VOA-EXT"), combined_tariff("BRIDGE"), combined_tariff("E33G")])
    db = _db()
    u = User(telegram_id=12, telegram_username="jeny")
    db.add(u); db.flush()
    db.add(Partner(user_id=u.id, kind="private", display_name="Jeny", codeword="KISSUNETS", created_at=datetime(2026, 1, 1)))
    db.flush()
    early = KommoLead(id=77, name="Рекомендация: Вика", price=0, pipeline_id=13724291, status_id=105886603,
                      status_name="РАСПРЕДЕЛЕНИЕ", fields={"Партнёр": "Kissunets"}, contact_ids=[], updated_at=datetime(2026, 11, 12))
    (acc,) = sync_lead(db, MockKommo(), early)
    assert acc.status == "awaiting_payment"  # друг виден, но это не «Проверяем»
