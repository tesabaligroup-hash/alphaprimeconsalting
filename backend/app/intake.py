"""Ручная проверка автозаявки на одной сделке.

    python -m app.intake --lead 12345            # показать, что будет сделано (ничего не меняет)
    python -m app.intake --lead 12345 --apply    # создать заявку в таблице производства
    python -m app.intake --lead 12345 --ready    # проверить готовую визу в сделке (ничего не меняет)
    python -m app.intake --lead 12345 --ready --apply
"""
import argparse
import json

from .db import SessionLocal, init_db
from .kommo import get_kommo
from .services import intake


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lead", type=int, required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ready", action="store_true")
    a = ap.parse_args()
    init_db()
    kommo = get_kommo()
    leads = kommo.get_leads([a.lead])
    if not leads:
        print("Сделка не найдена")
        return
    lead = leads[0]
    print(f"Сделка {lead.id}: {lead.name} · этап «{lead.status_name}»")
    with SessionLocal() as db:
        if a.ready:
            rep = intake.process_ready(db, kommo, lead, apply=a.apply)
        else:
            if a.apply is False and db.get(intake.IntakeRecord, lead.id):
                print("По этой сделке заявка уже создавалась.")
                return
            rep = intake.process_paid(db, kommo, lead, apply=a.apply)
    if not rep:
        print("Заявка по этой сделке уже есть.")
        return
    for d in rep.pop("docs", []):
        print(f"  📄 {d.get('file')}: {intake.DOC_RU.get(d.get('doc_type'), d.get('doc_type'))} · "
              f"{d.get('full_name') or ''} {('· до ' + d['passport_expiry']) if d.get('passport_expiry') else ''}"
              f"{(' · ' + d['note']) if d.get('note') else ''}")
    print(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    print("\n✅ Готово" if a.apply else "\n(проверка — ничего не изменено; чтобы выполнить, добавьте --apply)")


if __name__ == "__main__":
    main()
