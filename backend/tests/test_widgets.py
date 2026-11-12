"""Виджеты Telegram: состояние в лимите, HTML в лимите, widget_query доходит до обработчика."""
import asyncio
import json
import zlib
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import widgets
from app.kommo.mock import MockKommo
from app.models import Base, News, Partner, ServiceOrder, User


def _db():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    return Session(eng)


def test_html_fits_telegram_limits():
    for kind in widgets.KINDS:
        html = widgets.html_for(kind).encode()
        assert len(html) <= 32768 and len(zlib.compress(html, 9)) <= 4096, kind
        assert "__APP__" not in html.decode()


def test_visa_state_for_mock_client_fits():
    db = _db()
    u = User(telegram_id=1, kommo_contact_id=501)
    db.add(u); db.commit()
    s = widgets.visa_state(MockKommo(), u)
    assert s["s"] and len(json.dumps(s, ensure_ascii=False).encode()) <= 1024
    assert all(0 <= x["i"] < x["c"] for x in s["s"])
    assert "оплат" not in widgets.caption("partner", widgets.partner_state(db, u))  # у не-партнёра — нули, без ошибок


def test_unlinked_user_gets_hint():
    assert "номером" in widgets.visa_state(MockKommo(), User(telegram_id=2))["m"]


def test_events_query_creates_interest_and_answers(monkeypatch):
    db = _db()
    u = User(telegram_id=7, first_name="Оля")
    db.add(u)
    n = News(title="Волки в Нуану", body="Специальный вход", kind="company", published=True, cta_lead=True)
    db.add(n); db.commit()
    calls = []

    async def fake_tg(method, payload):
        calls.append((method, payload))
        return {"message_id": 10}

    monkeypatch.setattr(widgets, "tg", fake_tg)
    monkeypatch.setattr("app.services.interest.notify_managers", lambda *a, **k: None)
    kommo = MockKommo()
    asyncio.run(widgets.send(db, kommo, u, "events"))
    asyncio.run(widgets.handle_query(db, kommo, {"id": "q1", "from": {"id": 7}, "data": f"ev:{n.id}"}))
    assert db.query(ServiceOrder).filter_by(service_code=f"news:{n.id}").count() == 1
    assert ("answerWidgetQuery", {"widget_query_id": "q1", "data": "ok"}) in calls
    edit = [p for m, p in calls if m == "editMessageWidgetData"][-1]
    assert json.loads(edit["chat_data"])["ok"] == [n.id]


def test_partner_state_has_no_prices():
    db = _db()
    u = User(telegram_id=9)
    db.add(u); db.flush()
    db.add(Partner(user_id=u.id, kind="private", display_name="Лена", codeword="LENAWOLF", created_at=datetime(2026, 1, 1)))
    db.commit()
    s = widgets.partner_state(db, u)
    assert set(s) == {"n", "p", "e", "t", "f", "d", "k"}


def test_widget_query_reaches_middleware(monkeypatch):
    from aiogram import Bot
    from aiogram.types import Update

    from app import worker
    got = []

    async def fake_handle(db, kommo, q):
        got.append(q)

    monkeypatch.setattr(worker.widgets, "handle_query", fake_handle)
    upd = Update.model_validate({"update_id": 1, "widget_query": {"id": "5", "from": {"id": 1}, "data": "ev:1"}})
    bot = Bot("123:abc")
    asyncio.run(worker.dp.feed_update(bot, upd))
    assert got and got[0]["id"] == "5"
