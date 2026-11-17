"""Разослать партнёрам сообщение «программа обновлена, суммы пересчитаны».

Сначала пересчитывает все сделки из Kommo по новой таблице, потом показывает, кому что уйдёт.
    docker compose exec api python -m app.notify_partners          — только показать (ничего не отправляет)
    docker compose exec api python -m app.notify_partners --send   — отправить
В сообщении только суммы партнёра — без услуг, цен и процентов (правило программы).
"""
import sys
from datetime import timedelta

from sqlalchemy import select

from .db import SessionLocal
from .kommo import get_kommo
from .models import Partner
from .notify import notify_user
from .services.partner import dashboard, sync_all
from .timeutil import utcnow


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def text_for(name: str, b: dict, friends: int) -> str:
    return (f"{name}, мы обновили партнёрскую программу Alpha Prime 🤝\n\n"
            "Теперь за каждого друга — фиксированное вознаграждение. Оно начисляется, когда друг оплатил услугу и мы её полностью выполнили. "
            "Мы уже пересчитали ваши суммы:\n"
            f"• друзей: {friends}\n• ожидается: {fmt(b['expected'])} IDR\n• к выплате: {fmt(b['to_payout'])} IDR\n\n"
            "Подробности — в приложении, раздел «Партнёрка». "
            "Если кого-то не видите — там же кнопка «Связаться с менеджером».")


def main(send: bool) -> None:
    kommo = get_kommo()
    with SessionLocal() as db:
        print("Пересчитываю сделки из Kommo…")
        sync_all(db, kommo, utcnow() - timedelta(days=800))
        db.commit()
        sent = 0
        for p in db.scalars(select(Partner).where(Partner.status == "active")):
            d = dashboard(db, p)
            friends = len(d.get("friends") or [])
            if not friends:
                continue
            msg = text_for(p.display_name, d["balance"], friends)
            print(f"\n— {p.display_name} (@{p.user.telegram_username if p.user else '—'}): друзей {friends}, "
                  f"ожидается {fmt(d['balance']['expected'])}, к выплате {fmt(d['balance']['to_payout'])}")
            if send and p.user and notify_user(p.user.telegram_id, msg):
                sent += 1
        print(f"\nОтправлено: {sent}" if send else "\nЭто проверка. Чтобы отправить, добавьте --send")


if __name__ == "__main__":
    main("--send" in sys.argv)
