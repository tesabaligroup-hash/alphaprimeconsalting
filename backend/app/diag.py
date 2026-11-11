"""Диагностика: почему клиент не видит свои данные.

Запуск на сервере:
    docker compose exec api python -m app.diag souzemlivod      # ник Telegram
    docker compose exec api python -m app.diag +79119761793     # или телефон
"""
import sys

from sqlalchemy import or_, select

from .db import SessionLocal
from .kommo import get_kommo
from .kommo.mapping import CLIENT_PIPELINE_IDS, CONTACT_FIELDS, LEAD_FIELDS, STATUS_TO_STEP, STATUS_WON, norm
from .models import User
from .services.cabinet import as_date, field_value, load_client
from .services.linking import find_contact, find_contacts, link_user


def main(arg: str) -> None:
    k = get_kommo()
    key = arg.lstrip("@")
    digits = "".join(ch for ch in arg if ch.isdigit())
    with SessionLocal() as db:
        q = [User.telegram_username.ilike(key)]
        if len(digits) >= 7:
            q.append(User.phone.like(f"%{digits[-9:]}"))
        users = list(db.scalars(select(User).where(or_(*q))))
        print("=== Пользователь в приложении ===")
        if not users:
            print("  не найден — человек ещё не открывал бота/приложение")
        for u in users:
            print(f"  Telegram: @{u.telegram_username}  id {u.telegram_id}  телефон: {u.phone or 'НЕ ПРИСЛАН'}  контакт Kommo: {u.kommo_contact_id or 'НЕ ПРИВЯЗАН'}")

        phone = users[0].phone if users and users[0].phone else (arg if len(digits) >= 7 else None)
        username = users[0].telegram_username if users else (key if len(digits) < 7 else None)
        print("\n=== Поиск в Kommo ===")
        print(f"  по телефону {phone}: {k.find_contact_ids_by_phone(phone) if phone else '—'}")
        print(f"  по нику @{username}: {k.find_contact_ids_by_telegram(username) if username else '—'}")
        print(f"  основной контакт: {find_contact(k, phone, username)}")

        ids = list(dict.fromkeys(([users[0].kommo_contact_id] if users and users[0].kommo_contact_id else []) + find_contacts(k, phone, username)))
        if not ids:
            print("\nКонтакт в Kommo не найден.")
            return
        for cid in ids:
            c = k.get_contact(cid)
            if not c:
                continue
            print(f"\n=== Контакт {cid}: {c.name} ===")
            for f in ("full_name", "visa_until", "itk_until", "passport_until", "current_visa"):
                v = field_value(c.fields, CONTACT_FIELDS[f])
                print(f"  {CONTACT_FIELDS[f]}: {as_date(v) if 'until' in f and v else v}")
            print(f"  телефоны: {c.phones}")
            print(f"  сделки ({len(c.lead_ids)}):")
            for lead in k.get_leads(c.lead_ids):
                visible = lead.pipeline_id in CLIENT_PIPELINE_IDS and (lead.status_id == STATUS_WON or norm(lead.status_name) in STATUS_TO_STEP)
                why = "показывается" if visible else ("другая воронка" if lead.pipeline_id not in CLIENT_PIPELINE_IDS else f"этап «{lead.status_name}» клиенту не показывается")
                print(f"    #{lead.id}  этап: {lead.status_name or lead.status_id}  тип услуги: {field_value(lead.fields, LEAD_FIELDS['service_type'])}"
                      f"  оплатил: {field_value(lead.fields, LEAD_FIELDS['paid_amount'])}  → {why}")
        if users:
            link_user(db, k, users[0], refresh=True)
            print(f"\n✓ Привязка обновлена: основной контакт {users[0].kommo_contact_id}, дубли {users[0].kommo_extra_contact_ids}")
        data = load_client(k, users[0].contact_ids if users else ids, with_history=False)
        print(f"\n=== Что увидит клиент ===\n  услуг: {len(data['services'])}, в архиве: {len(data['archive'])}")
        for d in data["dates"]:
            print(f"  дата: {d['date']} — {d['title']} ({d['person']})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Укажите ник Telegram или телефон: python -m app.diag souzemlivod")
    main(sys.argv[1])
