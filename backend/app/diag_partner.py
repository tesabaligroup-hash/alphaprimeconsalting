"""Диагностика партнёра: найден ли он, какие сделки за ним в Kommo и что ему начислено.

Запуск на сервере:
    docker compose exec api python -m app.diag_partner aplebedev
Заодно пересчитывает начисления по найденным сделкам.
"""
import sys
from datetime import timedelta

from sqlalchemy import or_, select

from .db import SessionLocal
from .kommo import get_kommo
from .kommo.mapping import LEAD_FIELDS, norm
from .models import Accrual, Partner, User
from .partner_rules import ACCRUAL_LABELS
from .services.cabinet import field_value
from .services.partner import find_partner_for_lead, sync_lead
from .tariffs import find_tariff
from .timeutil import utcnow


def main(arg: str) -> None:
    key = arg.strip().lstrip("@")
    k = get_kommo()
    with SessionLocal() as db:
        partners = list(db.scalars(select(Partner).join(User, Partner.user_id == User.id).where(or_(
            Partner.kommo_partner_value.ilike(key), Partner.codeword.ilike(key), User.telegram_username.ilike(key)))))
        print("=== Партнёр в приложении ===")
        if not partners:
            print(f"  не найден по «{key}» (ни ник Telegram, ни кодовое слово, ни поле «Как записан в Kommo»)")
            print("  → человек должен открыть приложение и нажать «Стать партнёром», либо впишите это значение")
            print("    в админке → Партнёры → карточка → «Как записан в поле Партнёр в Kommo»")
        for p in partners:
            print(f"  id {p.id} · {p.display_name} · @{p.user.telegram_username} · кодовое слово {p.codeword or '—'}"
                  f" · в Kommo «{p.kommo_partner_value or '—'}» · статус {p.status} · вступил {p.created_at:%d.%m.%Y}")

        print("\n=== Сделки в Kommo с полем «Партнёр» =", key, "===")
        leads = [lead for lead in k.get_leads_updated_since(utcnow() - timedelta(days=800))
                 if norm(str(field_value(lead.fields, LEAD_FIELDS["partner"]) or "")).lstrip("@") == norm(key)]
        if not leads:
            print("  не найдено")
        for lead in leads:
            service = field_value(lead.fields, LEAD_FIELDS["service_type"])
            who = find_partner_for_lead(db, lead)
            print(f"\n  #{lead.id} «{lead.name}» · этап «{lead.status_name}» · бюджет {lead.price:,} · услуга «{service}»"
                  + ("" if find_tariff(str(service) if service else None) else "  ← услуга не из тарифов: менеджер укажет её в админке"))
            if not who:
                print("    партнёр не найден в приложении — начисления нет")
                continue
            for acc in sync_lead(db, k, lead):
                print(f"    → {who.display_name}: {acc.amount:,} IDR · {ACCRUAL_LABELS[acc.status]}")
        db.commit()
        if partners:
            total = list(db.scalars(select(Accrual).where(Accrual.partner_id.in_([p.id for p in partners]))))
            print(f"\nВсего начислений у партнёра: {len(total)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Укажите ник партнёра: python -m app.diag_partner aplebedev")
        sys.exit(1)
    main(sys.argv[1])
