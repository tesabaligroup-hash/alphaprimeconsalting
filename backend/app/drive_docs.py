"""Визы/ITK из папок Google Диска (поле «Документы» у контакта Kommo) → приложение.

    python -m app.drive_docs --contact 12345           # проверить одного человека (ничего не сохраняет)
    python -m app.drive_docs --contact 12345 --apply   # сохранить его документы
    python -m app.drive_docs --limit 20                # проверить первых 20 человек с папками
    python -m app.drive_docs --apply                   # все (первый раз — долго и с расходом на ИИ)
"""
import argparse

from .db import SessionLocal, init_db
from .kommo import get_kommo
from .services import drive_docs as dd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contact", type=int)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    init_db()
    kommo = get_kommo()
    with SessionLocal() as db:
        print("Смотрю папки клиентов на Диске…")
        r = dd.sync_all(db, kommo, apply=a.apply, contact_id=a.contact, limit=a.limit)
    print(f"\nЛюдей с папкой: {r['contacts']} · файлов (PDF/фото): {r['files']} · новых виз/ITK: {r['new_docs']}"
          f" · чужих (не показаны): {r['skipped']} · ошибок: {r['errors']} · дат для Kommo: {r['dates']}")
    for d in r["details"][:40]:
        print(f"\n👤 {d['contact']}")
        for x in d["new_docs"]:
            print("   ✅ " + x)
        for x in d["skipped"]:
            print("   🚫 " + x)
        for x in d["errors"]:
            print("   ⚠️ " + x)
        for k, v in d["dates"].items():
            print(f"   📅 {k}: {v:%d.%m.%Y}")
    print("\n✅ Сохранено" if a.apply else "\n(проверка — файлы прочитаны ИИ, но клиентам ещё не показаны; чтобы сохранить: --apply)")


if __name__ == "__main__":
    main()
