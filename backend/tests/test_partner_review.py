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
