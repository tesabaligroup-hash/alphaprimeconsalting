"""Диагностика партнёра: найден ли он, какие сделки за ним в Kommo, что начислено и что он видит в приложении.

Запуск на сервере (имя можно писать как угодно — по-русски, латиницей, с @):
    docker compose exec api python -m app.diag_partner Кицунес
Заодно пересчитывает начисления по найденным сделкам.

Если в Kommo партнёр записан иначе, чем в приложении, — привязать:
    docker compose exec api python -m app.diag_partner Кицунес --link 7
(7 — id партнёра из вывода; в его карточку запишется, как он назван в Kommo)
"""
import sys
from collections import Counter
from datetime import timedelta
from difflib import SequenceMatcher

from sqlalchemy import select

from .db import SessionLocal
from .kommo import get_kommo
from .kommo.mapping import LEAD_FIELDS, NO_PARTNER_VALUES, norm
from .models import Accrual, Partner
from .partner_rules import ACCRUAL_LABELS
from .services.cabinet import field_value
from .services.partner import dashboard, find_partner_for_lead, loose_key, sync_lead
from .tariffs import find_tariff
from .timeutil import utcnow


def _like(key: str, *values) -> bool:
    """Похоже по написанию: Kissunets ≈ Кицунес ≈ kitsunes ≈ kitsune_bali (для проверки, не для начислений)."""
    for v in values:
        lv = loose_key(v)
        if not lv or not key:
            continue
        if len(lv) >= 4 and (key in lv or lv in key):
            return True
        score = max(SequenceMatcher(None, key, lv).ratio(), SequenceMatcher(None, key, lv[:len(key)]).ratio())
        if score >= 0.65:
            return True
    return False


def main(arg: str, link_id: int | None = None) -> None:
    key = loose_key(arg)
    k = get_kommo()
    with SessionLocal() as db:
        partners = [p for p in db.scalars(select(Partner))
                    if _like(key, p.display_name, p.codeword, p.kommo_partner_value, p.user.telegram_username if p.user else None)]
        print("=== Партнёр в приложении ===")
        if not partners:
            print(f"  «{arg}» не найден среди партнёров приложения.")
            print("  → человек должен открыть приложение → «Партнёрка» → «Стать партнёром» и выбрать кодовое слово.")
        for p in partners:
            nick = f"@{p.user.telegram_username}" if p.user and p.user.telegram_username else "без ника"
            print(f"  id {p.id} · {p.display_name} · {nick} · кодовое слово {p.codeword or '—'}"
                  f" · в Kommo «{p.kommo_partner_value or '—'}» · статус {p.status} · вступил {p.created_at:%d.%m.%Y}")

        print("\n=== Сделки в Kommo, где поле «Партнёр» похоже на", arg, "===")
        all_leads = list(k.get_leads_updated_since(utcnow() - timedelta(days=800)))
        values = Counter(str(field_value(lead.fields, LEAD_FIELDS["partner"]) or "") for lead in all_leads)
        leads = [lead for lead in all_leads if _like(key, str(field_value(lead.fields, LEAD_FIELDS["partner"]) or ""))]
        if link_id:
            p = db.get(Partner, link_id)
            kommo_names = sorted({str(field_value(lead.fields, LEAD_FIELDS["partner"])) for lead in leads})
            if p and len(kommo_names) == 1:
                p.kommo_partner_value = kommo_names[0]
                db.commit()
                print(f"  ✅ Привязано: партнёр {p.display_name} = «{kommo_names[0]}» в Kommo")
            else:
                print(f"  ❌ Не привязано: в Kommo найдено значений {kommo_names or 'ни одного'}. Напишите разработчику.")
        if not leads:
            print("  не найдено. Значения поля «Партнёр», которые есть в Kommo:")
            for v, n in values.most_common(40):
                if v and norm(v) not in NO_PARTNER_VALUES:
                    print(f"    «{v}» — {n} сд.")
        for lead in leads:
            service = field_value(lead.fields, LEAD_FIELDS["service_type"])
            value = field_value(lead.fields, LEAD_FIELDS["partner"])
            who = find_partner_for_lead(db, lead)
            print(f"\n  #{lead.id} «{lead.name}» · Партнёр «{value}» · этап «{lead.status_name}» · бюджет {lead.price:,}"
                  f" · услуга «{service}»" + ("" if find_tariff(str(service) if service else None) else "  ← услуга не из тарифов"))
            if not who:
                print("    ❌ партнёр приложения не узнан по этому значению — начисления нет."
                      + (f" Привяжите: --link {partners[0].id}" if len(partners) == 1 else ""))
                continue
            accs = sync_lead(db, k, lead)
            if not accs:
                print("    ⚠️ начисления нет (этап до «Ждем $»? сделка не в Consulting? консультация?)")
            for acc in accs:
                print(f"    → {who.display_name}: {acc.amount:,} IDR · {ACCRUAL_LABELS[acc.status]}")
        db.commit()

        for p in partners:
            total = list(db.scalars(select(Accrual).where(Accrual.partner_id == p.id)))
            d = dashboard(db, p)
            print(f"\n=== Что видит {p.display_name} в приложении ===")
            print(f"  начислений в базе: {len(total)} · к выплате {d['balance']['to_payout']:,} · ожидается {d['balance']['expected']:,}")
            for f in d.get("friends") or []:
                print(f"  • {f.get('name')} — {f.get('status_label') or f.get('status')} — {f.get('amount', 0):,} IDR")
            if not d.get("friends"):
                print("  друзей пока нет")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Укажите имя партнёра: python -m app.diag_partner Кицунес")
        sys.exit(1)
    link = int(args[args.index("--link") + 1]) if "--link" in args else None
    main(" ".join(a for i, a in enumerate(args) if a != "--link" and (i == 0 or args[i - 1] != "--link")), link)
