"""Таблица производства → приложение и Kommo.

    python -m app.table_sync            # отчёт: что будет сделано (ничего не меняет)
    python -m app.table_sync --apply    # записать: начисления партнёрам + даты виз/ITK в Kommo
    python -m app.table_sync --apply --move   # + перевести выполненные сделки в «Услуга готова»
"""
import argparse

from .db import SessionLocal, init_db
from .kommo import get_kommo
from .services import table_sync as ts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--move", action="store_true")
    ap.add_argument("--all", action="store_true", help="показать списки полностью")
    a = ap.parse_args()
    init_db()
    kommo = get_kommo()
    with SessionLocal() as db:
        print("Читаю таблицу производства и контакты Kommo…")
        r = ts.run(db, kommo, apply=a.apply, move_stages=a.move, notify=False)
    lim = None if a.all else 15
    print(f"\nСтрок в «Производстве»: {r['table_rows']} · строк с датами виз: {r['renewal_rows']}")

    print(f"\n=== ДАТЫ ВИЗ / ITK ===\nЛюдей с действующей датой: {r['visa']['rows']} · уже верно в Kommo: {r['visa']['same']}"
          f" · записать: {len(r['visa_plan'])} · не нашли в Kommo: {len(r['visa']['not_found'])}")
    for p in r["visa_plan"][:lim]:
        was = f" (было {p['was']:%d.%m.%Y})" if p["was"] else ""
        print(f"  ✏️ {p['client']} → «{p['field']}» {p['date']:%d.%m.%Y}{was}")
    if r["visa"]["not_found"]:
        print("  Не нашли в Kommo (нет контакта с таким именем):")
        for x in r["visa"]["not_found"][:lim]:
            print("   · " + x)

    print(f"\n=== ПАРТНЁРЫ ===\nСтрок с партнёром: {r['partners'].get('rows_with_partner')}")
    for k, v in (r["partners"].get("matched") or {}).items():
        print(f"  ✅ {k}: {v} строк")
    unknown = r["partners"].get("unknown_partners") or {}
    if unknown:
        print("  ❓ Не нашли партнёра в приложении (проверьте имя в «Список партнеров» и контакт):")
        for k, v in sorted(unknown.items(), key=lambda x: -x[1]):
            print(f"   · {k}: {v} строк")

    print(f"\n=== ЭТАПЫ ===\nВыполнено по таблице, а в Kommo ещё не «Услуга готова»: {len(r['moves'])}")
    for m in r["moves"][:lim]:
        print(f"  → {m['client']}: «{m['from']}» → «Услуга готова» (сделка {m['lead_id']})")
    for d in r["doubts"][:lim]:
        print("  ⚠️ " + d)

    if a.apply:
        print(f"\n✅ Записано: контактов с датами — {r['contacts_updated']}, начислений — {r['partners'].get('accruals')},"
              f" сделок переведено — {r['moved']}")
    else:
        print("\n(проверка — ничего не изменено; чтобы записать: --apply, и этапы: --apply --move)")


if __name__ == "__main__":
    main()
